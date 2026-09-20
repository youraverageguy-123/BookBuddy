import tempfile
import unittest
from pathlib import Path

from db_manager import BookDatabase
from dictionary_subsystem.models import HighlightRequest, ServiceResult
from dictionary_subsystem.reader_state import ReaderKnowledgeStore
from dictionary_subsystem.service import HighlightResolver
from dictionary_subsystem.providers import EnglishWordNetProvider
from dictionary_subsystem.models import KnowledgeObjectRef
from dictionary_subsystem.terminology import GlossaryResolver, TerminologyDiscovery, TerminologyResolver


class FakeDictionary:
    def lookup(self, term, language="en", pos_hint=None):
        return ServiceResult("ok", {"lemma": term.lower(), "senses": [{"definition": "a test meaning"}]}, "fake", "1")


class FakePronunciation:
    def lookup(self, term, language="en"):
        return ServiceResult("ok", {"variants": [{"ipa": "/test/"}]}, "fake", "1")


class FakeContext:
    def resolve(self, term, sentence, language="en", allow_ai=False):
        return ServiceResult("ok", {"meaning": "meaning in context", "source": "deterministic"}, "fake", "1")


class DictionarySubsystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = BookDatabase(self.temp.name)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_terminology_requires_independent_chapters_and_is_chapter_safe(self):
        discovery = TerminologyDiscovery(self.db)
        discovery.process(1, "He activated gravBoots.")
        self.assertEqual("candidate", self.db._get_connection().execute("SELECT status FROM terminology_objects").fetchone()[0])
        discovery.process(2, "The gravBoots carried her.")
        self.assertEqual("confirmed", self.db._get_connection().execute("SELECT status FROM terminology_objects").fetchone()[0])
        result = GlossaryResolver(self.db).lookup("grav", 1)
        self.assertEqual("not_found", result.status)
        result = GlossaryResolver(self.db).lookup("grav", 2)
        self.assertEqual("ok", result.status)
        self.assertFalse(result.data["definition"]["stored"])

    def test_highlight_composes_independent_sections_and_routes_knowledge_object(self):
        discovery = TerminologyDiscovery(self.db)
        discovery.process(1, "He activated gravBoots.")
        discovery.process(2, "The gravBoots carried her.")
        response = HighlightResolver(self.db, FakeDictionary(), FakePronunciation(), FakeContext()).resolve(
            HighlightRequest(2, "gravBoots", context_text="The gravBoots carried her.")
        )
        self.assertEqual("story_glossary", response["routing"]["primary"])
        self.assertEqual("ok", response["general_dictionary"]["status"])
        self.assertEqual("ok", response["pronunciation"]["status"])
        self.assertEqual("ok", response["context"]["status"])

    def test_highlight_without_graph_keeps_independent_services_available(self):
        response = HighlightResolver(
            None, FakeDictionary(), FakePronunciation(), FakeContext()
        ).resolve(HighlightRequest(0, "world", context_text="The world was quiet."))
        self.assertEqual("unavailable", response["story_glossary"]["status"])
        self.assertEqual("graph_not_committed", response["story_glossary"]["reason"])
        self.assertEqual("ok", response["general_dictionary"]["status"])
        self.assertEqual("ok", response["context"]["status"])
        self.assertEqual("ok", response["pronunciation"]["status"])

    def test_wordnet_resolves_inflected_reader_selection(self):
        result = EnglishWordNetProvider().lookup("answered")
        self.assertEqual("ok", result.status)
        self.assertEqual("answer", result.data["lemma"])
        self.assertTrue(result.data["senses"])

    def test_wordnet_recovers_when_context_pos_hint_is_wrong(self):
        result = EnglishWordNetProvider().lookup("darkness", pos_hint="verb")
        self.assertEqual("ok", result.status)
        self.assertTrue(result.data["senses"])

    def test_canonical_fact_rejects_image_only_evidence(self):
        discovery = TerminologyDiscovery(self.db)
        discovery.process(1, "He activated gravBoots.")
        discovery.process(2, "The gravBoots carried her.")
        term_id = self.db._get_connection().execute("SELECT id FROM terminology_objects").fetchone()[0]
        image_evidence = self.db._get_connection().execute("""INSERT INTO terminology_evidence
            (term_id, chapter, source_type, payload_json, confidence) VALUES (?, 2, 'image', '{}', 0.9)""", (term_id,))
        self.db._get_connection().commit()
        with self.assertRaisesRegex(ValueError, "deterministic text evidence"):
            TerminologyResolver(self.db).record_function(term_id, "mobility", "enhanced movement", 0.9, image_evidence.lastrowid)

    def test_reader_state_is_separate_and_profile_scoped(self):
        with tempfile.TemporaryDirectory() as reader_dir:
            path = Path(reader_dir) / "reader.db"
            store = ReaderKnowledgeStore(str(path))
            first, second = store.create_profile(), store.create_profile()
            store.record_view(first, "terminology", 4)
            store.set_flag(first, "terminology", 4, "marked_known")
            self.assertTrue(store.get(first, "terminology", 4)["marked_known"])
            self.assertEqual(0, store.get(second, "terminology", 4)["view_count"])
            self.assertFalse((Path(reader_dir) / "graph.db").exists())

    def test_reader_library_state_is_durable_monotonic_and_profile_scoped(self):
        with tempfile.TemporaryDirectory() as reader_dir:
            store = ReaderKnowledgeStore(str(Path(reader_dir) / "reader.db"))
            user_id = store.create_profile()
            store.upsert_book_state(user_id, "Book::Reading", {"favorite": True, "book_progress": 0.42, "last_cfi": "epubcfi(/6/2)"})
            first = store.upsert_chapter_progress(user_id, "Book::Reading", 2, {"last_cfi": "epubcfi(/6/2)", "current_progress": .96, "contiguous_progress": .96, "threshold_started": True, "naturally_completed": True, "retry_required": True})
            second = store.upsert_chapter_progress(user_id, "Book::Reading", 2, {"last_cfi": "epubcfi(/6/4)", "current_progress": .2, "contiguous_progress": .2, "committed": True})
            self.assertTrue(first["naturally_completed"])
            self.assertTrue(second["naturally_completed"])
            self.assertGreaterEqual(second["contiguous_progress"], .96)
            self.assertFalse(second["retry_required"])
            collection = store.create_collection(user_id, "Favorites from Mars")
            store.set_collection_member(user_id, collection["collection_id"], "Book::Reading", True)
            bookmark = store.create_bookmark(user_id, "Book::Reading", 2, "epubcfi(/6/4)", "  a   quiet  excerpt ")
            state = store.library_state(user_id)
            self.assertEqual(["Book::Reading"], state["smart_collections"]["favorites"])
            self.assertEqual(["Book::Reading"], state["collections"][0]["session_keys"])
            self.assertEqual("a quiet excerpt", state["bookmarks"][0]["excerpt"])
            store.delete_bookmark(user_id, bookmark["bookmark_id"])
            store.delete_collection(user_id, collection["collection_id"])

    def test_reader_metadata_overrides_and_collection_polish_are_additive(self):
        with tempfile.TemporaryDirectory() as root:
            store = ReaderKnowledgeStore(str(Path(root) / "reader.db"))
            user_id = store.create_profile()
            book = store.upsert_book_state(user_id, "Book::Reading", {"description_override": "Local synopsis", "rating": 4.5, "tags": ["space opera", "favorite"]})
            self.assertEqual("Local synopsis", book["description_override"])
            self.assertEqual(4.5, book["rating"])
            self.assertEqual(["space opera", "favorite"], book["tags"])
            collection = store.create_collection(user_id, "Long voyages", "Books for quiet weekends", True, "title")
            self.assertTrue(collection["pinned"])
            self.assertEqual("Books for quiet weekends", collection["description"])
            updated = store.update_collection(user_id, collection["collection_id"], description="Updated shelf", pinned=False)
            self.assertFalse(updated["pinned"])
            self.assertEqual("Updated shelf", updated["description"])


if __name__ == "__main__":
    unittest.main()
