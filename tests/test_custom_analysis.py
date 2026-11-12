from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import create_app
from config import load_config
from epub_test_fixture import build_omnibus_navigation_fixture
from snapshot_manager import EvidenceStore

from .test_snapshot_manager import synthetic_payload


def record_fake_evidence(db, chapter_index):
    """Stand in for the AI extraction: store evidence the way a real chapter run does."""
    EvidenceStore.record(db, chapter_index, synthetic_payload([f"Character {chapter_index}"]), trigger_reason="test")


class _ReplayStub:
    def replay(self, reason):
        return {"reason": reason}


class CustomAnalysisTests(unittest.TestCase):
    def config(self, root):
        return load_config(root, {
            "BOOKBUDDY_LIBRARY_DIR": "library", "BOOKBUDDY_CACHE_DIR": "cache", "BOOKBUDDY_LOG_DIR": "logs",
            "BOOKBUDDY_CONFIG_DIR": "config",
        })

    def wait_for(self, client, base, status, seconds=20):
        deadline = time.time() + seconds
        overview = {}
        while time.time() < deadline:
            overview = client.get(f"{base}/analysis/overview").json()
            if overview["task"]["status"] == status:
                return overview
            time.sleep(0.1)
        self.fail(f"analysis never reached {status}: {overview.get('task')}")

    def test_custom_analysis_runs_through_the_chosen_chapter_and_unlocks_knowledge(self):
        import app as app_module
        with tempfile.TemporaryDirectory() as root:
            fixture = build_omnibus_navigation_fixture(Path(root, "fixture.epub"))
            with TestClient(create_app(self.config(root))) as client:
                identity = client.post(
                    "/upload", files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reading"},
                ).json()
                base = f"/reader/{identity['book_name']}/{identity['session_name']}"
                session_key = f"{identity['book_name']}::{identity['session_name']}"
                user_id = client.post("/reader/profile").json()["user_id"]

                overview = client.get(f"{base}/analysis/overview")
                self.assertEqual(200, overview.status_code, overview.text)
                body = overview.json()
                self.assertEqual("bookbuddy_analysis_overview_v1", body["schema_version"])
                self.assertEqual(identity["total_chapters"], body["total_chapters"])
                self.assertEqual(identity["total_chapters"], len(body["chapters"]))
                self.assertEqual(-1, body["analysed_through"])
                self.assertEqual("idle", body["task"]["status"])
                self.assertEqual(404, client.get("/reader/Missing/Nope/analysis/overview").status_code)

                request = {"through_chapter": 3, "user_id": user_id}
                too_far = client.post(f"{base}/analysis/custom", json={**request, "through_chapter": 999})
                self.assertEqual(422, too_far.status_code)
                preview = client.post(f"{base}/analysis/custom", json={**request, "dry_run": True})
                self.assertEqual(202, preview.status_code, preview.text)
                self.assertEqual(4, preview.json()["chapters_to_analyse"])
                self.assertFalse(preview.json()["started"])

                manager = app_module.ai_manager
                with mock.patch.object(manager, "is_available", return_value=False):
                    self.assertEqual(503, client.post(f"{base}/analysis/custom", json=request).status_code)
                state = client.get(f"/reader/{user_id}/library-state").json()
                self.assertEqual([], [item for item in state["books"] if item["session_key"] == session_key and item["knowledge_through_chapter"] is not None])

                processed = []

                def fake_process(chapter_index, book, db_dir, db, *args, **kwargs):
                    processed.append(chapter_index)
                    record_fake_evidence(db, chapter_index)

                with mock.patch.object(manager, "is_available", return_value=True), \
                        mock.patch.object(app_module.parser_service, "process_chapter", side_effect=fake_process), \
                        mock.patch.object(app_module.replay_service, "coordinator", return_value=_ReplayStub()):
                    started = client.post(f"{base}/analysis/custom", json=request)
                    self.assertEqual(202, started.status_code, started.text)
                    self.assertTrue(started.json()["started"])
                    finished = self.wait_for(client, base, "completed")
                    self.assertEqual([0, 1, 2, 3], processed)
                    self.assertEqual(3, finished["analysed_through"])
                    self.assertEqual(100.0, finished["task"]["progress"])

                    # Asking again for an earlier chapter needs no new work.
                    again = client.post(f"{base}/analysis/custom", json={**request, "through_chapter": 2, "dry_run": True})
                    self.assertEqual(0, again.json()["chapters_to_analyse"])

                book_state = next(item for item in client.get(f"/reader/{user_id}/library-state").json()["books"] if item["session_key"] == session_key)
                self.assertEqual(3, book_state["knowledge_through_chapter"])
                self.assertEqual("custom", book_state["analysis_mode"])
                # Declaring what you have read must not move reading progress.
                self.assertEqual(0.0, book_state["book_progress"])
                self.assertIsNone(book_state["current_chapter"])

                books_url = f"/reader/{user_id}/books/{identity['book_name']}/{identity['session_name']}"
                cleared = client.put(books_url, json={"knowledge_through_chapter": -1, "analysis_mode": "auto"}).json()["book"]
                self.assertIsNone(cleared["knowledge_through_chapter"])
                self.assertEqual("auto", cleared["analysis_mode"])
                self.assertEqual(422, client.put(books_url, json={"analysis_mode": "everything"}).status_code)

    def test_a_failed_run_reports_a_plain_message_and_keeps_finished_chapters(self):
        import app as app_module
        with tempfile.TemporaryDirectory() as root:
            fixture = build_omnibus_navigation_fixture(Path(root, "fixture.epub"))
            with TestClient(create_app(self.config(root))) as client:
                identity = client.post("/upload", files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")}).json()
                base = f"/reader/{identity['book_name']}/{identity['session_name']}"
                user_id = client.post("/reader/profile").json()["user_id"]

                def fake_process(chapter_index, book, db_dir, db, *args, **kwargs):
                    if chapter_index == 2:
                        raise RuntimeError("secret provider payload sk-123")
                    record_fake_evidence(db, chapter_index)

                with mock.patch.object(app_module.ai_manager, "is_available", return_value=True), \
                        mock.patch.object(app_module.parser_service, "process_chapter", side_effect=fake_process), \
                        mock.patch.object(app_module.replay_service, "coordinator", return_value=_ReplayStub()):
                    client.post(f"{base}/analysis/custom", json={"through_chapter": 4, "user_id": user_id})
                    failed = self.wait_for(client, base, "error")
                self.assertEqual(1, failed["analysed_through"])
                self.assertNotIn("secret provider payload", str(failed))
                self.assertIn("already analysed are kept", failed["task"]["log"])


if __name__ == "__main__":
    unittest.main()
