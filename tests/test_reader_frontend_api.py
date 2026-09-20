import asyncio
import io
import os
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
from urllib.parse import quote
from unittest import mock

from fastapi.testclient import TestClient

from app import create_app
from bootstrap import DatabaseRegistry
from config import load_config
from db_manager import BookDatabase
from epub_test_fixture import build_image_fixture, build_omnibus_navigation_fixture
from reader_analysis import ReaderAnalysisCoordinator
from session_manager import SessionManager
from snapshot_manager import EvidenceStore


class ReaderContractTests(unittest.TestCase):
    def config(self, root):
        return load_config(root, {
            "BOOKBUDDY_LIBRARY_DIR": "library",
            "BOOKBUDDY_CACHE_DIR": "cache",
            "BOOKBUDDY_LOG_DIR": "logs",
        })

    def test_health_upload_session_book_mapping_and_epub_stream(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = build_image_fixture(Path(root, "fixture.epub"))
            with TestClient(create_app(self.config(root))) as client:
                health = client.get("/health")
                self.assertEqual(200, health.status_code)
                self.assertEqual("bookbuddy_health_v1", health.json()["schema_version"])
                uploaded = client.post(
                    "/upload",
                    files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reader"},
                )
                self.assertEqual(200, uploaded.status_code, uploaded.text)
                identity = uploaded.json()
                sessions = client.get("/sessions").json()
                self.assertEqual("bookbuddy_sessions_v1", sessions["schema_version"])
                self.assertEqual(1, len(sessions["sessions"]))
                self.assertNotIn("session_dir", sessions["sessions"][0])
                self.assertEqual("BookBuddy Tests", sessions["sessions"][0]["author"])
                metadata = client.get(f"/book/{identity['book_name']}/{identity['session_name']}")
                self.assertEqual(200, metadata.status_code, metadata.text)
                first = metadata.json()["chapters"][0]
                self.assertEqual("chapter-images", first["item_id"])
                self.assertEqual("chapter-images.xhtml", first["spine_href"])
                streamed = client.get(f"/reader/{identity['book_name']}/{identity['session_name']}/epub")
                self.assertEqual(200, streamed.status_code)
                self.assertEqual("application/epub+zip", streamed.headers["content-type"])
                self.assertGreater(len(streamed.content), 100)
                cover_path = Path(root, "cover.png")
                cover_path.write_bytes(b"\x89PNG\r\n\x1a\nbookbuddy-cover")
                with mock.patch("app._extract_cover", return_value=(str(cover_path), "image/png")):
                    cover = client.get(f"/reader/{identity['book_name']}/{identity['session_name']}/cover?size=320")
                self.assertEqual(200, cover.status_code, cover.text)
                self.assertTrue(cover.headers["content-type"].startswith("image/"))
                self.assertGreater(len(cover.content), 8)
                invalid_cover_size = client.get(f"/reader/{identity['book_name']}/{identity['session_name']}/cover?size=321")
                self.assertEqual(422, invalid_cover_size.status_code)
                highlight = client.post(
                    f"/reader/{identity['book_name']}/{identity['session_name']}/highlight",
                    json={
                        "chapter_index": 0,
                        "selected_text": "world",
                        "context_text": "The whole world was quiet.",
                        "language": "en",
                        "allow_ai_fallback": False,
                        "knowledge_as_of_chapter": -1,
                    },
                )
                self.assertEqual(200, highlight.status_code, highlight.text)
                self.assertEqual("unavailable", highlight.json()["story_glossary"]["status"])
                self.assertIn(highlight.json()["general_dictionary"]["status"], {"ok", "not_found", "unavailable"})
                self.assertIn(highlight.json()["pronunciation"]["status"], {"ok", "unavailable"})

    def test_soft_deleted_session_is_not_rediscovered_from_its_undo_directory(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = build_image_fixture(Path(root, "fixture.epub"))
            with TestClient(create_app(self.config(root))) as client:
                uploaded = client.post(
                    "/upload",
                    files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reading"},
                )
                self.assertEqual(200, uploaded.status_code, uploaded.text)
                identity = uploaded.json()
                deleted = client.post(f"/session/{identity['book_name']}/{identity['session_name']}/delete")
                self.assertEqual(200, deleted.status_code, deleted.text)
                sessions = client.get("/sessions").json()["sessions"]
                self.assertEqual([], sessions)
                deleted_sessions = client.get("/sessions?include_deleted=true").json()["sessions"]
                self.assertEqual(1, len(deleted_sessions))
                self.assertEqual("deleted", deleted_sessions[0]["integrity"]["status"])
                structured = client.post(
                    f"/reader/{identity['book_name']}/{identity['session_name']}/highlight",
                    json={
                        "chapter_index": 0,
                        "selected_text": "I",
                        "context_text": "I waited. Then I left.",
                        "sentence_text": "Then I left.",
                        "previous_sentence": "I waited.",
                        "next_sentence": "",
                        "paragraph_text": "I waited. Then I left.",
                        "sentence_selection_start": 5,
                        "sentence_selection_end": 6,
                        "knowledge_as_of_chapter": -1,
                        "explain_function_words": False,
                    },
                )
                self.assertEqual(200, structured.status_code, structured.text)
                self.assertEqual("csre_v1", structured.json()["resolution"]["schema_version"])
                self.assertEqual("pronoun", structured.json()["resolution"]["classification"]["primary_class"])
                self.assertEqual("suppress_popup", structured.json()["routing"]["popup_action"])
                explain = client.post(
                    f"/reader/{identity['book_name']}/{identity['session_name']}/explain-selection",
                    json={"chapter_index": 0, "selected_text": "world", "context_text": "The whole world was quiet.", "knowledge_as_of_chapter": -1},
                )
                self.assertEqual(503, explain.status_code, explain.text)
                self.assertEqual("ai_service_unavailable", explain.json()["detail"]["code"])
                profile = client.post("/reader/profile").json()["user_id"]
                state_path = f"/reader/{profile}/books/{identity['book_name']}/{identity['session_name']}"
                updated = client.put(state_path, json={"favorite": True, "book_progress": .25, "last_cfi": "epubcfi(/6/2)"})
                self.assertEqual(200, updated.status_code, updated.text)
                chapter = client.put(f"{state_path}/chapters/0", json={"last_cfi": "epubcfi(/6/2)", "current_progress": .6, "contiguous_progress": .6, "threshold_started": True})
                self.assertEqual(200, chapter.status_code, chapter.text)
                collection = client.post(f"/reader/{profile}/collections", json={"name": "Quiet favorites"})
                self.assertEqual(200, collection.status_code, collection.text)
                collection_id = collection.json()["collection"]["collection_id"]
                member = client.put(f"/reader/{profile}/collections/{collection_id}/member", json={"session_key": f"{identity['book_name']}::{identity['session_name']}", "present": True})
                self.assertEqual(200, member.status_code, member.text)
                bookmark = client.post(f"{state_path}/bookmarks", json={"chapter_index": 0, "cfi": "epubcfi(/6/2)", "excerpt": "The whole world"})
                self.assertEqual(200, bookmark.status_code, bookmark.text)
                library_state = client.get(f"/reader/{profile}/library-state")
                self.assertEqual(200, library_state.status_code, library_state.text)
                self.assertEqual([f"{identity['book_name']}::{identity['session_name']}"], library_state.json()["smart_collections"]["favorites"])

    def test_epub_package_metadata_includes_local_synopsis_subjects_and_calibre_series(self):
        with tempfile.TemporaryDirectory() as root:
            epub_path = Path(root, "metadata.epub")
            with zipfile.ZipFile(epub_path, "w") as archive:
                archive.writestr("META-INF/container.xml", '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
                archive.writestr("OEBPS/content.opf", '''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Dungeon Crawler Carl</dc:title><dc:creator>Matt Dinniman</dc:creator><dc:publisher>Dandy House</dc:publisher><dc:date>2020-10-02T04:00:00+00:00</dc:date><dc:language>en</dc:language><dc:subject>LitRPG</dc:subject><dc:subject>Humor</dc:subject><dc:description>&lt;div&gt;&lt;p&gt;The apocalypse &lt;em&gt;will&lt;/em&gt; be televised!&lt;/p&gt;&lt;p&gt;A dungeon crawl.&lt;/p&gt;&lt;/div&gt;</dc:description><meta name="calibre:series" content="Dungeon Crawler Carl"/></metadata></package>''')
            from app import _epub_package_metadata_fields
            metadata = _epub_package_metadata_fields(str(epub_path))
            self.assertEqual("Dandy House", metadata["publisher"])
            self.assertEqual("en", metadata["language"])
            self.assertEqual(["LitRPG", "Humor"], metadata["genres"])
            self.assertEqual("Dungeon Crawler Carl", metadata["series"])
            self.assertEqual("The apocalypse will be televised!\nA dungeon crawl.", metadata["description"])

    def test_same_logical_import_is_idempotent_and_different_bytes_get_distinct_sources(self):
        with tempfile.TemporaryDirectory() as root:
            first_fixture = build_image_fixture(Path(root, "same-name.epub"))
            second_fixture = Path(root, "other", "same-name.epub")
            second_fixture.parent.mkdir()
            second_fixture.write_bytes(first_fixture.read_bytes())
            with zipfile.ZipFile(second_fixture, "a") as archive:
                archive.writestr("META-INF/collision-marker.txt", "different source bytes")

            with TestClient(create_app(self.config(root))) as client:
                first = client.post(
                    "/upload",
                    files={"file": ("same-name.epub", first_fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reading % 你好"},
                )
                repeated = client.post(
                    "/upload",
                    files={"file": ("same-name.epub", first_fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reading % 你好"},
                )
                collision = client.post(
                    "/upload",
                    files={"file": ("same-name.epub", second_fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reading % 你好"},
                )

                self.assertEqual(200, first.status_code, first.text)
                self.assertEqual(200, repeated.status_code, repeated.text)
                self.assertEqual(200, collision.status_code, collision.text)
                self.assertEqual(first.json()["session_name"], repeated.json()["session_name"])
                self.assertNotEqual(first.json()["session_name"], collision.json()["session_name"])
                self.assertIn("--", collision.json()["session_name"])

                first_stream = client.get(
                    f"/reader/{quote(first.json()['book_name'], safe='')}/{quote(first.json()['session_name'], safe='')}/epub"
                )
                collision_stream = client.get(
                    f"/reader/{quote(collision.json()['book_name'], safe='')}/{quote(collision.json()['session_name'], safe='')}/epub"
                )
                self.assertEqual(first_fixture.read_bytes(), first_stream.content)
                self.assertEqual(second_fixture.read_bytes(), collision_stream.content)

                state = __import__("json").loads(Path(root, "library", "session_state.json").read_text(encoding="utf-8"))
                self.assertEqual(2, len(state["sessions"]))
                for metadata in state["sessions"].values():
                    source = Path(metadata["session_dir"], metadata["source_epub_relpath"])
                    self.assertTrue(source.is_file())
                    self.assertEqual(source.stat().st_size, metadata["source_size_bytes"])
                    self.assertEqual("bookbuddy_session_source_v1", metadata["source_format_version"])

    def test_optional_api_token_protects_all_routes(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"BOOKBUDDY_API_TOKEN": "secret-token"}):
            with TestClient(create_app(self.config(root))) as client:
                self.assertEqual(401, client.get("/health").status_code)
                self.assertEqual(200, client.get("/health", headers={"Authorization": "Bearer secret-token"}).status_code)

    def test_reader_search_rebuild_runs_on_the_application_event_loop(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = build_image_fixture(Path(root, "search.epub"))
            with TestClient(create_app(self.config(root))) as client:
                uploaded = client.post(
                    "/upload",
                    files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Search Reader"},
                )
                self.assertEqual(200, uploaded.status_code, uploaded.text)
                identity = uploaded.json()
                route = f"/reader/{quote(identity['book_name'], safe='')}/{quote(identity['session_name'], safe='')}/search"

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    status = client.get(f"{route}/status")
                    self.assertEqual(200, status.status_code, status.text)
                    if status.json()["ready"]:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("initial reader search index was not ready")

                rebuilt = client.post(f"{route}/rebuild")
                self.assertEqual(202, rebuilt.status_code, rebuilt.text)

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if client.get(f"{route}/status").json()["ready"]:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("rebuilt reader search index was not ready")

                result = client.get(route, params={"q": "travelers", "chapter": 0})
                self.assertEqual(200, result.status_code, result.text)
                self.assertEqual("bookbuddy_reader_search_v1", result.json()["schema_version"])
                self.assertTrue(result.json()["results"])

    def test_book_metadata_exposes_additive_omnibus_navigation(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = build_omnibus_navigation_fixture(Path(root, "omnibus.epub"))
            with TestClient(create_app(self.config(root))) as client:
                uploaded = client.post("/upload", files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")}, data={"session_name": "Reading"})
                self.assertEqual(200, uploaded.status_code, uploaded.text)
                identity = uploaded.json()
                metadata = client.get(f"/book/{identity['book_name']}/{identity['session_name']}")
                self.assertEqual(200, metadata.status_code, metadata.text)
                payload = metadata.json()
                self.assertEqual("bookbuddy_book_v1", payload["schema_version"])
                self.assertEqual("bookbuddy_navigation_v1", payload["navigation"]["schema_version"])
                self.assertEqual("omnibus", payload["navigation"]["mode"])
                self.assertEqual(["First Tale", "Second Tale"], [book["title"] for book in payload["navigation"]["books"]])
                self.assertEqual("1", next(entry["display_number"] for entry in payload["navigation"]["books"][1]["entries"] if entry["title"] == "Chapter 1: Arrival"))
                self.assertIsNone(next(entry["chapter_index"] for entry in payload["navigation"]["books"][0]["entries"] if entry["title"] == "Publisher Note"))
                self.assertEqual(payload["total_chapters"], len(payload["chapters"]))
                self.assertEqual(payload["total_chapters"], len(payload["table_of_contents"]))


class _Parser:
    def process_chapter(self, chapter_index, book, db_dir, db, *args):
        return {"chapter": chapter_index, "major_events": [], "entities_present": [], "_metadata": {}}


class _Replay:
    def coordinator(self, db_dir):
        return self

    def replay(self, reason):
        return {"reason": reason}


class _FailingParser:
    def process_chapter(self, *args, **kwargs):
        from ai import PermanentAIError

        raise PermanentAIError("provider details must stay private", code="invalid_key")


class ReaderAnalysisCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def _wait_for(self, predicate, timeout=3):
        started = asyncio.get_running_loop().time()
        while not predicate():
            if asyncio.get_running_loop().time() - started > timeout:
                self.fail("reader analysis did not reach expected state")
            await asyncio.sleep(0.01)

    async def test_staging_is_invisible_until_completion_then_promotes(self):
        with tempfile.TemporaryDirectory() as root:
            db_dir = Path(root, "library", "Book", "Session", "database")
            db_dir.mkdir(parents=True)
            initial = BookDatabase(str(db_dir)); initial.close()
            sessions = SessionManager(str(Path(root, "state.json")))
            coordinator = ReaderAnalysisCoordinator(Path(root, "cache"), sessions, _Parser(), _Replay(), DatabaseRegistry())
            book = object()
            await coordinator.stage("Book::Session", 0, book, str(db_dir))
            await self._wait_for(lambda: coordinator.jobs[("Book::Session", 0)].state == "staged")
            canonical = BookDatabase(str(db_dir))
            self.assertIsNone(EvidenceStore.active_payload(canonical, 0))
            canonical.close()
            await coordinator.complete("Book::Session", 0, book, str(db_dir))
            self.assertEqual("committed", coordinator.jobs[("Book::Session", 0)].state)
            canonical = BookDatabase(str(db_dir))
            self.assertEqual(0, EvidenceStore.active_payload(canonical, 0)["chapter"])
            canonical.close()
            self.assertFalse(coordinator.jobs[("Book::Session", 0)].workspace.exists())
            await coordinator.shutdown()

    async def test_discard_removes_staged_payload_without_canonical_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            db_dir = Path(root, "library", "Book", "Session", "database")
            db_dir.mkdir(parents=True)
            initial = BookDatabase(str(db_dir)); initial.close()
            coordinator = ReaderAnalysisCoordinator(
                Path(root, "cache"), SessionManager(str(Path(root, "state.json"))),
                _Parser(), _Replay(), DatabaseRegistry(),
            )
            await coordinator.stage("Book::Session", 0, object(), str(db_dir))
            await self._wait_for(lambda: coordinator.jobs[("Book::Session", 0)].state == "staged")
            await coordinator.cancel("Book::Session", 0)
            self.assertEqual("cancelled", coordinator.jobs[("Book::Session", 0)].state)
            self.assertFalse(coordinator.jobs[("Book::Session", 0)].workspace.exists())
            canonical = BookDatabase(str(db_dir))
            self.assertIsNone(EvidenceStore.active_payload(canonical, 0))
            canonical.close()
            await coordinator.shutdown()

    async def test_failure_exposes_normalized_code_not_exception_class(self):
        with tempfile.TemporaryDirectory() as root:
            db_dir = Path(root, "library", "Book", "Session", "database")
            db_dir.mkdir(parents=True)
            coordinator = ReaderAnalysisCoordinator(
                Path(root, "cache"), SessionManager(str(Path(root, "state.json"))),
                _FailingParser(), _Replay(), DatabaseRegistry(),
            )
            await coordinator.stage("Book::Session", 0, object(), str(db_dir))
            await self._wait_for(lambda: coordinator.jobs[("Book::Session", 0)].state == "error")
            public = coordinator.jobs[("Book::Session", 0)].public()
            self.assertEqual("invalid_key", public["error_code"])
            self.assertNotIn("PermanentAIError", str(public))
            self.assertNotIn("provider details", str(public))
            await coordinator.shutdown()


if __name__ == "__main__":
    unittest.main()
