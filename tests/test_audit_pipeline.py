import io
import json
import tempfile
import unittest
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient

from app import create_app
from audit.database import compare_databases, export_evidence_bundle, import_evidence_bundle, inspect_database
from audit.faults import FaultInjector, InjectedAuditFault
from audit.fixtures import select_canary_chapters
from audit.models import AuditReport
from audit.runner import audited_model_price
from config import load_config
from db_manager import BookDatabase
from snapshot_manager import EvidenceStore, ReaderSnapshotBuilder, ReplayCoordinator
from storage_security import resolve_under_root, safe_epub_filename, validate_epub_archive


def payload(name="Audit Subject"):
    return {
        "pov_character_found": name,
        "new_aliases_discovered": [],
        "new_group_aliases_discovered": [],
        "entities_present": [{"name": name, "entity_type": "INDIVIDUAL", "active_status": "active_participant"}],
        "relationships": [],
        "major_events": [],
        "entity_semantic_relations": [],
        "language_observations": [],
        "life_status_events": [],
        "legacy_signals": [],
        "_metadata": {"audit": True},
    }


class AuditPipelineTests(unittest.TestCase):
    def test_live_audit_fails_closed_when_official_model_pricing_is_unpublished(self):
        pricing = json.loads((Path(__file__).parents[1] / "backend" / "audit" / "pricing.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(RuntimeError, "pricing is not published"):
            audited_model_price(pricing, "gemini-3.6-flash")

    def test_report_blocks_critical_failure_and_pending_gate(self):
        report = AuditReport("run", "offline", 1, {})
        report.add("ok", "pass", "ok")
        self.assertEqual("ready", report.release_decision)
        report.add("review", "not_run", "pending")
        self.assertEqual("pending", report.release_decision)
        report.add("failure", "fail", "failed")
        self.assertEqual("blocked", report.release_decision)

    def test_fault_injection_is_explicit_and_counted(self):
        faults = FaultInjector("replay.before_promote", 2)
        faults.hit("replay.before_promote")
        with self.assertRaises(InjectedAuditFault):
            faults.hit("replay.before_promote")
        FaultInjector().hit("replay.before_promote")

    def test_evidence_bundle_rebuilds_identical_derived_graph(self):
        with tempfile.TemporaryDirectory() as root:
            first = Path(root, "first")
            second = Path(root, "second")
            first.mkdir()
            second.mkdir()
            db = BookDatabase(str(first))
            EvidenceStore.record(db, 0, payload(), trigger_reason="audit_test")
            db.close()
            self.assertTrue(ReplayCoordinator(str(first)).run(mode="full", reason="audit_test")["promoted"])
            bundle = Path(root, "evidence.json")
            export_evidence_bundle(first / "graph.db", bundle)
            import_evidence_bundle(bundle, second)
            self.assertTrue(ReplayCoordinator(str(second)).run(mode="full", reason="audit_test")["promoted"])
            comparison = compare_databases(first / "graph.db", second / "graph.db", categories=("derived",))
            self.assertTrue(comparison["matched"], comparison["mismatches"])
            self.assertTrue(inspect_database(second / "graph.db")["passed"])

    def test_replay_fault_does_not_promote_partial_derived_state(self):
        with tempfile.TemporaryDirectory() as root:
            db = BookDatabase(root)
            EvidenceStore.record(db, 0, payload("First Subject"), trigger_reason="audit_test")
            db.close()
            ReplayCoordinator(root).run(mode="full", reason="audit_test")
            before = Path(root, "before.db")
            __import__("shutil").copy2(Path(root, "graph.db"), before)
            db = BookDatabase(root)
            EvidenceStore.record(db, 1, payload("Second Subject"), trigger_reason="audit_test")
            db.close()
            fault = FaultInjector("replay.before_promote")
            with self.assertRaises(InjectedAuditFault):
                ReplayCoordinator(root, fault_injector=fault).run(mode="full", reason="fault_test")
            comparison = compare_databases(before, Path(root, "graph.db"), categories=("derived",))
            self.assertTrue(comparison["matched"], comparison["mismatches"])
            self.assertTrue(ReplayCoordinator(root).run(mode="full", reason="recovery")["promoted"])

    def test_reader_entity_aggregate_is_strictly_as_of(self):
        with tempfile.TemporaryDirectory() as root:
            db = BookDatabase(root)
            EvidenceStore.record(db, 0, payload(), trigger_reason="audit_test")
            db.close()
            ReplayCoordinator(root).run(mode="full", reason="audit_test")
            db = BookDatabase(root)
            entity_id = db._get_connection().execute("SELECT id FROM entities").fetchone()[0]
            result = ReaderSnapshotBuilder(db).build_entity(entity_id, 0)
            db.close()
            self.assertEqual("reader_entity_v1", result["contract_version"])
            self.assertEqual(entity_id, result["entity"]["id"])
            self.assertEqual(0, result["as_of_chapter"])

    def test_storage_paths_and_epub_members_are_contained(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(Path(root, "book", "session").resolve(), resolve_under_root(root, "book", "session"))
            with self.assertRaises(ValueError):
                resolve_under_root(root, "..", "outside")
            self.assertEqual("escape.epub", safe_epub_filename("../../escape.epub"))
            unsafe = Path(root, "unsafe.epub")
            with zipfile.ZipFile(unsafe, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                validate_epub_archive(unsafe)

    def test_upload_rejects_unsafe_archive_without_writing_outside_library(self):
        with tempfile.TemporaryDirectory() as root:
            config = load_config(root, {"BOOKBUDDY_LIBRARY_DIR": "library", "BOOKBUDDY_CACHE_DIR": "cache", "BOOKBUDDY_LOG_DIR": "logs"})
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            with TestClient(create_app(config)) as client:
                response = client.post(
                    "/upload",
                    files={"file": ("../../escape.epub", raw.getvalue(), "application/epub+zip")},
                    data={"session_name": "audit"},
                )
            self.assertEqual(400, response.status_code)
            self.assertFalse(Path(root, "escape.epub").exists())

    def test_canary_selection_is_data_driven_and_bounded(self):
        class Chapter:
            def __init__(self, index, words, images=0):
                self.index = index
                self.word_count = words
                self.image_descriptors = [object()] * images
        selected = select_canary_chapters([Chapter(i, 100 + i, 3 if i == 2 else 0) for i in range(10)])
        self.assertLessEqual(len(selected), 5)
        self.assertIn(0, selected)
        self.assertIn(9, selected)
        self.assertIn(2, selected)


class ReaderEntityApiTests(unittest.TestCase):
    def test_reader_entity_route_uses_reader_contract(self):
        with tempfile.TemporaryDirectory() as root:
            config = load_config(root, {"BOOKBUDDY_LIBRARY_DIR": "library", "BOOKBUDDY_CACHE_DIR": "cache", "BOOKBUDDY_LOG_DIR": "logs"})
            db_dir = config.paths.library_dir / "Book" / "Session" / "database"
            db_dir.mkdir(parents=True)
            db = BookDatabase(str(db_dir))
            EvidenceStore.record(db, 0, payload(), trigger_reason="api_test")
            db.close()
            ReplayCoordinator(str(db_dir)).run(mode="full", reason="api_test")
            db = BookDatabase(str(db_dir))
            entity_id = db._get_connection().execute("SELECT id FROM entities").fetchone()[0]
            db.close()
            with TestClient(create_app(config)) as client:
                response = client.get(f"/reader/Book/Session/entity/{entity_id}?as_of_chapter=0")
            self.assertEqual(200, response.status_code, response.text)
            self.assertEqual("reader_entity_v1", response.json()["contract_version"])
            self.assertEqual(entity_id, response.json()["entity"]["id"])


if __name__ == "__main__":
    unittest.main()
