from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from database_maintenance import DatabaseMaintenanceService
from dictionary_subsystem.reader_state import ReaderKnowledgeStore
from performance_audit import MEMORY_BUDGETS_MB, TIME_BUDGETS_MS, evaluate
from reader_search import ReaderSearchService
from resource_manager import ResourceManager
from task_manager import PersistentTaskManager
from bootstrap import DatabaseRegistry, TaskSupervisor
from storage_security import validate_epub_archive
from log_manager import RedactionFilter, configure_file_logging
from epub_compatibility_fixtures import build_compatibility_fixtures
from epub_parser import parse_epub


class ReaderStateV5BackendTests(unittest.TestCase):
    def test_annotations_bookmarks_and_local_telemetry_are_profile_scoped(self):
        with tempfile.TemporaryDirectory() as root:
            store = ReaderKnowledgeStore(str(Path(root, "reader.db")))
            user_id = store.create_profile()
            other_user_id = store.create_profile()
            bookmark = store.create_bookmark(user_id, "Book::Reading", 2, "epubcfi(/6/8)", "Quote", "Turning point")
            self.assertEqual("Turning point", store.update_bookmark(user_id, bookmark["bookmark_id"], "Turning point")["name"])
            annotation = store.create_annotation(user_id, "Book::Reading", 2, "epubcfi(/6/8!/4/2,/1:0,/1:5)", "Quote", "note", note_text="Remember")
            self.assertEqual([annotation["annotation_id"]], [item["annotation_id"] for item in store.list_annotations(user_id, query="Remember")])
            self.assertEqual([], store.list_annotations(other_user_id))
            now = time.time()
            recorded = store.record_reading_session(user_id, "Book::Reading", now - 120, now, 90, 0.2, 0.3)
            self.assertEqual(90, recorded["active_seconds"])
            statistics = store.reading_statistics(user_id)
            self.assertEqual(90, statistics["active_seconds"])
            self.assertFalse(statistics["per_book"]["Book::Reading"]["sufficient_data"])
            self.assertGreater(statistics["per_book"]["Book::Reading"]["seconds_per_book"], 0)
            exported = store.export_reading_sessions(user_id)
            self.assertEqual([recorded["reading_session_id"]], [item["reading_session_id"] for item in exported])
            self.assertNotIn("quote", exported[0])
            self.assertEqual(1, store.reset_reading_sessions(user_id))
            self.assertEqual(0, store.reading_statistics(user_id)["session_count"])


