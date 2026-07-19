import hashlib
import json
import tempfile
import unittest
import uuid

from db_manager import BookDatabase
from explanation_service import ExplanationService
from graph_sanity import run_graph_sanity
from landmark_resolver import LandmarkResolver
from snapshot_manager import EvidenceStore, ReplayCoordinator, SnapshotStore, _changed_resolvers, resolver_manifest


def payload_for(name: str) -> dict:
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
        "_metadata": {},
    }


class PreRetentionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reader_snapshot_is_strictly_as_of_and_uses_v2(self):
        name = f"subject_{uuid.uuid4().hex[:12]}"
        db = BookDatabase(self.db_dir)
        entity_id = db.add_entity(name, "INDIVIDUAL", 0)
        db.record_life_status_evidence(
            entity_id, subject_surface=name, chapter_idx=0, actual_status="alive",
            belief_status="alive", reader_visible=True, confidence=0.95,
        )
        db.record_life_status_evidence(
            entity_id, subject_surface=name, chapter_idx=4, actual_status="dead",
            belief_status="dead", reader_visible=True, confidence=0.95,
        )
        db.update_entity_ontology(entity_id, {"sentience": "sentient"}, chapter_idx=4, confidence=0.95)
        evidence = EvidenceStore.record(db, 0, payload_for(name), trigger_reason="test")
        SnapshotStore.capture(db, 0, evidence, trigger_reason="test")
        snapshot = SnapshotStore.get(db, 0)["snapshot"]
        db.close()

        self.assertEqual("reader_snapshot_v2", snapshot["contract_version"])
        self.assertEqual(0, snapshot["reader_contract"]["as_of_chapter"])
        self.assertEqual("known", snapshot["life_status"][0]["reader_state"])
        self.assertEqual("alive", snapshot["life_status"][0]["status"])
        self.assertEqual("unknown", snapshot["visible_entities"][0]["ontology"]["sentience"])
        self.assertNotIn("dead", json.dumps(snapshot, sort_keys=True))
        self.assertNotIn("actual_status", snapshot["life_status"][0])

    def test_resolver_decisions_and_conflicts_are_append_only(self):
        first_name = f"subject_{uuid.uuid4().hex[:12]}"
        second_name = f"peer_{uuid.uuid4().hex[:12]}"
        db = BookDatabase(self.db_dir)
        evidence = EvidenceStore.record(db, 0, payload_for(first_name), trigger_reason="test")
        payload_before = EvidenceStore.active_payload(db, 0)
        first_id = db.add_entity(first_name, "INDIVIDUAL", 0)
        second_id = db.add_entity(second_name, "INDIVIDUAL", 0)
        db.resolve_entity_reference(first_name, "INDIVIDUAL", 0)
        db.update_entity_ontology(first_id, {"sentience": "sentient"}, chapter_idx=0, confidence=0.9)
        db.update_entity_ontology(second_id, {"sentience": "sentient"}, chapter_idx=0, confidence=0.9)
        db.record_life_status_evidence(
            first_id, subject_surface=first_name, chapter_idx=0, actual_status="alive",
            belief_status="alive", reader_visible=True, confidence=0.9,
        )
        event_id = db.add_event(0, "generic structural event", 0)
        LandmarkResolver(db).resolve_or_create(
            {"summary": "generic structural event", "landmark_name": "generic landmark"}, event_id, 0
        )
        db.add_relationship_event(first_id, second_id, 0, 3, "generic direct interaction")
        db.record_conflict(
            "relationship_contradiction", 0, {"reason": "test"}, first_id, second_id,
            resolver_key="relationships", subject_type="relationship", subject_key=f"{first_id}::{second_id}",
        )
        decisions = db.get_resolver_decisions()
        explanation = ExplanationService(db).explain("entity", first_id)
        payload_after = EvidenceStore.active_payload(db, 0)
        conflict = db._get_connection().execute(
            "SELECT resolver_key, subject_type, subject_key FROM conflict_records ORDER BY id DESC LIMIT 1"
        ).fetchone()
        db.close()

        self.assertEqual(evidence["payload_hash"], hashlib.sha256(json.dumps(payload_after, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest())
        self.assertEqual(payload_before, payload_after)
        self.assertTrue(
            {"identity", "ontology", "life_status", "landmarks", "relationships"}.issubset({row["resolver"] for row in decisions}),
            decisions,
        )
        self.assertEqual("engine_debug", explanation["scope"])
        self.assertEqual(("relationships", "relationship", f"{first_id}::{second_id}"), conflict)

    def test_manifest_dependency_closure_and_replay_modes(self):
        manifest = resolver_manifest()
        older_manifest = dict(manifest)
        older_manifest["resolver:identity"] = "previous_identity_contract"
        changed = _changed_resolvers(older_manifest, manifest)
        self.assertTrue({"identity", "ontology", "life_status", "landmarks", "relationships"}.issubset(set(changed)))

        name = f"subject_{uuid.uuid4().hex[:12]}"
        db = BookDatabase(self.db_dir)
        EvidenceStore.record(db, 0, payload_for(name), trigger_reason="test")
        db.close()
        coordinator = ReplayCoordinator(self.db_dir)
        full = coordinator.run(mode="full", reason="test")
        db = BookDatabase(self.db_dir)
        sanity = run_graph_sanity(db.db_path)
        db._get_connection().execute(
            "UPDATE chapter_processing_checkpoints SET resolver_manifest_json = ?, resolver_manifest_hash = ?",
            (json.dumps(older_manifest, sort_keys=True), "obsolete_manifest_hash"),
        )
        db._get_connection().commit()
        ReplayCoordinator._record_version_invalidations(db, "")
        invalidation_details = json.loads(
            db._get_connection().execute(
                "SELECT details_json FROM chapter_invalidations WHERE reason = 'resolver_manifest_changed' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        )
        history_before_verify = len(SnapshotStore.history(db, 0))
        db.close()
        self.assertIn("relationships", invalidation_details["affected_resolvers"])
        coordinator.run(mode="full", reason="manifest_test")
        verify = coordinator.run(mode="verify", reason="test")
        db = BookDatabase(self.db_dir)
        history_after_verify = len(SnapshotStore.history(db, 0))
        db.close()
        normal = coordinator.run(mode="normal", reason="test")

        self.assertTrue(full["promoted"])
        self.assertEqual([], sanity["issues"])
        self.assertFalse(verify["promoted"])
        self.assertTrue(verify["verified"])
        self.assertEqual(history_before_verify, history_after_verify)
        self.assertFalse(normal["rebuilt"])


if __name__ == "__main__":
    unittest.main()
