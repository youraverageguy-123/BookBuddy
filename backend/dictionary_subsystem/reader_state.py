from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class ReaderKnowledgeStore:
    """Operational reader state kept outside every book graph database."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_profiles (
                user_id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_term_history (
                user_id TEXT NOT NULL, object_kind TEXT NOT NULL, object_id INTEGER NOT NULL,
                first_viewed TEXT, last_viewed TEXT, view_count INTEGER DEFAULT 0,
                marked_known INTEGER DEFAULT 0, ignored INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, object_kind, object_id),
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_book_state (
                user_id TEXT NOT NULL, session_key TEXT NOT NULL,
                favorite INTEGER NOT NULL DEFAULT 0,
                want_to_read INTEGER NOT NULL DEFAULT 0,
                last_opened_at REAL, last_cfi TEXT NOT NULL DEFAULT '',
                current_chapter INTEGER, chapter_progress REAL NOT NULL DEFAULT 0,
                book_progress REAL NOT NULL DEFAULT 0,
                added_at REAL, finished_at REAL, updated_at REAL NOT NULL,
                PRIMARY KEY(user_id, session_key),
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            book_columns = {row[1] for row in conn.execute("PRAGMA table_info(reader_book_state)")}
            for name, definition in {"title_override":"TEXT", "author_override":"TEXT", "description_override":"TEXT", "series_override":"TEXT", "rating":"REAL", "tags_json":"TEXT", "knowledge_through_chapter":"INTEGER", "analysis_mode":"TEXT"}.items():
                if name not in book_columns:
                    conn.execute(f"ALTER TABLE reader_book_state ADD COLUMN {name} {definition}")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_chapter_progress (
                user_id TEXT NOT NULL, session_key TEXT NOT NULL, chapter_index INTEGER NOT NULL,
                last_cfi TEXT NOT NULL DEFAULT '', current_progress REAL NOT NULL DEFAULT 0,
                contiguous_progress REAL NOT NULL DEFAULT 0,
                threshold_started INTEGER NOT NULL DEFAULT 0,
                naturally_completed INTEGER NOT NULL DEFAULT 0,
                committed INTEGER NOT NULL DEFAULT 0,
                retry_required INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY(user_id, session_key, chapter_index),
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_bookmarks (
                bookmark_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_key TEXT NOT NULL,
                chapter_index INTEGER NOT NULL, cfi TEXT NOT NULL, excerpt TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL, name TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            bookmark_columns = {row[1] for row in conn.execute("PRAGMA table_info(reader_bookmarks)")}
            if "name" not in bookmark_columns:
                conn.execute("ALTER TABLE reader_bookmarks ADD COLUMN name TEXT NOT NULL DEFAULT ''")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_collections (
                collection_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                description TEXT NOT NULL DEFAULT '', pinned INTEGER NOT NULL DEFAULT 0,
                book_sort TEXT NOT NULL DEFAULT 'recent', custom_cover TEXT,
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            collection_columns = {row[1] for row in conn.execute("PRAGMA table_info(reader_collections)")}
            for name, definition in {"description":"TEXT NOT NULL DEFAULT ''", "pinned":"INTEGER NOT NULL DEFAULT 0", "book_sort":"TEXT NOT NULL DEFAULT 'recent'", "custom_cover":"TEXT"}.items():
                if name not in collection_columns:
                    conn.execute(f"ALTER TABLE reader_collections ADD COLUMN {name} {definition}")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS reader_collections_name
                ON reader_collections(user_id, name COLLATE NOCASE)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_collection_members (
                collection_id TEXT NOT NULL, session_key TEXT NOT NULL, added_at REAL NOT NULL,
                PRIMARY KEY(collection_id, session_key),
                FOREIGN KEY(collection_id) REFERENCES reader_collections(collection_id) ON DELETE CASCADE
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_annotations (
                annotation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_key TEXT NOT NULL,
                chapter_index INTEGER NOT NULL, cfi_range TEXT NOT NULL, quote TEXT NOT NULL DEFAULT '',
                annotation_type TEXT NOT NULL, color TEXT NOT NULL DEFAULT 'gold', note_text TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS reader_annotations_session ON reader_annotations(user_id, session_key, chapter_index)")
            conn.execute("""CREATE TABLE IF NOT EXISTS reader_sessions (
                reading_session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_key TEXT NOT NULL,
                started_at REAL NOT NULL, ended_at REAL NOT NULL, active_seconds REAL NOT NULL,
                start_progress REAL NOT NULL DEFAULT 0, end_progress REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES reader_profiles(user_id) ON DELETE CASCADE
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS reader_sessions_daily ON reader_sessions(user_id, started_at)")

    def create_profile(self) -> str:
        user_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute("INSERT INTO reader_profiles(user_id) VALUES (?)", (user_id,))
        return user_id

    def profile_exists(self, user_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM reader_profiles WHERE user_id = ?", (user_id,)).fetchone() is not None

    def _require_profile(self, user_id: str) -> None:
        if not self.profile_exists(user_id):
            raise LookupError("reader profile not found")

    @staticmethod
    def _book_row(row: sqlite3.Row) -> dict:
        import json
        return {
            "session_key": row["session_key"], "favorite": bool(row["favorite"]),
            "want_to_read": bool(row["want_to_read"]), "last_opened_at": row["last_opened_at"],
            "last_cfi": row["last_cfi"], "current_chapter": row["current_chapter"],
            "chapter_progress": float(row["chapter_progress"]), "book_progress": float(row["book_progress"]),
            "added_at": row["added_at"], "finished_at": row["finished_at"], "updated_at": row["updated_at"],
            "title_override": row["title_override"], "author_override": row["author_override"], "description_override": row["description_override"], "series_override": row["series_override"], "rating": row["rating"], "tags": json.loads(row["tags_json"] or "[]"),
            # The reader's own statement of how far they have read, used to unlock
            # story knowledge without touching reading progress. None = not set.
            "knowledge_through_chapter": row["knowledge_through_chapter"],
            "analysis_mode": row["analysis_mode"],
        }

    @staticmethod
    def _chapter_row(row: sqlite3.Row) -> dict:
        return {
            "session_key": row["session_key"], "chapter_index": int(row["chapter_index"]),
            "last_cfi": row["last_cfi"], "current_progress": float(row["current_progress"]),
            "contiguous_progress": float(row["contiguous_progress"]),
            "threshold_started": bool(row["threshold_started"]),
            "naturally_completed": bool(row["naturally_completed"]), "committed": bool(row["committed"]),
            "retry_required": bool(row["retry_required"]), "updated_at": row["updated_at"],
        }

    def library_state(self, user_id: str) -> dict:
        self._require_profile(user_id)
        with self._connect() as conn:
            books = [self._book_row(row) for row in conn.execute(
                "SELECT * FROM reader_book_state WHERE user_id = ? ORDER BY COALESCE(last_opened_at, 0) DESC", (user_id,)
            )]
            chapters = [self._chapter_row(row) for row in conn.execute(
                "SELECT * FROM reader_chapter_progress WHERE user_id = ? ORDER BY session_key, chapter_index", (user_id,)
            )]
            collections = []
            for row in conn.execute("SELECT * FROM reader_collections WHERE user_id = ? ORDER BY sort_order, created_at", (user_id,)):
                members = [item[0] for item in conn.execute(
                    "SELECT session_key FROM reader_collection_members WHERE collection_id = ? ORDER BY added_at", (row["collection_id"],)
                )]
                collections.append({"collection_id": row["collection_id"], "name": row["name"], "sort_order": row["sort_order"], "session_keys": members, "description": row["description"], "pinned": bool(row["pinned"]), "book_sort": row["book_sort"], "custom_cover": row["custom_cover"], "created_at": row["created_at"], "updated_at": row["updated_at"]})
            bookmarks = [dict(row) for row in conn.execute(
                "SELECT bookmark_id, session_key, chapter_index, cfi, excerpt, name, created_at FROM reader_bookmarks WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
            )]
            annotation_counts = {row["session_key"]: int(row["count"]) for row in conn.execute(
                "SELECT session_key, COUNT(*) AS count FROM reader_annotations WHERE user_id=? GROUP BY session_key", (user_id,)
            )}
        smart = {
            "currently_reading": [item["session_key"] for item in books if item["book_progress"] > 0 and not item["finished_at"]],
            "favorites": [item["session_key"] for item in books if item["favorite"]],
            "finished": [item["session_key"] for item in books if item["finished_at"]],
            "want_to_read": [item["session_key"] for item in books if item["want_to_read"]],
        }
        return {"schema_version": "bookbuddy_reader_library_v1", "user_id": user_id, "books": books, "chapters": chapters, "collections": collections, "bookmarks": bookmarks, "annotation_counts": annotation_counts, "smart_collections": smart}

    def upsert_book_state(self, user_id: str, session_key: str, values: dict) -> dict:
        self._require_profile(user_id)
        now = time.time()
        allowed = {"favorite", "want_to_read", "last_opened_at", "last_cfi", "current_chapter", "chapter_progress", "book_progress", "added_at", "finished_at", "title_override", "author_override", "description_override", "series_override", "rating", "tags"}
        clean = {key: values[key] for key in allowed if key in values and values[key] is not None}
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM reader_book_state WHERE user_id = ? AND session_key = ?", (user_id, session_key)).fetchone()
            merged = self._book_row(existing) if existing else {
                "favorite": False, "want_to_read": False, "last_opened_at": None, "last_cfi": "", "current_chapter": None,
                "chapter_progress": 0.0, "book_progress": 0.0, "added_at": now, "finished_at": None, "title_override": None, "author_override": None, "description_override": None, "series_override": None, "rating": None, "tags": [],
            }
            merged.update(clean)
            import json
            merged["tags"] = [" ".join(str(tag).split())[:80] for tag in (merged.get("tags") or []) if " ".join(str(tag).split())]
            merged["chapter_progress"] = max(0.0, min(1.0, float(merged["chapter_progress"])))
            merged["book_progress"] = max(0.0, min(1.0, float(merged["book_progress"])))
            conn.execute("""INSERT INTO reader_book_state
                (user_id, session_key, favorite, want_to_read, last_opened_at, last_cfi, current_chapter, chapter_progress, book_progress, added_at, finished_at, updated_at, title_override, author_override, description_override, series_override, rating, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_key) DO UPDATE SET
                favorite=excluded.favorite, want_to_read=excluded.want_to_read,
                last_opened_at=excluded.last_opened_at, last_cfi=excluded.last_cfi,
                current_chapter=excluded.current_chapter, chapter_progress=excluded.chapter_progress,
                book_progress=excluded.book_progress, added_at=COALESCE(reader_book_state.added_at, excluded.added_at),
                finished_at=COALESCE(reader_book_state.finished_at, excluded.finished_at), updated_at=excluded.updated_at,
                title_override=excluded.title_override, author_override=excluded.author_override,
                description_override=excluded.description_override, series_override=excluded.series_override,
                rating=excluded.rating, tags_json=excluded.tags_json""",
                (user_id, session_key, int(bool(merged["favorite"])), int(bool(merged["want_to_read"])), merged["last_opened_at"],
                 str(merged["last_cfi"] or "")[:2000], merged["current_chapter"], merged["chapter_progress"], merged["book_progress"],
                 merged["added_at"], merged["finished_at"], now, merged["title_override"], merged["author_override"], merged["description_override"], merged["series_override"], merged["rating"], json.dumps(merged["tags"])))
            if "knowledge_through_chapter" in values and values["knowledge_through_chapter"] is not None:
                declared = int(values["knowledge_through_chapter"])
                conn.execute(
                    "UPDATE reader_book_state SET knowledge_through_chapter = ? WHERE user_id = ? AND session_key = ?",
                    (declared if declared >= 0 else None, user_id, session_key),
                )
            if values.get("analysis_mode") in {"off", "auto", "custom"}:
                conn.execute(
                    "UPDATE reader_book_state SET analysis_mode = ? WHERE user_id = ? AND session_key = ?",
                    (values["analysis_mode"], user_id, session_key),
                )
            row = conn.execute("SELECT * FROM reader_book_state WHERE user_id = ? AND session_key = ?", (user_id, session_key)).fetchone()
        return self._book_row(row)

    def upsert_chapter_progress(self, user_id: str, session_key: str, chapter_index: int, values: dict) -> dict:
        self._require_profile(user_id)
        now = time.time()
        with self._connect() as conn:
            old = conn.execute("SELECT * FROM reader_chapter_progress WHERE user_id=? AND session_key=? AND chapter_index=?", (user_id, session_key, chapter_index)).fetchone()
            previous = self._chapter_row(old) if old else {"last_cfi": "", "current_progress": 0.0, "contiguous_progress": 0.0, "threshold_started": False, "naturally_completed": False, "committed": False, "retry_required": False}
            current = max(0.0, min(1.0, float(values.get("current_progress", previous["current_progress"]))))
            contiguous = max(previous["contiguous_progress"], max(0.0, min(1.0, float(values.get("contiguous_progress", previous["contiguous_progress"])))))
            flags = {key: bool(previous[key] or values.get(key, False)) for key in ("threshold_started", "naturally_completed", "committed")}
            retry = bool(values.get("retry_required", previous["retry_required"]))
            if flags["committed"]:
                retry = False
            conn.execute("""INSERT INTO reader_chapter_progress
                (user_id, session_key, chapter_index, last_cfi, current_progress, contiguous_progress, threshold_started, naturally_completed, committed, retry_required, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_key, chapter_index) DO UPDATE SET
                last_cfi=excluded.last_cfi, current_progress=excluded.current_progress,
                contiguous_progress=MAX(reader_chapter_progress.contiguous_progress, excluded.contiguous_progress),
                threshold_started=MAX(reader_chapter_progress.threshold_started, excluded.threshold_started),
                naturally_completed=MAX(reader_chapter_progress.naturally_completed, excluded.naturally_completed),
                committed=MAX(reader_chapter_progress.committed, excluded.committed),
                retry_required=CASE WHEN excluded.committed=1 THEN 0 ELSE excluded.retry_required END,
                updated_at=excluded.updated_at""",
                (user_id, session_key, chapter_index, str(values.get("last_cfi", previous["last_cfi"]) or "")[:2000], current, contiguous,
                 int(flags["threshold_started"]), int(flags["naturally_completed"]), int(flags["committed"]), int(retry), now))
            row = conn.execute("SELECT * FROM reader_chapter_progress WHERE user_id=? AND session_key=? AND chapter_index=?", (user_id, session_key, chapter_index)).fetchone()
        return self._chapter_row(row)

    def import_legacy_state(self, user_id: str, books: list[dict], chapters: list[dict]) -> dict:
        self._require_profile(user_id)
        imported_books = imported_chapters = 0
        with self._connect() as conn:
            for item in books:
                if not conn.execute("SELECT 1 FROM reader_book_state WHERE user_id=? AND session_key=?", (user_id, item["session_key"])).fetchone():
                    self.upsert_book_state(user_id, item["session_key"], item)
                    imported_books += 1
            for item in chapters:
                if not conn.execute("SELECT 1 FROM reader_chapter_progress WHERE user_id=? AND session_key=? AND chapter_index=?", (user_id, item["session_key"], item["chapter_index"])).fetchone():
                    self.upsert_chapter_progress(user_id, item["session_key"], int(item["chapter_index"]), item)
                    imported_chapters += 1
        return {"schema_version": "bookbuddy_reader_import_v1", "imported_books": imported_books, "imported_chapters": imported_chapters}

    def create_collection(self, user_id: str, name: str, description: str = "", pinned: bool = False, book_sort: str = "recent", custom_cover: str | None = None) -> dict:
        self._require_profile(user_id)
        name = " ".join(name.split())
        if not name or len(name) > 80:
            raise ValueError("collection name must contain 1 to 80 characters")
        now = time.time(); collection_id = str(uuid.uuid4())
        try:
            with self._connect() as conn:
                order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM reader_collections WHERE user_id=?", (user_id,)).fetchone()[0]
                conn.execute("INSERT INTO reader_collections(collection_id,user_id,name,sort_order,created_at,updated_at,description,pinned,book_sort,custom_cover) VALUES(?,?,?,?,?,?,?,?,?,?)", (collection_id,user_id,name,order,now,now,description[:1000],int(pinned),book_sort,custom_cover))
        except sqlite3.IntegrityError as exc:
            raise ValueError("a collection with this name already exists") from exc
        return {"collection_id": collection_id, "name": name, "sort_order": order, "session_keys": [], "description": description[:1000], "pinned": bool(pinned), "book_sort": book_sort, "custom_cover": custom_cover, "created_at": now, "updated_at": now}

    def update_collection(self, user_id: str, collection_id: str, name: str | None = None, sort_order: int | None = None, description: str | None = None, pinned: bool | None = None, book_sort: str | None = None, custom_cover: str | None = None) -> dict:
        self._require_profile(user_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reader_collections WHERE collection_id=? AND user_id=?", (collection_id,user_id)).fetchone()
            if not row: raise LookupError("collection not found")
            clean_name = " ".join((name if name is not None else row["name"]).split())
            if not clean_name or len(clean_name) > 80: raise ValueError("collection name must contain 1 to 80 characters")
            try:
                conn.execute("UPDATE reader_collections SET name=?, sort_order=?, description=?, pinned=?, book_sort=?, custom_cover=?, updated_at=? WHERE collection_id=?", (clean_name, max(0, sort_order if sort_order is not None else row["sort_order"]), (description if description is not None else row["description"])[:1000], int(pinned if pinned is not None else row["pinned"]), book_sort or row["book_sort"], custom_cover if custom_cover is not None else row["custom_cover"], time.time(), collection_id))
            except sqlite3.IntegrityError as exc: raise ValueError("a collection with this name already exists") from exc
        return next(item for item in self.library_state(user_id)["collections"] if item["collection_id"] == collection_id)

    def delete_collection(self, user_id: str, collection_id: str) -> None:
        self._require_profile(user_id)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM reader_collections WHERE collection_id=? AND user_id=?", (collection_id,user_id))
            if not cursor.rowcount: raise LookupError("collection not found")

    def set_collection_member(self, user_id: str, collection_id: str, session_key: str, present: bool) -> dict:
        self._require_profile(user_id)
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM reader_collections WHERE collection_id=? AND user_id=?", (collection_id,user_id)).fetchone(): raise LookupError("collection not found")
            if present: conn.execute("INSERT OR IGNORE INTO reader_collection_members(collection_id,session_key,added_at) VALUES(?,?,?)", (collection_id,session_key,time.time()))
            else: conn.execute("DELETE FROM reader_collection_members WHERE collection_id=? AND session_key=?", (collection_id,session_key))
        return next(item for item in self.library_state(user_id)["collections"] if item["collection_id"] == collection_id)

    def create_bookmark(self, user_id: str, session_key: str, chapter_index: int, cfi: str, excerpt: str = "", name: str = "") -> dict:
        self._require_profile(user_id)
        bookmark_id = str(uuid.uuid4()); created_at = time.time()
        with self._connect() as conn:
            conn.execute("INSERT INTO reader_bookmarks(bookmark_id,user_id,session_key,chapter_index,cfi,excerpt,created_at,name) VALUES(?,?,?,?,?,?,?,?)", (bookmark_id,user_id,session_key,chapter_index,cfi[:2000]," ".join(excerpt.split())[:240],created_at," ".join(name.split())[:120]))
        return {"bookmark_id": bookmark_id, "session_key": session_key, "chapter_index": chapter_index, "cfi": cfi[:2000], "excerpt": " ".join(excerpt.split())[:240], "name": " ".join(name.split())[:120], "created_at": created_at}

    def update_bookmark(self, user_id: str, bookmark_id: str, name: str) -> dict:
        self._require_profile(user_id)
        with self._connect() as conn:
            cursor = conn.execute("UPDATE reader_bookmarks SET name=? WHERE bookmark_id=? AND user_id=?", (" ".join(name.split())[:120], bookmark_id, user_id))
            if not cursor.rowcount: raise LookupError("bookmark not found")
            row = conn.execute("SELECT bookmark_id,session_key,chapter_index,cfi,excerpt,name,created_at FROM reader_bookmarks WHERE bookmark_id=?", (bookmark_id,)).fetchone()
        return dict(row)

    def delete_bookmark(self, user_id: str, bookmark_id: str) -> None:
        self._require_profile(user_id)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM reader_bookmarks WHERE bookmark_id=? AND user_id=?", (bookmark_id,user_id))
            if not cursor.rowcount: raise LookupError("bookmark not found")

    def list_annotations(self, user_id: str, session_key: str | None = None, query: str = "") -> list[dict]:
        self._require_profile(user_id)
        sql = "SELECT annotation_id,session_key,chapter_index,cfi_range,quote,annotation_type,color,note_text,created_at,updated_at FROM reader_annotations WHERE user_id=?"
        values: list[object] = [user_id]
        if session_key:
            sql += " AND session_key=?"; values.append(session_key)
        if query.strip():
            sql += " AND (quote LIKE ? OR note_text LIKE ?)"; needle = f"%{query.strip()[:200]}%"; values.extend([needle, needle])
        sql += " ORDER BY updated_at DESC LIMIT 5000"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, values)]

    def create_annotation(self, user_id: str, session_key: str, chapter_index: int, cfi_range: str, quote: str, annotation_type: str, color: str = "gold", note_text: str = "") -> dict:
        self._require_profile(user_id)
        if annotation_type not in {"highlight", "underline", "note"}: raise ValueError("invalid annotation type")
        annotation_id = str(uuid.uuid4()); now = time.time()
        values = (annotation_id,user_id,session_key,chapter_index,cfi_range[:4000],quote[:2000],annotation_type,color[:24],note_text[:20000],now,now)
        with self._connect() as conn:
            conn.execute("INSERT INTO reader_annotations(annotation_id,user_id,session_key,chapter_index,cfi_range,quote,annotation_type,color,note_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", values)
        return self.get_annotation(user_id, annotation_id)

    def get_annotation(self, user_id: str, annotation_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT annotation_id,session_key,chapter_index,cfi_range,quote,annotation_type,color,note_text,created_at,updated_at FROM reader_annotations WHERE annotation_id=? AND user_id=?", (annotation_id,user_id)).fetchone()
        if not row: raise LookupError("annotation not found")
        return dict(row)

    def update_annotation(self, user_id: str, annotation_id: str, values: dict) -> dict:
        current = self.get_annotation(user_id, annotation_id)
        annotation_type = values.get("annotation_type", current["annotation_type"])
        if annotation_type not in {"highlight", "underline", "note"}: raise ValueError("invalid annotation type")
        with self._connect() as conn:
            conn.execute("UPDATE reader_annotations SET annotation_type=?,color=?,note_text=?,updated_at=? WHERE annotation_id=? AND user_id=?", (annotation_type,str(values.get("color",current["color"]))[:24],str(values.get("note_text",current["note_text"]))[:20000],time.time(),annotation_id,user_id))
        return self.get_annotation(user_id, annotation_id)

    def delete_annotation(self, user_id: str, annotation_id: str) -> None:
        self._require_profile(user_id)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM reader_annotations WHERE annotation_id=? AND user_id=?", (annotation_id,user_id))
            if not cursor.rowcount: raise LookupError("annotation not found")

    def record_reading_session(self, user_id: str, session_key: str, started_at: float, ended_at: float, active_seconds: float, start_progress: float, end_progress: float) -> dict:
        self._require_profile(user_id)
        if ended_at < started_at or active_seconds < 0: raise ValueError("invalid reading session")
        reading_session_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute("INSERT INTO reader_sessions(reading_session_id,user_id,session_key,started_at,ended_at,active_seconds,start_progress,end_progress) VALUES(?,?,?,?,?,?,?,?)", (reading_session_id,user_id,session_key,started_at,ended_at,min(active_seconds,ended_at-started_at),max(0,min(1,start_progress)),max(0,min(1,end_progress))))
        return {"reading_session_id":reading_session_id,"session_key":session_key,"started_at":started_at,"ended_at":ended_at,"active_seconds":min(active_seconds,ended_at-started_at),"start_progress":start_progress,"end_progress":end_progress}

    def reading_statistics(self, user_id: str) -> dict:
        self._require_profile(user_id)
        with self._connect() as conn:
            totals = conn.execute("SELECT COALESCE(SUM(active_seconds),0),COUNT(*),COUNT(DISTINCT session_key) FROM reader_sessions WHERE user_id=?", (user_id,)).fetchone()
            days = [row[0] for row in conn.execute("SELECT DISTINCT date(started_at,'unixepoch','localtime') FROM reader_sessions WHERE user_id=? AND active_seconds>0 ORDER BY 1 DESC", (user_id,))]
            per_book_rows = conn.execute("SELECT session_key,COALESCE(SUM(active_seconds),0),COALESCE(SUM(CASE WHEN end_progress>start_progress THEN end_progress-start_progress ELSE 0 END),0),COUNT(*) FROM reader_sessions WHERE user_id=? GROUP BY session_key", (user_id,)).fetchall()
            today = conn.execute("SELECT COALESCE(SUM(active_seconds),0) FROM reader_sessions WHERE user_id=? AND date(started_at,'unixepoch','localtime')=date('now','localtime')", (user_id,)).fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM reader_book_state WHERE user_id=? AND finished_at IS NOT NULL", (user_id,)).fetchone()[0]
        streak = 0
        if days:
            from datetime import date, timedelta
            expected = date.today()
            for value in days:
                day = date.fromisoformat(value)
                if day == expected: streak += 1; expected -= timedelta(days=1)
                elif day < expected: break
        per_book = {}
        for session_key, active_seconds, progress_delta, session_count in per_book_rows:
            active = float(active_seconds); delta = float(progress_delta)
            per_book[str(session_key)] = {"active_seconds":active,"progress_delta":delta,"session_count":int(session_count),"seconds_per_book":active/delta if delta >= .01 else None,"sufficient_data":active >= 300 and delta >= .01}
        session_count = int(totals[1])
        return {"active_seconds":float(totals[0]),"session_count":session_count,"books_read":int(completed),"current_streak_days":streak,"average_session_seconds":float(totals[0])/session_count if session_count else 0.0,"today_active_seconds":float(today),"per_book":per_book}

    def export_reading_sessions(self, user_id: str) -> list[dict]:
        """Return only local timing/progress telemetry; never book text or selections."""
        self._require_profile(user_id)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                """SELECT reading_session_id,session_key,started_at,ended_at,active_seconds,
                          start_progress,end_progress
                   FROM reader_sessions WHERE user_id=? ORDER BY started_at""",
                (user_id,),
            )]

    def reset_reading_sessions(self, user_id: str) -> int:
        self._require_profile(user_id)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM reader_sessions WHERE user_id=?", (user_id,))
            return int(cursor.rowcount)

    def _validate(self, user_id: str, object_kind: str, object_id: int):
        if object_kind not in {"entity", "terminology"} or int(object_id) <= 0:
            raise ValueError("invalid knowledge object")
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM reader_profiles WHERE user_id = ?", (user_id,)).fetchone():
                raise LookupError("reader profile not found")

    def record_view(self, user_id: str, object_kind: str, object_id: int) -> dict:
        self._validate(user_id, object_kind, object_id)
        with self._connect() as conn:
            conn.execute("""INSERT INTO reader_term_history
                (user_id, object_kind, object_id, first_viewed, last_viewed, view_count)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(user_id, object_kind, object_id) DO UPDATE SET
                    last_viewed = CURRENT_TIMESTAMP, view_count = view_count + 1""", (user_id, object_kind, object_id))
        return self.get(user_id, object_kind, object_id)

    def set_flag(self, user_id: str, object_kind: str, object_id: int, flag: str, value: bool = True) -> dict:
        if flag not in {"marked_known", "ignored"}:
            raise ValueError("invalid reader flag")
        self._validate(user_id, object_kind, object_id)
        with self._connect() as conn:
            conn.execute("""INSERT INTO reader_term_history (user_id, object_kind, object_id, marked_known, ignored)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, object_kind, object_id) DO UPDATE SET
                    marked_known = CASE WHEN ? = 'marked_known' THEN ? ELSE marked_known END,
                    ignored = CASE WHEN ? = 'ignored' THEN ? ELSE ignored END""",
                (user_id, object_kind, object_id, int(value) if flag == "marked_known" else 0, int(value) if flag == "ignored" else 0, flag, int(value), flag, int(value)))
        return self.get(user_id, object_kind, object_id)

    def get(self, user_id: str, object_kind: str, object_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("""SELECT first_viewed, last_viewed, view_count, marked_known, ignored
                FROM reader_term_history WHERE user_id = ? AND object_kind = ? AND object_id = ?""", (user_id, object_kind, object_id)).fetchone()
        return {"user_id": user_id, "object_kind": object_kind, "object_id": object_id, "first_viewed": row[0] if row else None, "last_viewed": row[1] if row else None, "view_count": row[2] if row else 0, "marked_known": bool(row[3]) if row else False, "ignored": bool(row[4]) if row else False}
