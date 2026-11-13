from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from ai.models import GenerationResult
from app import create_app
from config import load_config
from db_manager import BookDatabase
from epub_test_fixture import build_image_fixture
from reader_search import ReaderSearchService
import reader_knowledge


class _Chapter:
    def __init__(self, index, title, content):
        self.index, self.title, self.content, self.spine_href = index, title, content, f"c{index}.xhtml"


class _Book:
    def __init__(self, chapters):
        self.chapters = chapters


def seed_graph(db_dir: str) -> dict[str, int]:
    db = BookDatabase(db_dir)
    person = {"entity_category": "CHARACTER", "sentience": "true", "can_form_relationships": "true"}
    aster = db.add_entity("Aster", "INDIVIDUAL", 0, ontology=person)
    beryl = db.add_entity("Beryl", "INDIVIDUAL", 0, ontology=person)
    villain = db.add_entity("Corvin", "INDIVIDUAL", 2, ontology=person)
    meeting = db.add_event(0, "Aster meets Beryl at the harbor.", 0)
    db.add_event_participant(meeting, aster)
    db.add_event_participant(meeting, beryl)
    betrayal = db.add_event(2, "Corvin betrays Aster.", 0)
    db.add_event_participant(betrayal, villain)
    db.add_event_participant(betrayal, aster)
    db.add_relationship_event(aster, beryl, 0, 4, "They share a meal.")
    db.add_relationship_event(villain, aster, 2, -6, "Corvin sells the map.")
    db.close()
    return {"aster": aster, "beryl": beryl, "corvin": villain}


class ReaderKnowledgeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.db_dir = str(Path(self.root.name, "database"))
        Path(self.db_dir).mkdir()
        self.ids = seed_graph(self.db_dir)

    def overview(self, chapter):
        db = BookDatabase(self.db_dir)
        try:
            return reader_knowledge.build_overview(db, chapter)
        finally:
            db.close()

    def test_overview_hides_everything_after_the_boundary(self):
        early = self.overview(1)
        self.assertTrue(early["available"])
        self.assertEqual({"Aster", "Beryl"}, {item["name"] for item in early["entities"]})
        self.assertEqual(["Aster meets Beryl at the harbor."], [item["summary"] for item in early["timeline"]])
        self.assertEqual(1, len(early["relationships"]))
        self.assertNotIn("Corvin", str(early))

        later = self.overview(2)
        self.assertIn("Corvin", {item["name"] for item in later["entities"]})
        self.assertEqual(2, len(later["timeline"]))
        self.assertEqual(2, len(later["relationships"]))
        aster = next(item for item in later["entities"] if item["name"] == "Aster")
        self.assertEqual(2, aster["event_count"])
        self.assertTrue(aster["is_person"])

    def test_placeholder_entities_are_hidden_from_the_reader(self):
        db = BookDatabase(self.db_dir)
        placeholder = db.add_entity("[UNNAMED_POV]", "INDIVIDUAL", 0)
        event = db.add_event(0, "The narrator arrives in town.", 5)
        db.add_event_participant(event, placeholder)
        db.add_event_participant(event, self.ids["aster"])
        db.close()
        overview = self.overview(0)
        self.assertNotIn("[UNNAMED_POV]", {item["name"] for item in overview["entities"]})
        arrival = next(item for item in overview["timeline"] if item["summary"].startswith("The narrator"))
        self.assertEqual(["Aster"], [participant["name"] for participant in arrival["participants"]])
        self.assertTrue(reader_knowledge.is_placeholder_entity("[UNNAMED_POV]"))
        self.assertTrue(reader_knowledge.is_placeholder_entity("Unnamed narrator"))
        self.assertFalse(reader_knowledge.is_placeholder_entity("Aster Vale"))

    def test_nothing_is_known_before_the_first_finished_chapter(self):
        self.assertFalse(self.overview(-1)["available"])

    def test_chat_context_only_uses_read_passages_and_known_facts(self):
        search = ReaderSearchService(self.root.name)
        search.index_book("Book::Reading", _Book([
            _Chapter(0, "One", "Aster walked to the harbor and met Beryl."),
            _Chapter(1, "Two", "Beryl taught Aster to sail."),
            _Chapter(2, "Three", "Corvin betrayed Aster and stole the map."),
        ]))
        question = "What do we know about Aster and Corvin?"
        passages = reader_knowledge.retrieve_passages(search, "Book::Reading", question, 1)
        self.assertTrue(passages)
        self.assertTrue(all(item["chapter_index"] <= 1 for item in passages))
        prompt = reader_knowledge.build_chat_prompt(
            book_title="Fixture", question="What do we know about Aster?",
            history=[{"role": "user", "text": "Hello"}],
            as_of_chapter=1, overview=self.overview(1), passages=passages,
        )
        self.assertIn("Aster meets Beryl", prompt)
        self.assertIn("finished chapters 1 to 2", prompt)
        self.assertNotIn("betray", prompt.lower())
        self.assertNotIn("stole the map", prompt)
        self.assertNotIn("Corvin", prompt)
        self.assertEqual([], reader_knowledge.retrieve_passages(search, "Book::Reading", question, -1))


