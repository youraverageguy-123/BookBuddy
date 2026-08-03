"""Spoiler-safe, chapter-scoped analysis staging for the desktop reader."""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai import AIError
from snapshot_manager import EvidenceStore


TERMINAL_STATES = {"committed", "cancelled", "error"}
ACTIVE_STATES = {"queued", "analyzing", "eligible", "committing", "paused"}
PUBLIC_AI_ERROR_CODES = {
    "invalid_key",
    "network_unavailable",
    "quota_exceeded",
    "region_unsupported",
    "permission_denied",
    "provider_unavailable",
    "unexpected_error",
}


def _public_error_code(error: Exception) -> str:
    if isinstance(error, AIError) and error.code in PUBLIC_AI_ERROR_CODES:
        return error.code
    return "unexpected_error"


@dataclass
class ReaderAnalysisJob:
    session_key: str
    chapter_index: int
    workspace: Path
    state: str = "queued"
    progress: float = 0.0
    log: str = "Queued for spoiler-safe analysis."
    eligible: bool = False
    cancelled: bool = False
    retryable: bool = True
    error_code: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    payload: dict[str, Any] | None = field(default=None, repr=False)
    paused_from: str | None = field(default=None, repr=False)

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            setattr(self, key, value)
        self.updated_at = time.time()

    def public(self) -> dict[str, Any]:
        return {
            "chapter_index": self.chapter_index,
            "state": self.state,
            "progress": round(self.progress, 1),
            "log": self.log,
            "eligible": self.eligible,
            "retryable": self.retryable,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ReaderAnalysisCoordinator:
    """Own temporary extraction and promote only reader-authorized evidence."""

    def __init__(self, cache_root: str | Path, session_manager, parser_service, replay_service, databases):
        self.root = Path(cache_root).resolve() / "reader-analysis"
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_manager = session_manager
        self.parser_service = parser_service
        self.replay_service = replay_service
        self.databases = databases
        self.jobs: dict[tuple[str, int], ReaderAnalysisJob] = {}
        self.tasks: dict[tuple[str, int], asyncio.Task] = {}
        self._job_locks: dict[tuple[str, int], asyncio.Lock] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self.cleanup_abandoned()

    def pause(self) -> int:
        self._resume_event.clear()
        paused = 0
        for job in self.jobs.values():
            if job.state in ACTIVE_STATES and job.state != "paused" and not job.cancelled:
                job.paused_from = job.state
                job.update(state="paused", log="Paused safely; staged work is preserved.")
                paused += 1
        return paused

    def resume(self) -> int:
        resumed = 0
        for job in self.jobs.values():
            if job.state == "paused" and not job.cancelled:
                job.update(state=job.paused_from or "queued", log="Background analysis resumed.")
                job.paused_from = None
                resumed += 1
        self._resume_event.set()
        return resumed

    async def cancel_active(self) -> int:
        cancelled = 0
        for job in list(self.jobs.values()):
            if job.state in ACTIVE_STATES and not job.cancelled:
                await self.cancel(job.session_key, job.chapter_index)
                cancelled += 1
        return cancelled

    async def _wait_if_paused(self, job: ReaderAnalysisJob) -> None:
        if job.cancelled:
            return
        await self._resume_event.wait()

    def cleanup_abandoned(self) -> None:
        for child in self.root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    @staticmethod
    def _key(session_key: str, chapter_index: int) -> tuple[str, int]:
        return session_key, int(chapter_index)

    def _new_job(self, session_key: str, chapter_index: int, *, eligible: bool = False) -> ReaderAnalysisJob:
        workspace = self.root / f"{uuid.uuid4().hex}-{chapter_index}"
        job = ReaderAnalysisJob(session_key, int(chapter_index), workspace, eligible=eligible)
        if eligible:
            job.state = "eligible"
            job.log = "Chapter completed; analysis queued for promotion."
        self.jobs[self._key(session_key, chapter_index)] = job
        return job

    async def stage(self, session_key: str, chapter_index: int, book, canonical_db_dir: str) -> dict:
        key = self._key(session_key, chapter_index)
        job = self.jobs.get(key)
        if job and job.state not in {"cancelled", "error"}:
            return job.public()
        if job:
            await self._remove_workspace(job)
        job = self._new_job(session_key, chapter_index)
        self._submit(key, job, book, canonical_db_dir)
        return job.public()

    async def complete(self, session_key: str, chapter_index: int, book, canonical_db_dir: str) -> dict:
        key = self._key(session_key, chapter_index)
        job = self.jobs.get(key)
        if job and job.state == "committed":
            return job.public()
        if job is None or job.state in {"cancelled", "error"}:
            if job:
                await self._remove_workspace(job)
            job = self._new_job(session_key, chapter_index, eligible=True)
            self._submit(key, job, book, canonical_db_dir)
            return job.public()
        job.update(eligible=True)
        if job.state == "staged":
            await self._promote(job, canonical_db_dir)
        elif job.state not in {"committing", "committed"}:
            job.update(state="eligible", log="Chapter completed; waiting for analysis to finish.")
        return job.public()

    async def cancel(self, session_key: str, chapter_index: int) -> dict:
        key = self._key(session_key, chapter_index)
        job = self.jobs.get(key) or self._new_job(session_key, chapter_index)
        if job.state == "committed":
            return job.public()
        job.update(
            state="cancelled", cancelled=True, eligible=False, progress=0.0,
            log="Unfinished chapter analysis discarded.", retryable=True,
        )
        if key not in self.tasks or self.tasks[key].done():
            await self._remove_workspace(job)
        return job.public()

    def status(self, session_key: str) -> dict:
        jobs = sorted(
            (job.public() for key, job in self.jobs.items() if key[0] == session_key),
            key=lambda item: item["chapter_index"],
        )
        active = [job for job in jobs if job["state"] in ACTIVE_STATES]
        aggregate = round(sum(job["progress"] for job in active) / len(active), 1) if active else 0.0
        return {
            "schema_version": "reader_analysis_v1", "session_key": session_key,
            "state": "active" if active else "idle", "progress": aggregate, "jobs": jobs,
        }

    def _submit(self, key: tuple[str, int], job: ReaderAnalysisJob, book, canonical_db_dir: str) -> None:
        existing = self.tasks.get(key)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._run(job, book, canonical_db_dir), name=f"reader-analysis:{job.session_key}:{job.chapter_index}")
        self.tasks[key] = task

        def finished(done: asyncio.Task) -> None:
            if self.tasks.get(key) is done:
                self.tasks.pop(key, None)
            try:
                done.exception()
            except (asyncio.CancelledError, Exception):
                pass
        task.add_done_callback(finished)

    @staticmethod
    def _clone_graph(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not source.is_file():
            return
        with closing(sqlite3.connect(source)) as source_db, closing(sqlite3.connect(destination)) as destination_db:
            source_db.backup(destination_db)

    async def _run(self, job: ReaderAnalysisJob, book, canonical_db_dir: str) -> None:
        await self._wait_if_paused(job)
        session_lock = self._session_locks.setdefault(job.session_key, asyncio.Lock())
        async with session_lock:
            await self._wait_if_paused(job)
            if job.cancelled:
                await self._remove_workspace(job)
                return
            await self._run_isolated(job, book, canonical_db_dir)

    async def _run_isolated(self, job: ReaderAnalysisJob, book, canonical_db_dir: str) -> None:
        try:
            job.workspace.mkdir(parents=True, exist_ok=True)
            staging_db_dir = job.workspace / "database"
            staging_db_dir.mkdir(parents=True, exist_ok=True)
            job.update(state="analyzing", progress=5.0, log="Preparing isolated chapter workspace.")
            await self._wait_if_paused(job)
            await asyncio.to_thread(self._clone_graph, Path(canonical_db_dir) / "graph.db", staging_db_dir / "graph.db")
            if job.cancelled:
                return
            job.update(progress=15.0, log="Analyzing chapter without changing reader knowledge.")
            await self._wait_if_paused(job)
            staging_db = self.databases.open(str(staging_db_dir))
            try:
                payload = await asyncio.to_thread(
                    self.parser_service.process_chapter,
                    job.chapter_index, book, str(staging_db_dir), staging_db, {},
                    False, True, "reader_staging", False,
                )
            finally:
                staging_db.close()
            await self._wait_if_paused(job)
            if job.cancelled:
                return
            job.payload = payload
            (job.workspace / "staged-payload.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            if job.eligible:
                job.update(state="eligible", progress=85.0, log="Analysis complete; promoting reader-safe evidence.")
                await self._promote(job, canonical_db_dir)
            else:
                job.update(state="staged", progress=100.0, log="Analysis staged until the chapter is completed.")
        except Exception as exc:
            if not job.cancelled:
                job.update(
                    state="error",
                    log="Chapter analysis failed and can be retried.",
                    error_code=_public_error_code(exc),
                    retryable=True,
                )
        finally:
            if job.cancelled:
                await self._remove_workspace(job)

    async def _promote(self, job: ReaderAnalysisJob, canonical_db_dir: str) -> None:
        await self._wait_if_paused(job)
        key = self._key(job.session_key, job.chapter_index)
        lock = self._job_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if job.state == "committed" or job.cancelled or not job.eligible:
                return
            payload = job.payload
            payload_path = job.workspace / "staged-payload.json"
            if payload is None and payload_path.is_file():
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            if payload is None:
                return
            job.update(state="committing", progress=90.0, log="Committing completed chapter evidence.")
            await self._wait_if_paused(job)
            async with self.session_manager.get_lock(job.session_key):
                canonical_db = self.databases.open(canonical_db_dir)
                try:
                    EvidenceStore.record(
                        canonical_db, job.chapter_index, payload,
                        trigger_reason="reader_chapter_completed",
                        source_metadata={"reader_completion_authorized": True},
                    )
                finally:
                    canonical_db.close()
                await asyncio.to_thread(self.replay_service.coordinator(canonical_db_dir).replay, "reader_chapter_completed")
            job.update(state="committed", progress=100.0, log="Completed chapter evidence committed.", retryable=False, error_code=None)
            await self._remove_workspace(job)

    @staticmethod
    async def _remove_workspace(job: ReaderAnalysisJob) -> None:
        if job.workspace.exists():
            await asyncio.to_thread(shutil.rmtree, job.workspace, True)

    async def shutdown(self, timeout: float = 30.0) -> None:
        for job in self.jobs.values():
            if not job.eligible and job.state not in TERMINAL_STATES:
                job.update(state="cancelled", cancelled=True, log="Discarded during backend shutdown.")
        pending = [task for task in self.tasks.values() if not task.done()]
        if pending:
            _, still_pending = await asyncio.wait(pending, timeout=timeout)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)
        for job in self.jobs.values():
            if job.state != "committed":
                await self._remove_workspace(job)
