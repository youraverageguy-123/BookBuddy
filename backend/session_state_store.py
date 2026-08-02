"""Crash-safe, process-coordinated persistence for session metadata."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Iterator


class SessionStateStore:
    """Serialize state snapshots with thread and interprocess locking."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).resolve()
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self._lock = threading.RLock()

    @contextmanager
    def _interprocess_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> dict:
        if not self.path.is_file():
            return {"sessions": {}, "analysis_tasks": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Session state is unreadable: {self.path}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Session state root must be an object: {self.path}")
        sessions = payload.get("sessions", {})
        tasks = payload.get("analysis_tasks", {})
        if not isinstance(sessions, dict) or not isinstance(tasks, dict):
            raise RuntimeError(f"Session state collections are invalid: {self.path}")
        return payload

    def read(self) -> dict:
        with self._lock, self._interprocess_lock():
            return deepcopy(self._read_unlocked())

    def _write_unlocked(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            if os.name != "nt":
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def write(self, payload: dict) -> None:
        with self._lock, self._interprocess_lock():
            self._write_unlocked(deepcopy(payload))

    @contextmanager
    def transaction(self) -> Iterator[dict]:
        """Reload, mutate, and replace one snapshot under a single process lock."""

        with self._lock, self._interprocess_lock():
            payload = self._read_unlocked()
            yield payload
            self._write_unlocked(payload)
