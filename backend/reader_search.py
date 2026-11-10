"""Rebuildable reader-text FTS index, deliberately separate from canonical graph search."""
from __future__ import annotations
import hashlib
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

SEARCH_SCHEMA_VERSION = 1


class ReaderSearchService:
    def __init__(self, root: str):
        self.root = Path(root) / "search"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_key: str) -> Path:
        return self.root / f"{hashlib.sha256(session_key.encode('utf-8')).hexdigest()}.sqlite"

    def index_book(self, session_key: str, book) -> dict:
        path = self._path(session_key); temp = path.with_suffix(".building")
        if temp.exists(): temp.unlink()
        conn = sqlite3.connect(temp)
        try:
            conn.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            conn.execute("CREATE VIRTUAL TABLE documents USING fts5(chapter_index UNINDEXED,chapter_title UNINDEXED,spine_href UNINDEXED,paragraph_index UNINDEXED,text,tokenize='unicode61 remove_diacritics 2')")
            count = words = 0
            for chapter in book.chapters:
                chunks = [part.strip() for part in re.split(r"(?:\r?\n){2,}|(?<=[.!?])\s+(?=[A-Z])", chapter.content or "") if part.strip()]
                if not chunks and chapter.content.strip(): chunks = [chapter.content.strip()]
                for paragraph_index, text in enumerate(chunks):
                    conn.execute("INSERT INTO documents(chapter_index,chapter_title,spine_href,paragraph_index,text) VALUES(?,?,?,?,?)", (chapter.index,chapter.title,getattr(chapter,"spine_href",""),paragraph_index,text[:10000]))
                    count += 1; words += len(text.split())
            conn.executemany("INSERT INTO metadata(key,value) VALUES(?,?)", (("schema_version",str(SEARCH_SCHEMA_VERSION)),("session_key",session_key),("indexed_at",str(time.time())),("word_count",str(words))))
            conn.commit()
        finally: conn.close()
        temp.replace(path)
        return {"documents":count,"word_count":words,"schema_version":SEARCH_SCHEMA_VERSION}

    def search(self, session_key: str, query: str, limit: int = 50, max_chapter: int | None = None, chapter: int | None = None) -> dict:
        path = self._path(session_key)
        if not path.exists(): raise LookupError("search index is not ready")
        tokens = re.findall(r"[\w'-]+", query, flags=re.UNICODE)
        if not tokens: return {"results":[],"elapsed_ms":0}
        # Quote every token so punctuation cannot become an FTS5 operator.
        expression = " ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)[:500]
        where = ["documents MATCH ?"]; values: list[object] = [expression]
        if chapter is not None: where.append("chapter_index=?"); values.append(chapter)
        elif max_chapter is not None: where.append("chapter_index<=?"); values.append(max_chapter)
        values.append(max(1,min(100,limit))); started = time.perf_counter()
        with closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT chapter_index,chapter_title,spine_href,paragraph_index,snippet(documents,4,'<mark>','</mark>','…',24) AS excerpt,bm25(documents) AS score FROM documents WHERE {' AND '.join(where)} ORDER BY score LIMIT ?", values).fetchall()
        return {"results":[dict(row) for row in rows],"elapsed_ms":round((time.perf_counter()-started)*1000,2)}

    def passages(self, session_key: str, query: str, limit: int = 4, max_chapter: int | None = None) -> list[dict]:
        """Full paragraph text for the best matches, never past ``max_chapter``."""
        path = self._path(session_key)
        if not path.exists(): raise LookupError("search index is not ready")
        tokens = re.findall(r"[\w'-]+", query, flags=re.UNICODE)
        if not tokens: return []
        expression = " ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)[:500]
        where = ["documents MATCH ?"]; values: list[object] = [expression]
        if max_chapter is not None: where.append("CAST(chapter_index AS INTEGER)<=?"); values.append(int(max_chapter))
        values.append(max(1,min(20,limit)))
        with closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT chapter_index,chapter_title,paragraph_index,text FROM documents WHERE {' AND '.join(where)} ORDER BY bm25(documents) LIMIT ?", values).fetchall()
        return [dict(row) for row in rows]

    def status(self, session_key: str) -> dict:
        path = self._path(session_key)
        if not path.exists(): return {"ready":False,"schema_version":SEARCH_SCHEMA_VERSION}
        with closing(sqlite3.connect(path)) as conn:
            values = dict(conn.execute("SELECT key,value FROM metadata"))
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
        return {"ready":check == "ok","schema_version":int(values.get("schema_version",0)),"word_count":int(values.get("word_count",0)),"indexed_at":float(values.get("indexed_at",0))}
