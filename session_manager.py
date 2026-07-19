import asyncio
import json
import os
import re
import shutil
import sqlite3
import time
from copy import deepcopy

from config import CACHE_VERSION, GRAPH_SCHEMA_VERSION, NORMALIZATION_VERSION, PROMPT_VERSION


def sanitize_session_component(value: str, fallback: str = "Session") -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(value or "")).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    if not cleaned:
        cleaned = fallback
    return cleaned[:80]


class SessionManager:
    def __init__(self, metadata_path: str = "session_state.json"):
        self.sessions = {}
        self.book_locks = {}
        self.analysis_tasks = {}
        self.session_metadata = {}
        self.metadata_path = metadata_path
        self._load_metadata()

    def _load_metadata(self):
        if not os.path.exists(self.metadata_path):
            return
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        self.session_metadata = payload.get("sessions", {})
        self.analysis_tasks = payload.get("analysis_tasks", {})

    def _persist_metadata(self):
        directory = os.path.dirname(os.path.abspath(self.metadata_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "sessions": self.session_metadata,
            "analysis_tasks": self.analysis_tasks,
            "updated_at": time.time(),
        }
        tmp_path = f"{self.metadata_path}.{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.metadata_path)

    def _now(self) -> float:
        return time.time()

    def list_sessions(self, include_deleted: bool = False, validate: bool = True) -> list[dict]:
        sessions = []
        for session_key, metadata in sorted(self.session_metadata.items()):
            item = deepcopy(metadata)
            item.setdefault("session_key", session_key)
            if item.get("is_deleted") and not include_deleted:
                continue
            if validate:
                item["integrity"] = self.validate_session_integrity(session_key)
            sessions.append(item)
        return sessions

    def validate_session_integrity(self, session_key: str) -> dict:
        metadata = self.session_metadata.get(session_key)
        issues = []
        if not metadata:
            return {"status": "missing_metadata", "issues": ["metadata missing"]}

        session_dir = metadata.get("session_dir")
        if not session_dir:
            issues.append("session_dir missing from metadata")
            return {"status": "broken", "issues": issues}

        if not os.path.isdir(session_dir):
            issues.append("session directory missing")
        db_dir = os.path.join(session_dir, "database")
        if not os.path.isdir(db_dir):
            issues.append("database directory missing")
        graph_path = os.path.join(db_dir, "graph.db")
        snapshot_integrity = {"status": "not_initialized", "active_evidence": 0, "completed_checkpoints": 0}
        if not os.path.exists(graph_path):
            issues.append("graph.db missing")
        else:
            try:
                with sqlite3.connect(graph_path) as conn:
                    tables = {
                        row[0]
                        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                    }
                    required = {
                        "chapter_evidence_revisions",
                        "reader_snapshot_current",
                        "chapter_processing_checkpoints",
                        "chapter_invalidations",
                    }
                    if required.issubset(tables):
                        active_evidence = conn.execute(
                            "SELECT COUNT(*) FROM chapter_evidence_revisions WHERE is_active = 1"
                        ).fetchone()[0]
                        completed = conn.execute(
                            "SELECT COUNT(*) FROM chapter_processing_checkpoints WHERE state = 'complete'"
                        ).fetchone()[0]
                        open_invalidations = conn.execute(
                            "SELECT COUNT(*) FROM chapter_invalidations WHERE status = 'open'"
                        ).fetchone()[0]
                        missing_snapshots = conn.execute("""
                            SELECT COUNT(*)
                            FROM chapter_evidence_revisions evidence
                            LEFT JOIN reader_snapshot_current snapshot ON snapshot.chapter = evidence.chapter
                            WHERE evidence.is_active = 1 AND snapshot.chapter IS NULL
                        """).fetchone()[0]
                        snapshot_integrity = {
                            "status": "current" if not open_invalidations and not missing_snapshots else "rebuild_required",
                            "active_evidence": active_evidence,
                            "completed_checkpoints": completed,
                            "open_invalidations": open_invalidations,
                            "missing_snapshots": missing_snapshots,
                        }
                        if open_invalidations or missing_snapshots:
                            issues.append("chapter snapshot replay required")
            except sqlite3.Error as exc:
                snapshot_integrity = {"status": "unreadable", "error": str(exc)}
                issues.append("chapter snapshot metadata unreadable")
        continuity_path = os.path.join(session_dir, "continuity.json")
        if not os.path.exists(continuity_path):
            issues.append("continuity.json missing")

        chapter_files = []
        if os.path.isdir(db_dir):
            chapter_files = [
                name for name in os.listdir(db_dir)
                if name.startswith("chapter_") and name.endswith(".json")
            ]
            stale_cache_files = []
            for name in chapter_files:
                chapter_path = os.path.join(db_dir, name)
                try:
                    with open(chapter_path, "r", encoding="utf-8") as f:
                        chapter_payload = json.load(f)
                except (OSError, json.JSONDecodeError):
                    issues.append(f"chapter cache unreadable: {name}")
                    continue
                metadata_payload = chapter_payload.get("_metadata") or {}
                expected_versions = {
                    "cache_version": CACHE_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "normalization_version": NORMALIZATION_VERSION,
                    "graph_schema_version": GRAPH_SCHEMA_VERSION,
                }
                if any(metadata_payload.get(key) != value for key, value in expected_versions.items()):
                    stale_cache_files.append(name)
            if stale_cache_files:
                issues.append(f"stale chapter cache version: {len(stale_cache_files)} file(s)")
        total_chapters = metadata.get("total_chapters")
        if total_chapters and chapter_files and len(chapter_files) < int(total_chapters):
            issues.append(f"chapter cache incomplete: {len(chapter_files)}/{total_chapters}")

        book_dir = os.path.dirname(session_dir)
        if not os.path.isdir(book_dir):
            issues.append("book directory missing")
        elif not any(name.lower().endswith(".epub") for name in os.listdir(book_dir)):
            issues.append("EPUB file missing")

        if metadata.get("is_deleted"):
            status = "deleted"
        elif issues:
            status = "broken"
        else:
            status = "ok"
        return {
            "status": status,
            "issues": issues,
            "chapter_cache_count": len(chapter_files),
            "snapshot_integrity": snapshot_integrity,
        }

    def register_disk_session(
        self,
        session_key: str,
        book_name: str,
        session_name: str,
        session_dir: str,
        total_chapters: int | None = None,
    ) -> dict:
        metadata = self.session_metadata.setdefault(session_key, {"session_key": session_key})
        metadata.update({
            "book_title": metadata.get("book_title") or book_name.replace("_", " "),
            "book_name": book_name,
            "session_name": session_name,
            "session_dir": session_dir,
            "total_chapters": metadata.get("total_chapters", total_chapters),
            "is_deleted": bool(metadata.get("is_deleted", False)),
            "discovered_on_disk_at": metadata.get("discovered_on_disk_at") or self._now(),
            "updated_at": self._now(),
        })
        self._persist_metadata()
        return deepcopy(metadata)

    def rename_session(self, session_key: str, label: str) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        label = " ".join(str(label or "").split())
        if not label:
            raise ValueError("label must not be empty")
        metadata = self.session_metadata[session_key]
        metadata["label"] = label
        metadata["session_name_quality"] = "human_label"
        metadata["updated_at"] = self._now()
        self._persist_metadata()
        return deepcopy(metadata)

    def soft_delete_session(self, session_key: str) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        metadata = self.session_metadata[session_key]
        metadata["is_deleted"] = True
        metadata["deleted_at"] = self._now()
        metadata["updated_at"] = self._now()
        self.sessions.pop(session_key, None)
        self.analysis_tasks.pop(session_key, None)
        self._persist_metadata()
        return deepcopy(metadata)

    def restore_session(self, session_key: str) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        metadata = self.session_metadata[session_key]
        metadata["is_deleted"] = False
        metadata["deleted_at"] = None
        metadata["updated_at"] = self._now()
        self._persist_metadata()
        return deepcopy(metadata)

    def hard_delete_session(self, session_key: str, library_root: str, dry_run: bool = True) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        metadata = self.session_metadata[session_key]
        session_dir = metadata.get("session_dir")
        if not session_dir:
            raise ValueError("session_dir missing from metadata")

        library_root_abs = os.path.abspath(library_root)
        session_dir_abs = os.path.abspath(session_dir)
        if not os.path.commonpath([library_root_abs, session_dir_abs]) == library_root_abs:
            raise ValueError("session_dir is outside library root")

        plan = {
            "session_key": session_key,
            "session_dir": session_dir_abs,
            "dry_run": dry_run,
            "would_delete": os.path.isdir(session_dir_abs),
        }
        if dry_run:
            return plan

        if os.path.isdir(session_dir_abs):
            shutil.rmtree(session_dir_abs)
        self.sessions.pop(session_key, None)
        self.analysis_tasks.pop(session_key, None)
        self.session_metadata.pop(session_key, None)
        self._persist_metadata()
        plan["deleted"] = True
        return plan

    def purge_deleted_sessions(self, library_root: str, older_than_seconds: float = 0, dry_run: bool = True) -> dict:
        cutoff = self._now() - max(0.0, float(older_than_seconds or 0))
        purged = []
        for session_key, metadata in list(self.session_metadata.items()):
            if not metadata.get("is_deleted"):
                continue
            deleted_at = metadata.get("deleted_at") or 0
            if deleted_at > cutoff:
                continue
            purged.append(self.hard_delete_session(session_key, library_root, dry_run=dry_run))
        return {"dry_run": dry_run, "count": len(purged), "sessions": purged}

    def set_book(self, session_key: str, book, session_dir: str | None = None):
        self.sessions[session_key] = book
        self.book_locks.setdefault(session_key, asyncio.Lock())
        self.session_metadata[session_key] = {
            **self.session_metadata.get(session_key, {}),
            "session_key": session_key,
            "book_title": getattr(book, "title", None),
            "book_name": self.session_metadata.get(session_key, {}).get("book_name"),
            "session_name": self.session_metadata.get(session_key, {}).get("session_name"),
            "total_chapters": getattr(book, "total_chapters", None),
            "session_dir": session_dir,
            "internal_session_id": session_key,
            "is_deleted": False,
            "deleted_at": None,
            "loaded_at": time.time(),
        }
        self._persist_metadata()

    def get_book(self, session_key: str):
        return self.sessions.get(session_key)

    def get_session_metadata(self, session_key: str, default: dict | None = None) -> dict:
        if session_key not in self.session_metadata:
            return deepcopy(default) if default is not None else {}
        return deepcopy(self.session_metadata[session_key])

    def update_session_metadata(self, session_key: str, **updates):
        self.session_metadata.setdefault(session_key, {"session_key": session_key})
        self.session_metadata[session_key].update(updates)
        self.session_metadata[session_key]["updated_at"] = time.time()
        self._persist_metadata()

    def get_lock(self, session_key: str):
        self.book_locks.setdefault(session_key, asyncio.Lock())
        return self.book_locks[session_key]

    def get_task(self, session_key: str, default: dict | None = None) -> dict:
        if session_key not in self.analysis_tasks:
            return deepcopy(default) if default is not None else {}
        return deepcopy(self.analysis_tasks[session_key])

    def set_task(self, session_key: str, state: dict):
        self.analysis_tasks[session_key] = {
            **state,
            "updated_at": time.time(),
        }
        self._persist_metadata()

    def update_task(self, session_key: str, **updates):
        self.analysis_tasks.setdefault(session_key, {})
        self.analysis_tasks[session_key].update(updates)
        self.analysis_tasks[session_key]["updated_at"] = time.time()
        if "current_chapter" in updates:
            self.session_metadata.setdefault(session_key, {"session_key": session_key})
            self.session_metadata[session_key]["last_analyzed_chapter"] = updates["current_chapter"]
        if "last_analyzed_chapter" in updates:
            self.session_metadata.setdefault(session_key, {"session_key": session_key})
            self.session_metadata[session_key]["last_analyzed_chapter"] = updates["last_analyzed_chapter"]
        if "last_successful_graph_version" in updates:
            self.session_metadata.setdefault(session_key, {"session_key": session_key})
            self.session_metadata[session_key]["last_successful_graph_version"] = updates["last_successful_graph_version"]
        if updates.get("status") in {"completed", "cancelled", "error"}:
            self.session_metadata.setdefault(session_key, {"session_key": session_key})
            self.session_metadata[session_key]["last_task_status"] = updates["status"]
        self._persist_metadata()

    def request_cancel(self, session_key: str) -> bool:
        task = self.analysis_tasks.get(session_key)
        if not task or task.get("status") != "processing":
            return False
        task["cancel_requested"] = True
        task["log"] = "Cancellation requested. Waiting for current chapter to finish."
        task["updated_at"] = time.time()
        self._persist_metadata()
        return True

    def cancel_requested(self, session_key: str) -> bool:
        return bool(self.analysis_tasks.get(session_key, {}).get("cancel_requested"))
