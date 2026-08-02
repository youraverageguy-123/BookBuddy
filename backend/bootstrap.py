"""BookBuddy application composition root and lifecycle resources."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Coroutine, Any, Callable
import weakref

from ai import AIManager, GenerationRequest, create_ai_manager
from config import AppConfig
from dictionary_subsystem.context import WordNetContextResolver
from dictionary_subsystem.linguistics import LinguisticAnalyzer
from dictionary_subsystem.providers import EnglishWordNetProvider, OfflinePronunciationProvider
from dictionary_subsystem.reader_state import ReaderKnowledgeStore
from reader_analysis import ReaderAnalysisCoordinator
from session_manager import SessionManager
from task_manager import PersistentTaskManager
from reader_search import ReaderSearchService
from database_maintenance import DatabaseMaintenanceService
from resource_manager import ResourceManager


class DatabaseRegistry:
    """Factory and shutdown registry for session-scoped SQLite databases."""

    def __init__(self):
        self._databases = weakref.WeakSet()

    def open(self, db_dir: str):
        from db_manager import BookDatabase

        database = BookDatabase(db_dir)
        self._databases.add(database)
        return database

    def close_all(self) -> None:
        for database in tuple(self._databases):
            try:
                database.close()
            finally:
                self._databases.discard(database)


class ParserService:
    def __init__(self, ai_manager: AIManager):
        self.ai_manager = ai_manager

    def process_chapter(self, *args, **kwargs):
        from analysis_engine import process_single_chapter

        return process_single_chapter(self.ai_manager, *args, **kwargs)


class ReplayService:
    @staticmethod
    def coordinator(db_dir: str):
        from snapshot_manager import ReplayCoordinator

        return ReplayCoordinator(db_dir)


class TaskSupervisor:
    """Own background jobs so application shutdown can drain them."""

    def __init__(self, session_manager: SessionManager, shutdown_timeout: float, persistent: PersistentTaskManager | None = None):
        self.session_manager = session_manager
        self.shutdown_timeout = shutdown_timeout
        self._tasks: dict[str, asyncio.Task] = {}
        self._accepting = True
        self.persistent = persistent
        self._persistent_ids: dict[str, str] = {}
        self._session_by_task_id: dict[str, str] = {}
        self._retry_factories: dict[str, tuple[str, str, Callable[[], Coroutine[Any, Any, Any]]]] = {}

    def submit(
        self,
        session_key: str,
        coroutine: Coroutine[Any, Any, Any],
        task_type: str = "analysis",
        retry_factory: Callable[[], Coroutine[Any, Any, Any]] | None = None,
    ) -> asyncio.Task:
        if not self._accepting:
            coroutine.close()
            raise RuntimeError("Application is shutting down")
        existing = self._tasks.get(session_key)
        if existing is not None and not existing.done():
            coroutine.close()
            return existing
        task_id = None
        if self.persistent is not None:
            record = self.persistent.enqueue(task_type, f"{task_type}:{session_key}", session_key=session_key)
            task_id = record["task_id"]
            if retry_factory is not None:
                self._retry_factories[task_id] = (session_key, task_type, retry_factory)
        return self._start(session_key, coroutine, task_id)

    def _start(self, session_key: str, coroutine: Coroutine[Any, Any, Any], task_id: str | None) -> asyncio.Task:
        if task_id and self.persistent is not None:
            self._persistent_ids[session_key] = task_id
            self._session_by_task_id[task_id] = session_key

        async def managed() -> Any:
            if task_id and self.persistent is not None:
                if self.persistent.cancel_requested(task_id):
                    coroutine.close()
                    self.persistent.acknowledge_cancel(task_id)
                    raise asyncio.CancelledError
                self.persistent.update(
                    task_id,
                    state="running",
                    stage="executing",
                    progress=1,
                    user_message="Task is running",
                    lease_seconds=max(30, self.shutdown_timeout * 2),
                    lease_owner=f"process:{__import__('os').getpid()}",
                )
            return await coroutine

        task = asyncio.create_task(managed(), name=f"bookbuddy:{session_key}")
        self._tasks[session_key] = task

        def discard(completed: asyncio.Task) -> None:
            # A retry may replace a finished task before its done callback gets
            # a turn on the event loop.  Only the current task owns the session
            # mapping and may finalize the persistent row; an older callback
            # must never overwrite the newer attempt's state.
            is_current = self._tasks.get(session_key) is completed
            if not is_current:
                # Retrieve an orphaned exception before returning so replacing
                # a task cannot produce an unhandled-task warning.
                if not completed.cancelled():
                    completed.exception()
                return
            self._tasks.pop(session_key, None)
            completed_task_id = self._persistent_ids.pop(session_key, None)
            if completed_task_id:
                self._session_by_task_id.pop(completed_task_id, None)
            try:
                cancelled = completed.cancelled()
                error = None if cancelled else completed.exception()
                if completed_task_id and self.persistent is not None:
                    record = self.persistent.get(completed_task_id)
                    # A cooperative checkpoint acknowledges cancellation.  A
                    # request that arrives after successful work has finished
                    # must not turn that successful attempt into "cancelled".
                    cancellation_won = cancelled or (
                        record["cancel_requested"] and record["cancel_acknowledged"]
                    )
                    if cancellation_won:
                        self.persistent.mark_cancelled(completed_task_id)
                        self.session_manager.update_task(session_key, status="cancelled", log="Cancelled safely.")
                    else:
                        self.persistent.update(
                            completed_task_id,
                            state="failed" if error else "succeeded",
                            progress=100 if not error else None,
                            diagnostic_code=type(error).__name__ if error else None,
                            user_message="Task failed and can be retried" if error else "Completed",
                        )
                if completed_task_id and error is None and not cancelled:
                    self._retry_factories.pop(completed_task_id, None)
            except asyncio.CancelledError:
                if completed_task_id and self.persistent is not None:
                    self.persistent.mark_cancelled(completed_task_id)
                    self.session_manager.update_task(session_key, status="cancelled", log="Cancelled safely.")
            except Exception as exc:
                if completed_task_id and self.persistent is not None:
                    self.persistent.update(
                        completed_task_id,
                        state="failed",
                        diagnostic_code=type(exc).__name__,
                        user_message="Task failed and can be retried",
                    )

        task.add_done_callback(discard)
        return task

    def task_id_for_session(self, session_key: str) -> str | None:
        task_id = self._persistent_ids.get(session_key)
        if task_id:
            return task_id
        if self.persistent is None:
            return None
        record = self.persistent.active_for_session(session_key)
        return str(record["task_id"]) if record else None

    def request_cancel(self, *, task_id: str | None = None, session_key: str | None = None) -> dict:
        if self.persistent is None:
            raise LookupError("persistent task cancellation is unavailable")
        resolved_task_id = task_id or (self.task_id_for_session(session_key or ""))
        if not resolved_task_id:
            raise LookupError("active task not found")
        record = self.persistent.request_cancel(resolved_task_id)
        resolved_session = str(record.get("session_key") or session_key or "")
        if resolved_session:
            self.session_manager.request_cancel(resolved_session)
        return record

    def cancel_requested(self, session_key: str) -> bool:
        if self.persistent is None:
            return self.session_manager.cancel_requested(session_key)
        task_id = self.task_id_for_session(session_key)
        return bool(task_id and self.persistent.cancel_requested(task_id))

    def cancellation_checkpoint(self, session_key: str, stage: str) -> None:
        if not self.cancel_requested(session_key):
            return
        task_id = self.task_id_for_session(session_key)
        if task_id and self.persistent is not None:
            self.persistent.update(task_id, stage=stage, cancel_acknowledged=True, user_message="Cancellation acknowledged; stopping safely")
        self.session_manager.update_task(session_key, status="cancelling", log="Cancellation acknowledged; stopping safely.")
        raise asyncio.CancelledError

    def retry(self, task_id: str) -> dict:
        if self.persistent is None:
            raise ValueError("persistent task retries are unavailable")
        retry = self._retry_factories.get(task_id)
        if retry is None:
            self.persistent.get(task_id)
            raise ValueError("This task cannot be reconstructed after restart; run the original action again")
        session_key, _task_type, factory = retry
        existing = self._tasks.get(session_key)
        if existing is not None and not existing.done():
            raise ValueError("A task is already running for this session")
        coroutine = factory()
        try:
            self.persistent.retry(task_id)
            # The retry is accepted synchronously.  This keeps the API's
            # response deterministic even though the managed coroutine starts
            # on the next event-loop turn and will refresh the lease again.
            self.persistent.update(
                task_id,
                state="running",
                stage="executing",
                progress=1,
                user_message="Task is running",
                lease_seconds=max(30, self.shutdown_timeout * 2),
                lease_owner=f"process:{__import__('os').getpid()}",
            )
            self._start(session_key, coroutine, task_id)
        except Exception:
            coroutine.close()
            raise
        return self.persistent.get(task_id)

    async def shutdown(self) -> None:
        self._accepting = False
        tasks = [task for task in self._tasks.values() if not task.done()]
        for session_key in list(self._tasks):
            task_id = self._persistent_ids.get(session_key)
            try:
                self.request_cancel(task_id=task_id, session_key=session_key)
            except LookupError:
                self.session_manager.request_cancel(session_key)
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=self.shutdown_timeout)
            for task in pending:
                name = task.get_name()
                session_key = name.split("bookbuddy:", 1)[-1]
                self.session_manager.update_task(
                    session_key,
                    status="cancelling",
                    log="Stopping during backend shutdown.",
                )
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        self.session_manager.flush()


@dataclass(frozen=True)
class AppServices:
    config: AppConfig
    ai_manager: AIManager
    session_manager: SessionManager
    dictionary_provider: EnglishWordNetProvider
    pronunciation_provider: OfflinePronunciationProvider
    reader_knowledge_store: ReaderKnowledgeStore
    context_resolver: WordNetContextResolver
    task_supervisor: TaskSupervisor
    task_manager: PersistentTaskManager
    search: ReaderSearchService
    maintenance: DatabaseMaintenanceService
    resources: ResourceManager
    databases: DatabaseRegistry
    parser_service: ParserService
    replay_service: ReplayService
    reader_analysis: ReaderAnalysisCoordinator

    async def shutdown(self) -> None:
        await self.reader_analysis.shutdown(self.config.server.shutdown_timeout_seconds)
        await self.task_supervisor.shutdown()
        self.databases.close_all()
        self.ai_manager.close()


def bootstrap_application(config: AppConfig) -> AppServices:
    """Create long-lived services without parsing books or issuing AI calls."""
    logger = logging.getLogger(__name__)
    logger.info("Initializing application services")
    for directory in (config.paths.library_dir, config.paths.cache_dir, config.paths.log_dir):
        Path(directory).mkdir(parents=True, exist_ok=True)

    session_manager = SessionManager(str(config.paths.library_dir / "session_state.json"))
    ai_manager = create_ai_manager(config)
    dictionary_provider = EnglishWordNetProvider()
    pronunciation_provider = OfflinePronunciationProvider(
        str(config.paths.pronunciation_corpus_root or ""),
        str(config.paths.pronunciation_corpus_index or ""),
    )
    try:
        LinguisticAnalyzer.warmup()
        dictionary_provider.lookup("book", "en", "noun")
        pronunciation_provider.lookup("book", "en")
        logger.info("Local dictionary models ready")
    except Exception as exc:
        logger.warning("Local dictionary warmup degraded: %s", type(exc).__name__)
    reader_store = ReaderKnowledgeStore(str(config.paths.reader_state_path))

    def dictionary_ai_fallback(term: str, sentence: str) -> str | None:
        if not ai_manager.is_available("text"):
            return None
        result = ai_manager.generate(GenerationRequest(
            role="dictionary",
            prompt=(
                "Explain only the selected word inside the supplied sentence. "
                "Do not explain the sentence or invent story facts. Return one concise meaning.\n"
                f"Selected word: {term}\nSentence: {sentence}"
            ),
            temperature=0.0,
        ))
        return result.text[:400].strip() or None

    context_resolver = WordNetContextResolver(dictionary_provider, dictionary_ai_fallback)
    persistent_tasks = PersistentTaskManager(str(config.paths.reader_state_path.parent / "tasks.db"))
    supervisor = TaskSupervisor(session_manager, config.server.shutdown_timeout_seconds, persistent_tasks)
    search = ReaderSearchService(str(config.paths.cache_dir))
    maintenance = DatabaseMaintenanceService(str(config.paths.cache_dir),{"reader":config.paths.reader_state_path,"tasks":config.paths.reader_state_path.parent/"tasks.db"})
    resources = ResourceManager(str(config.paths.cache_dir))
    for namespace in ("images","covers","dictionary","web","search"):
        resources.prune(namespace)
    databases = DatabaseRegistry()
    parser_service = ParserService(ai_manager)
    replay_service = ReplayService()
    reader_analysis = ReaderAnalysisCoordinator(
        config.paths.cache_dir,
        session_manager,
        parser_service,
        replay_service,
        databases,
    )
    return AppServices(
        config=config,
        ai_manager=ai_manager,
        session_manager=session_manager,
        dictionary_provider=dictionary_provider,
        pronunciation_provider=pronunciation_provider,
        reader_knowledge_store=reader_store,
        context_resolver=context_resolver,
        task_supervisor=supervisor,
        task_manager=persistent_tasks,
        search=search,
        maintenance=maintenance,
        resources=resources,
        databases=databases,
        parser_service=parser_service,
        replay_service=replay_service,
        reader_analysis=reader_analysis,
    )
