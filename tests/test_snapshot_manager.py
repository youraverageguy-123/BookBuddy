import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from db_manager import BookDatabase
from life_status_resolver import LifeStatusResolver
from snapshot_manager import EvidenceStore, ReplayCoordinator, SnapshotStore


def synthetic_payload(entity_names):
    return {
        "pov_character_found": entity_names[0] if entity_names else "",
        "new_aliases_discovered": [],
        "new_group_aliases_discovered": [],
        "entities_present": [
            {"name": name, "entity_type": "INDIVIDUAL", "active_status": "active_participant"}
            for name in entity_names
        ],
        "relationships": [],
        "major_events": [],
        "entity_semantic_relations": [],
        "language_observations": [],
        "life_status_events": [],
        "legacy_signals": [],
        "_metadata": {},
    }


class SnapshotManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_replay_is_idempotent_and_only_versions_changed_snapshots(self):
        db = BookDatabase(self.db_dir)
        EvidenceStore.record(db, 0, synthetic_payload(["Aster"]), trigger_reason="new_chapter")
        db.close()

        first = ReplayCoordinator(self.db_dir).replay("test_replay")
        second = ReplayCoordinator(self.db_dir).replay("test_replay")
        self.assertTrue(first["rebuilt"])
        self.assertEqual(1, first["snapshots_changed"])
        self.assertEqual(0, second["snapshots_changed"])

        db = BookDatabase(self.db_dir)
        EvidenceStore.record(db, 0, synthetic_payload(["Beryl"]), trigger_reason="bug_fix")
        db.close()
        changed = ReplayCoordinator(self.db_dir).replay("bug_fix")
        self.assertEqual(1, changed["snapshots_changed"])

        db = BookDatabase(self.db_dir)
        history = SnapshotStore.history(db, 0)
        db.close()
        self.assertEqual(2, len(history))
        self.assertIn("Beryl", history[-1]["change_summary"]["affected"]["entities"])

    def test_snapshot_filters_hidden_state_and_keeps_reader_known_categories(self):
        db = BookDatabase(self.db_dir)
        entity_id = db.add_entity("Aster", "INDIVIDUAL", 0)
        db.record_life_status_evidence(
            entity_id,
            subject_surface="Aster",
            chapter_idx=0,
            actual_status="alive",
            belief_status="alive",
            reader_visible=True,
            confidence=0.9,
        )
        db.record_life_status_evidence(
            entity_id,
            subject_surface="Aster",
            chapter_idx=0,
            actual_status="dead",
            belief_status="dead",
            reader_visible=False,
            confidence=1.0,
        )
        LifeStatusResolver(db).resolve_all()
        conn = db._get_connection()
        conn.execute(
            """
            INSERT INTO event_landmarks (
                identity_key, lifecycle, landmark_type, event_state,
                event_reliability, reader_visibility, narrative_first_chapter,
                reader_known_since_chapter
            ) VALUES ('visible-landmark', 'landmark', 'event', 'completed', 'direct', 'fully_known', 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO event_landmarks (
                identity_key, lifecycle, landmark_type, event_state,
                event_reliability, reader_visibility, narrative_first_chapter,
                reader_known_since_chapter
            ) VALUES ('hidden-landmark', 'landmark', 'event', 'completed', 'direct', 'hidden', 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO reference_mentions (
                surface_form, normalized_form, chapter, entity_type_guess,
                reference_subtype, promotion_state
            ) VALUES ('Aster Memorial', 'aster memorial', 0, 'CONCEPT_OR_LORE', 'commemorative_reference', 'reference')
            """
        )
        conn.commit()
        evidence = EvidenceStore.record(db, 0, synthetic_payload(["Aster"]), trigger_reason="test")
        SnapshotStore.capture(db, 0, evidence, trigger_reason="test")
        snapshot = SnapshotStore.get(db, 0)["snapshot"]
        db.close()

        self.assertEqual(["visible-landmark"], [item["identity_key"] for item in snapshot["landmarks"]])
        self.assertEqual("Aster Memorial", snapshot["reference_mentions"][0]["surface"])
        self.assertEqual("known", snapshot["life_status"][0]["reader_state"])
        self.assertEqual("alive", snapshot["life_status"][0]["status"])
        self.assertNotIn("source_quote", json.dumps(snapshot, sort_keys=True))

    def test_legacy_cache_import_preserves_the_existing_active_revision(self):
        cache_path = Path(self.db_dir) / "chapter_0.json"
        cache_path.write_text(json.dumps(synthetic_payload(["Aster"])), encoding="utf-8")
        db = BookDatabase(self.db_dir)
        imported = EvidenceStore.import_legacy_caches(db, self.db_dir)
        first = EvidenceStore.active_records(db)
        EvidenceStore.record(db, 0, synthetic_payload(["Aster", "Beryl"]), trigger_reason="explicit_reextract")
        imported_again = EvidenceStore.import_legacy_caches(db, self.db_dir)
        active = EvidenceStore.active_records(db)
        db.close()

        self.assertEqual(1, len(imported))
        self.assertEqual(1, first[0]["revision"])
        self.assertEqual(1, len(imported_again))
        self.assertEqual(2, active[0]["revision"])
        self.assertIn("Beryl", active[0]["payload"]["entities_present"][1]["name"])

    def test_replay_preserves_parent_graph_provenance(self):
        library_dir = Path(self.db_dir) / "library"
        parent_db_dir = library_dir / "Parent_Work" / "base" / "database"
        parent_db_dir.mkdir(parents=True)
        parent_db = BookDatabase(str(parent_db_dir))
        parent_db.add_entity("Aster", "INDIVIDUAL", 0)
        parent_db.close()

        child_session_dir = library_dir / "Child_Work" / "reading" 
        child_db_dir = child_session_dir / "database"
        child_db_dir.mkdir(parents=True)
        (child_session_dir / "continuity.json").write_text(
            json.dumps(
                {
                    "current_book": "Child_Work",
                    "parent_book": "Parent_Work",
                    "parent_session": "base",
                    "inherited_graph": True,
                }
            ),
            encoding="utf-8",
        )
        child_db = BookDatabase(str(child_db_dir))
        EvidenceStore.record(child_db, 0, synthetic_payload(["Beryl"]), trigger_reason="new_chapter")
        child_db.close()

        ReplayCoordinator(str(child_db_dir)).replay("test_inheritance")
        child_db = BookDatabase(str(child_db_dir))
        snapshot = SnapshotStore.get(child_db, 0)["snapshot"]
        child_db.close()

        inherited = next(item for item in snapshot["visible_entities"] if item["canonical_name"] == "Aster")
        self.assertEqual("inherited", inherited["provenance"]["origin"])

    def test_raw_and_reader_snapshot_handlers_keep_separate_contracts(self):
        with contextlib.redirect_stdout(io.StringIO()):
            import app as api_main

        library_dir = Path(self.db_dir) / "library"
        db_dir = library_dir / "Book_Work" / "reading" / "database"
        db_dir.mkdir(parents=True)
        db = BookDatabase(str(db_dir))
        payload = synthetic_payload(["Aster"])
        evidence = EvidenceStore.record(db, 0, payload, trigger_reason="test")
        SnapshotStore.capture(db, 0, evidence, trigger_reason="test")
        db.close()

        original_library_dir = api_main.LIBRARY_DIR
        original_registry = api_main.database_registry
        from bootstrap import DatabaseRegistry
        api_main.LIBRARY_DIR = str(library_dir)
        api_main.database_registry = DatabaseRegistry()
        try:
            raw = api_main.get_chapter_data("Book_Work", "reading", 0)
            reader_snapshot = api_main.get_chapter_snapshot("Book_Work", "reading", 0)
            engine_explanation = api_main.explain_engine_state("Book_Work", "reading", "snapshot", "0")
        finally:
            api_main.LIBRARY_DIR = original_library_dir
            api_main.database_registry.close_all()
            api_main.database_registry = original_registry

        self.assertEqual("Aster", raw["pov_character_found"])
        self.assertEqual("reader_snapshot_v2", reader_snapshot["contract_version"])
        self.assertIn("visible_entities", reader_snapshot["snapshot"])
        self.assertEqual("engine_debug", engine_explanation["scope"])


if __name__ == "__main__":
    unittest.main()
