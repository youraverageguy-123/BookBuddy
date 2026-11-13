import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps

from config import CACHE_VERSION, GRAPH_SCHEMA_VERSION, NORMALIZATION_VERSION, PROMPT_VERSION
from session_state_store import SessionStateStore


def sanitize_session_component(value: str, fallback: str = "Session") -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(value or "")).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    if not cleaned:
        cleaned = fallback
    return cleaned[:80]


def _state_mutation(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._state_transaction():
            return method(self, *args, **kwargs)

    return guarded


class SessionManager:
    def __init__(self, metadata_path: str = "session_state.json"):
        self.sessions = {}
        self.book_locks = {}
        self.analysis_tasks = {}
        self.session_metadata = {}
        self.metadata_path = metadata_path
        self._state_lock = threading.RLock()
        self._mutation_depth = 0
        self._state_store = SessionStateStore(metadata_path)
        self._load_metadata()
        self.recover_interrupted_tasks()

    @_state_mutation
    def recover_interrupted_tasks(self) -> int:
        """Close out runs that were in progress when the previous process ended.

        Analysis runs inside the backend process, so a task still marked as
        running at startup can never finish and would look active forever.
        """
        recovered = 0
        for task in self.analysis_tasks.values():
            if task.get("status") in {"processing", "cancelling"}:
                stopped = bool(task.get("cancel_requested"))
                task.update(
                    status="cancelled" if stopped else "error",
                    cancel_requested=False,
                    log="Analysis was stopped." if stopped else "Analysis was interrupted when BookBuddy closed.",
                    updated_at=time.time(),
                )
                recovered += 1
        if recovered:
            self._persist_metadata()
        return recovered

    def _load_metadata(self):
        with self._state_lock:
            payload = self._state_store.read()
            self.session_metadata = payload.get("sessions", {})
            self.analysis_tasks = payload.get("analysis_tasks", {})

    @contextmanager
    def _state_transaction(self):
        with self._state_lock:
            if self._mutation_depth:
                self._mutation_depth += 1
                try:
                    yield
                finally:
                    self._mutation_depth -= 1
                return
            with self._state_store.transaction() as payload:
                self.session_metadata = payload.setdefault("sessions", {})
                self.analysis_tasks = payload.setdefault("analysis_tasks", {})
                self._mutation_depth = 1
                try:
                    yield
                finally:
                    payload["sessions"] = deepcopy(self.session_metadata)
                    payload["analysis_tasks"] = deepcopy(self.analysis_tasks)
                    payload["updated_at"] = time.time()
                    self._mutation_depth = 0

    def _persist_metadata(self):
        with self._state_lock:
            if self._mutation_depth:
                return
            self._state_store.write({
                "sessions": deepcopy(self.session_metadata),
                "analysis_tasks": deepcopy(self.analysis_tasks),
                "updated_at": time.time(),
            })

    def flush(self) -> None:
        """Persist current session and task state during graceful shutdown."""
        self._persist_metadata()

    def _now(self) -> float:
        return time.time()

    def list_sessions(self, include_deleted: bool = False, validate: bool = True) -> list[dict]:
        # Several packaged processes can briefly overlap during upgrades or
        # crash recovery. Always read the last committed snapshot before a
        # public listing so one process cannot serve stale deletion metadata.
        self._load_metadata()
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
        analysis_issues = []
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
            analysis_issues.append("database directory not initialized")
        graph_path = os.path.join(db_dir, "graph.db")
        snapshot_integrity = {"status": "not_initialized", "active_evidence": 0, "completed_checkpoints": 0}
        if not os.path.exists(graph_path):
            analysis_issues.append("analysis graph not initialized")
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
                            analysis_issues.append("chapter snapshot replay required")
            except sqlite3.Error as exc:
                snapshot_integrity = {"status": "unreadable", "error": str(exc)}
                analysis_issues.append("chapter snapshot metadata unreadable")
        continuity_path = os.path.join(session_dir, "continuity.json")
        if not os.path.exists(continuity_path):
            analysis_issues.append("analysis continuity not initialized")

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
                    analysis_issues.append(f"chapter cache unreadable: {name}")
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
                analysis_issues.append(f"stale chapter cache version: {len(stale_cache_files)} file(s)")
        total_chapters = metadata.get("total_chapters")
        if total_chapters and chapter_files and len(chapter_files) < int(total_chapters):
            analysis_issues.append(f"chapter cache incomplete: {len(chapter_files)}/{total_chapters}")

        source_relpath = metadata.get("source_epub_relpath")
        if source_relpath:
            source_parts = str(source_relpath).replace("\\", "/").split("/")
            source_path = os.path.abspath(os.path.join(session_dir, *source_parts))
            if (
                any(part in {"", ".", ".."} for part in source_parts)
                or os.path.commonpath([os.path.abspath(session_dir), source_path]) != os.path.abspath(session_dir)
                or self._is_reparse_point(source_path)
            ):
                issues.append("session EPUB source identity is invalid")
            elif not os.path.isfile(source_path):
                issues.append("session EPUB source is missing")
            else:
                expected_size = metadata.get("source_size_bytes")
                if expected_size is not None and os.path.getsize(source_path) != int(expected_size):
                    issues.append("session EPUB source size mismatch")
                expected_hash = str(metadata.get("source_sha256") or "")
                if expected_hash:
                    digest = hashlib.sha256()
                    with open(source_path, "rb") as source_file:
                        for block in iter(lambda: source_file.read(1024 * 1024), b""):
                            digest.update(block)
                    if digest.hexdigest() != expected_hash:
                        issues.append("session EPUB source hash mismatch")
        else:
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
            "analysis_issues": analysis_issues,
            "chapter_cache_count": len(chapter_files),
            "snapshot_integrity": snapshot_integrity,
        }

    @_state_mutation
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

    @_state_mutation
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

    @_state_mutation
    def soft_delete_session(self, session_key: str) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        metadata = self.session_metadata[session_key]
        metadata["is_deleted"] = True
        metadata["deleted_at"] = self._now()
        metadata["updated_at"] = self._now()
        # Soft deletion keeps the source EPUB and its parsed reader payload
        # available during the Undo window. The public library listing is
        # controlled by is_deleted, while local dictionary/selection services
        # can continue to resolve an already-open reader without re-importing.
        self.analysis_tasks.pop(session_key, None)
        self._persist_metadata()
        return deepcopy(metadata)

    @_state_mutation
    def restore_session(self, session_key: str) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        metadata = self.session_metadata[session_key]
        metadata["is_deleted"] = False
        metadata["deleted_at"] = None
        metadata["updated_at"] = self._now()
        self._persist_metadata()
        return deepcopy(metadata)

    @_state_mutation
    def hard_delete_session(self, session_key: str, library_root: str, dry_run: bool = True) -> dict:
        if session_key not in self.session_metadata:
            raise KeyError(session_key)
        metadata = self.session_metadata[session_key]
        book_name, separator, session_name = session_key.partition("::")
        if not separator or not book_name or not session_name:
            raise ValueError("session identity is invalid")
        if metadata.get("book_name") not in {None, book_name} or metadata.get("session_name") not in {None, session_name}:
            raise ValueError("session metadata identity does not match its key")

        library_root_path = os.path.realpath(os.path.abspath(library_root))
        session_dir_abs = os.path.abspath(os.path.join(library_root_path, book_name, session_name))
        if os.path.commonpath([library_root_path, session_dir_abs]) != library_root_path:
            raise ValueError("session identity resolves outside library root")
        expected_leaf = os.path.basename(session_dir_abs)
        expected_parent = os.path.basename(os.path.dirname(session_dir_abs))
        if expected_leaf != session_name or expected_parent != book_name:
            raise ValueError("session directory identity mismatch")
        current = os.path.dirname(session_dir_abs)
        for candidate in (current, session_dir_abs):
            if os.path.lexists(candidate) and self._is_reparse_point(candidate):
                raise ValueError("session deletion does not follow links or reparse points")

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

    @staticmethod
    def _is_reparse_point(path: str) -> bool:
        if os.path.islink(path):
            return True
        try:
            attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        except OSError:
            return False
        return bool(attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

    @_state_mutation
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

    @_state_mutation
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

    @_state_mutation
    def register_imported_book(self, session_key: str, book, session_dir: str, metadata: dict) -> dict:
        current = self.session_metadata.get(session_key, {})
        revision = max(int(current.get("metadata_revision", 0) or 0) + 1, int(metadata.get("metadata_revision", 1) or 1))
        self.sessions[session_key] = book
        self.book_locks.setdefault(session_key, asyncio.Lock())
        self.session_metadata[session_key] = {
            **current,
            **metadata,
            "session_key": session_key,
            "session_dir": session_dir,
            "internal_session_id": session_key,
            "book_title": getattr(book, "title", None),
            "total_chapters": getattr(book, "total_chapters", None),
            "is_deleted": False,
            "deleted_at": None,
            "metadata_revision": revision,
            "loaded_at": time.time(),
            "updated_at": time.time(),
        }
        self._persist_metadata()
        return deepcopy(self.session_metadata[session_key])

    def get_book(self, session_key: str):
        return self.sessions.get(session_key)

    def get_session_metadata(self, session_key: str, default: dict | None = None) -> dict:
        if session_key not in self.session_metadata:
            return deepcopy(default) if default is not None else {}
        return deepcopy(self.session_metadata[session_key])

    @_state_mutation
    def update_session_metadata(self, session_key: str, **updates):
        self.session_metadata.setdefault(session_key, {"session_key": session_key})
        self.session_metadata[session_key].update(updates)
        self.session_metadata[session_key]["updated_at"] = time.time()
        self._persist_metadata()

    def get_lock(self, session_key: str):
        with self._state_lock:
            self.book_locks.setdefault(session_key, asyncio.Lock())
            return self.book_locks[session_key]

    def get_task(self, session_key: str, default: dict | None = None) -> dict:
        if session_key not in self.analysis_tasks:
            return deepcopy(default) if default is not None else {}
        return deepcopy(self.analysis_tasks[session_key])

    @_state_mutation
    def set_task(self, session_key: str, state: dict):
        self.analysis_tasks[session_key] = {
            **state,
            "updated_at": time.time(),
        }
        self._persist_metadata()

    @_state_mutation
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

    @_state_mutation
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