class PersistentTaskTests(unittest.TestCase):
    def test_idempotency_retry_and_stale_lease_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "tasks.db")
            manager = PersistentTaskManager(str(path))
            first = manager.enqueue("analysis", "stable-key", session_key="Book::Reading")
            duplicate = manager.enqueue("analysis", "stable-key", session_key="Book::Reading")
            self.assertEqual(first["task_id"], duplicate["task_id"])
            manager.update(first["task_id"], state="failed", diagnostic_code="worker_exit")
            retried = manager.retry(first["task_id"])
            self.assertEqual(("queued", 1), (retried["state"], retried["retry_count"]))
            manager.update(first["task_id"], state="running", lease_seconds=1)
            recovered = PersistentTaskManager(str(path)).list()[0]
            self.assertEqual("failed", recovered["state"])
            self.assertEqual("restart_interrupted", recovered["diagnostic_code"])
            self.assertIn("original action", recovered["user_message"])

    def test_supervisor_retry_executes_the_original_operation(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as root:
                manager = PersistentTaskManager(str(Path(root, "tasks.db")))
                supervisor = TaskSupervisor(SimpleNamespace(request_cancel=lambda _key: False, flush=lambda: None, update_task=lambda *_args, **_kwargs: None), 1, manager)
                attempts = []

                async def operation():
                    attempts.append(len(attempts) + 1)
                    if len(attempts) == 1:
                        raise RuntimeError("first attempt fails")

                task = supervisor.submit("Book::Reading", operation(), retry_factory=operation)
                await asyncio.gather(task, return_exceptions=True)
                failed = manager.list()[0]
                self.assertEqual("failed", failed["state"])
                retried = supervisor.retry(failed["task_id"])
                self.assertEqual("running", retried["state"])
                await asyncio.gather(*supervisor._tasks.values(), return_exceptions=True)
                self.assertEqual([1, 2], attempts)
                self.assertEqual("succeeded", manager.get(failed["task_id"])["state"])

        asyncio.run(exercise())

    def test_database_registry_does_not_retain_closed_callers(self):
        import gc
        import weakref

        with tempfile.TemporaryDirectory() as root:
            registry = DatabaseRegistry()
            database = registry.open(root)
            reference = weakref.ref(database)
            database.close()
            del database
            gc.collect()
            self.assertIsNone(reference())
            self.assertEqual(0, len(registry._databases))


class SearchAndResourceTests(unittest.TestCase):
    def test_search_quotes_user_input_scopes_results_and_releases_windows_handles(self):
        with tempfile.TemporaryDirectory() as root:
            service = ReaderSearchService(root)
            book = SimpleNamespace(chapters=[
                SimpleNamespace(index=0, title="One", content="Alpha beta. Gamma delta.", spine_href="one.xhtml"),
                SimpleNamespace(index=1, title="Two", content="Don't panic. Alpha returns.", spine_href="two.xhtml"),
            ])
            indexed = service.index_book("Book::Reading", book)
            self.assertGreaterEqual(indexed["documents"], 2)
            self.assertEqual(1, len(service.search("Book::Reading", "don't")["results"]))
            punctuation_results = service.search("Book::Reading", "alpha - beta", max_chapter=0)["results"]
            self.assertTrue(punctuation_results)
            self.assertTrue(all(item["chapter_index"] == 0 for item in punctuation_results))
            self.assertTrue(service.status("Book::Reading")["ready"])

    def test_svg_covers_are_hashed_sanitized_and_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            manager = ResourceManager(root)
            unsafe = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script><a href="javascript:alert(1)"><rect width="10" height="10"/></a></svg>'
            cover = manager.store_cover("Book::Reading", unsafe, ".svg")
            rendered = cover.read_text(encoding="utf-8").lower()
            self.assertNotIn("script", rendered)
            self.assertNotIn("onload", rendered)
            self.assertNotIn("javascript:", rendered)
            self.assertEqual(cover, manager.cover("Book::Reading"))
            self.assertLessEqual(manager.diagnostics()["covers"]["size_bytes"], manager.diagnostics()["covers"]["limit_bytes"])
            self.assertEqual("covers", manager.prune("covers")["namespace"])


class OperationsGateTests(unittest.TestCase):
    def test_performance_evaluator_requires_ten_timing_samples_and_memory_evidence(self):
        passing = {
            "timings_ms": {name: [budget / 2] * 10 for name, budget in TIME_BUDGETS_MS.items()},
            "memory_mb": {name: [budget / 2] for name, budget in MEMORY_BUDGETS_MB.items()},
        }
        self.assertTrue(evaluate(passing)["passed"])
        passing["timings_ms"]["page_turn"] = [79] * 9
        self.assertFalse(evaluate(passing)["passed"])

    def test_database_backup_is_verified_and_connections_close(self):
        with tempfile.TemporaryDirectory() as root:
            database = Path(root, "operational.db")
            with closing(sqlite3.connect(database)) as conn:
                conn.execute("CREATE TABLE values_table(value TEXT)")
                conn.execute("INSERT INTO values_table VALUES('safe')")
                conn.commit()
            service = DatabaseMaintenanceService(str(Path(root, "backups")), {"reader": database})
            self.assertEqual("ok", service.inspect(database)["integrity"])
            backup = service.backup("reader")
            self.assertEqual("ok", service.inspect(backup)["integrity"])
            self.assertTrue(database.unlink() is None)

    def test_production_logging_is_bounded_compressed_and_redacted(self):
        import logging
        with tempfile.TemporaryDirectory() as root:
            target, handler, owned = configure_file_logging(root)
            self.assertEqual(5, handler.backupCount)
            self.assertTrue(handler.namer("bookbuddy.log.1").endswith(".gz"))
            record = logging.LogRecord("test", logging.ERROR, __file__, 1, "Authorization: Bearer secret token=abc", (), None)
            RedactionFilter().filter(record)
            from log_manager import close_file_logging

            close_file_logging(handler, owned=owned)
            self.assertNotIn("secret", record.getMessage())
            self.assertNotIn("abc", record.getMessage())
            logging.getLogger().removeHandler(handler)
            handler.close()


class SecurityBoundaryTests(unittest.TestCase):
    def test_epub_requires_a_standard_mimetype_signature(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "bad.epub")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("META-INF/container.xml", "<container/>")
            with self.assertRaisesRegex(ValueError, "mimetype"):
                validate_epub_archive(path)

    def test_epub_rejects_executable_members_before_import(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "hostile.epub")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
                archive.writestr("OPS/payload.exe", b"MZ")
            with self.assertRaisesRegex(ValueError, "Executable EPUB member"):
                validate_epub_archive(path)


class EpubCompatibilityMatrixTests(unittest.TestCase):
    def test_generated_matrix_imports_and_preserves_visual_spine_items(self):
        with tempfile.TemporaryDirectory() as root:
            fixtures = build_compatibility_fixtures(root)
            self.assertEqual({"reflowable_epub3", "poetry_heavy_css", "rtl", "missing_toc", "broken_html_css", "fixed_layout"}, set(fixtures))
            for name, path in fixtures.items():
                with self.subTest(name=name):
                    self.assertGreater(validate_epub_archive(path)["members"], 2)
                    parsed = parse_epub(str(path))
                    self.assertGreaterEqual(parsed.total_chapters, 1)
                    self.assertTrue(parsed.chapters[0].spine_href)
            fixed = parse_epub(str(fixtures["fixed_layout"]))
            self.assertEqual("VISUAL_PAGE", fixed.chapters[0].section_type)

if __name__ == "__main__":
    unittest.main()
