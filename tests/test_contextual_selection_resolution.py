import tempfile
import unittest

from db_manager import BookDatabase
from dictionary_subsystem.classification import SelectionClassifier
from dictionary_subsystem.models import HighlightRequest, ServiceResult
from dictionary_subsystem.service import HighlightResolver


class SpyDictionary:
    def __init__(self):
        self.calls = []

    def lookup(self, term, language="en", pos_hint=None):
        self.calls.append((term, language, pos_hint))
        return ServiceResult("ok", {"lemma": str(term).lower(), "part_of_speech": pos_hint, "senses": [{"synset_id": "test-1", "pos": "n", "definition": "test definition"}]}, "fake_dictionary", "1")


class SpyPronunciation:
    def __init__(self):
        self.calls = []

    def lookup(self, term, language="en"):
        self.calls.append((term, language))
        return ServiceResult("ok", {"variants": []}, "fake_pronunciation", "1")


class FakeContext:
    def __init__(self):
        self.calls = []

    def resolve(self, term, sentence, language="en", allow_ai=False):
        self.calls.append((term, sentence, language, allow_ai))
        return ServiceResult("ok", {"meaning": "meaning in context", "confidence": 0.8}, "fake_context", "1")


class ContextualSelectionResolutionTests(unittest.TestCase):
    def test_function_words_classify_before_and_skip_downstream_services(self):
        dictionary, pronunciation, context = SpyDictionary(), SpyPronunciation(), FakeContext()
        response = HighlightResolver(None, dictionary, pronunciation, context).resolve(
            HighlightRequest(0, "I", sentence_text="I went home.", context_text="I went home.", knowledge_as_of_chapter=-1, explain_function_words=False)
        )
        self.assertEqual("pronoun", response["resolution"]["classification"]["primary_class"])
        self.assertEqual("suppress_popup", response["routing"]["popup_action"])
        self.assertEqual([], dictionary.calls)
        self.assertEqual([], pronunciation.calls)
        self.assertEqual([], context.calls)

    def test_function_word_suppression_is_the_default_and_grammar_is_opt_in(self):
        response = HighlightResolver(None, SpyDictionary(), SpyPronunciation(), FakeContext()).resolve(
            HighlightRequest(0, "I", sentence_text="I waited.", context_text="I waited.", knowledge_as_of_chapter=-1)
        )
        self.assertEqual("suppress_popup", response["routing"]["popup_action"])
        grammar = HighlightResolver(None, SpyDictionary(), SpyPronunciation(), FakeContext()).resolve(
            HighlightRequest(0, "I", sentence_text="I waited.", context_text="I waited.", knowledge_as_of_chapter=-1, explain_function_words=True)
        )
        self.assertEqual("show_popup", grammar["routing"]["popup_action"])
        self.assertEqual("deterministic_grammar", grammar["context"]["source"])
        self.assertEqual("A first-person singular pronoun used in this sentence.", grammar["context"]["meaning"])
        self.assertEqual("not_applicable", grammar["general_dictionary"]["status"])

    def test_case_and_irregular_morphology_are_preserved(self):
        resolver = HighlightResolver(None, SpyDictionary(), SpyPronunciation(), FakeContext())
        cases = [("US", "US helps allies.", "US"), ("running", "She was running home.", "run"), ("reappeared", "He reappeared.", "reappear"), ("children", "The children laughed.", "child"), ("mice", "The mice fled.", "mouse")]
        for selected, sentence, lemma in cases:
            with self.subTest(selected=selected):
                response = resolver.resolve(HighlightRequest(0, selected, sentence_text=sentence, context_text=sentence, knowledge_as_of_chapter=-1))
                self.assertEqual(selected, response["query"]["forms"]["original"])
                self.assertEqual(lemma, response["query"]["lemma"])

    def test_context_sensitive_language_nationality_and_adjective(self):
        resolver = HighlightResolver(None, SpyDictionary(), SpyPronunciation(), FakeContext())
        cases = [("He spoke French.", "language"), ("The French army advanced.", "nationality"), ("French doors opened.", "adjective")]
        for sentence, expected in cases:
            with self.subTest(sentence=sentence):
                response = resolver.resolve(HighlightRequest(0, "French", sentence_text=sentence, context_text=sentence, knowledge_as_of_chapter=-1))
                self.assertEqual(expected, response["resolution"]["classification"]["primary_class"])

    def test_context_can_override_overeager_organization_ner(self):
        resolver = HighlightResolver(None, SpyDictionary(), SpyPronunciation(), FakeContext())
        cases = [("Apple tasted sweet.", "Apple", "object"), ("Apple announced a product.", "Apple", "organization"), ("Amazon flooded its banks.", "Amazon", "named_place"), ("Amazon announced earnings.", "Amazon", "organization")]
        for sentence, selected, expected in cases:
            with self.subTest(sentence=sentence):
                response = resolver.resolve(HighlightRequest(0, selected, sentence_text=sentence, context_text=sentence, knowledge_as_of_chapter=-1))
                self.assertEqual(expected, response["resolution"]["classification"]["primary_class"])

    def test_sentence_offsets_are_validated_in_their_own_text_space(self):
        with self.assertRaisesRegex(ValueError, "sentence selection bounds exceed sentence"):
            HighlightResolver(None).resolve(HighlightRequest(0, "word", sentence_text="A word.", sentence_selection_start=2, sentence_selection_end=20, knowledge_as_of_chapter=-1))

    def test_story_visibility_respects_knowledge_boundary_and_lookup_is_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            db = BookDatabase(root)
            entity_id = db.add_entity("Ariadne Vale", "PERSON", 2)
            before = db._get_connection().execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            hidden = HighlightResolver(db, SpyDictionary(), SpyPronunciation(), FakeContext()).resolve(HighlightRequest(3, "Ariadne Vale", sentence_text="Ariadne Vale entered.", context_text="Ariadne Vale entered.", knowledge_as_of_chapter=1))
            visible = HighlightResolver(db, SpyDictionary(), SpyPronunciation(), FakeContext()).resolve(HighlightRequest(3, "Ariadne Vale", sentence_text="Ariadne Vale entered.", context_text="Ariadne Vale entered.", knowledge_as_of_chapter=2))
            after = db._get_connection().execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            self.assertFalse(hidden["routing"]["story_object_match"])
            self.assertTrue(visible["routing"]["story_object_match"])
            self.assertEqual(entity_id, visible["routing"]["object_id"])
            self.assertEqual(before, after)
            db.close()

    def test_classifier_prefers_grammar_over_symbol_shapes(self):
        classifier = SelectionClassifier()
        base = {"forms": {"original": "I"}, "tag": "PRP", "dependency": "nsubj", "entity_type": "", "nearby_nouns": ["iodine"]}
        self.assertEqual("pronoun", classifier.classify({**base, "pos": "PRON"})["primary_class"])
        self.assertEqual("roman_numeral", classifier.classify({**base, "pos": "PROPN", "nearby_nouns": []})["primary_class"])

    def test_story_homonym_requires_context_and_case_eligibility(self):
        with tempfile.TemporaryDirectory() as root:
            db = BookDatabase(root)
            db.add_entity("Bill", "PERSON", 0)
            resolver = HighlightResolver(db, SpyDictionary(), SpyPronunciation(), FakeContext())
            invoice = resolver.resolve(HighlightRequest(1, "bill", sentence_text="He paid the bill.", context_text="He paid the bill.", knowledge_as_of_chapter=0))
            person = resolver.resolve(HighlightRequest(1, "Bill", sentence_text="Bill arrived early.", context_text="Bill arrived early.", knowledge_as_of_chapter=0))
            self.assertFalse(invoice["routing"]["story_object_match"])
            self.assertEqual("context_or_case_mismatch", invoice["story_glossary"]["reason"])
            self.assertTrue(person["routing"]["story_object_match"])
            db.close()

    def test_reported_gatsby_contexts_resolve_without_homonym_fallthrough(self):
        resolver = HighlightResolver(None)
        cases = [
            ("Daisy", "The other girl, Daisy, made an attempt to rise—she leaned slightly forward."),
            ("boom", "Then there was a boom as Tom Buchanan shut the rear windows and the caught wind died out."),
            ("rise", "The other girl, Daisy, made an attempt to rise—she leaned slightly forward."),
            ("Buccleuch", "The Carraways are something of a clan and we have a tradition that we’re descended from the Dukes of Buccleuch."),
            ("contemptuously", "You live in West Egg, she remarked contemptuously."),
        ]
        results = {term: resolver.resolve(HighlightRequest(0, term, sentence_text=sentence, context_text=sentence, paragraph_text=sentence, sentence_selection_start=0, sentence_selection_end=min(len(term), len(sentence)), knowledge_as_of_chapter=-1)) for term, sentence in cases}
        self.assertEqual("named_person", results["Daisy"]["resolution"]["classification"]["primary_class"])
        self.assertIn("a person", results["Daisy"]["context"]["meaning"])
        self.assertEqual("not_applicable", results["Daisy"]["general_dictionary"]["status"])
        self.assertIn("loud noise", results["boom"]["context"]["meaning"])
        self.assertNotIn("pole", results["boom"]["context"]["meaning"])
        self.assertEqual("verb", results["rise"]["resolution"]["classification"]["primary_class"])
        self.assertEqual("rise", results["rise"]["query"]["lemma"])
        self.assertIn("move upward", results["rise"]["context"]["meaning"])
        self.assertEqual("not_applicable", results["Buccleuch"]["general_dictionary"]["status"])
        self.assertIn("named title or reference", results["Buccleuch"]["context"]["meaning"])
        self.assertEqual("adverb", results["contemptuously"]["general_dictionary"]["part_of_speech"])


if __name__ == "__main__":
    unittest.main()