class ReaderKnowledgeApiTests(unittest.TestCase):
    def config(self, root):
        return load_config(root, {
            "BOOKBUDDY_LIBRARY_DIR": "library", "BOOKBUDDY_CACHE_DIR": "cache", "BOOKBUDDY_LOG_DIR": "logs",
            "BOOKBUDDY_CONFIG_DIR": "config",
        })

    def test_knowledge_and_chat_routes(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = build_image_fixture(Path(root, "fixture.epub"))
            with TestClient(create_app(self.config(root))) as client:
                uploaded = client.post(
                    "/upload", files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")},
                    data={"session_name": "Reader"},
                )
                self.assertEqual(200, uploaded.status_code, uploaded.text)
                identity = uploaded.json()
                base = f"/reader/{identity['book_name']}/{identity['session_name']}"

                empty = client.get(f"{base}/knowledge", params={"as_of_chapter": 0})
                self.assertEqual(200, empty.status_code, empty.text)
                self.assertEqual("bookbuddy_reader_knowledge_v1", empty.json()["schema_version"])
                self.assertFalse(empty.json()["available"])
                missing = client.get("/reader/Missing/Nope/knowledge", params={"as_of_chapter": 0})
                self.assertEqual(404, missing.status_code)

                db_dir = Path(root, "library", identity["book_name"], identity["session_name"], "database")
                seed_graph(str(db_dir))
                seeded = client.get(f"{base}/knowledge", params={"as_of_chapter": 0}).json()
                self.assertTrue(seeded["available"])
                self.assertNotIn("Corvin", str(seeded))

                import app as app_module
                manager = app_module.ai_manager
                with mock.patch.object(manager, "is_available", return_value=False):
                    offline = client.post(f"{base}/chat", json={"question": "Who is Aster?", "as_of_chapter": 0})
                    self.assertEqual(503, offline.status_code, offline.text)
                captured = {}

                def fake_generate(request):
                    captured["prompt"] = request.prompt
                    return GenerationResult(text="Aster met Beryl at the harbor.", provider="fake", model="fake", credential_id="x")

                with mock.patch.object(manager, "is_available", return_value=True), \
                        mock.patch.object(manager, "generate", side_effect=fake_generate):
                    answered = client.post(f"{base}/chat", json={"question": "Who is Aster?", "as_of_chapter": 0})
                    self.assertEqual(200, answered.status_code, answered.text)
                    self.assertEqual("Aster met Beryl at the harbor.", answered.json()["answer"])
                    self.assertTrue(answered.json()["grounding"]["story_knowledge"])
                    self.assertNotIn("Corvin", captured["prompt"])
                    too_far = client.post(f"{base}/chat", json={"question": "Who?", "as_of_chapter": 9999})
                    self.assertEqual(422, too_far.status_code)


if __name__ == "__main__":
    unittest.main()
