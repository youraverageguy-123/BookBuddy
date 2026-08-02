from __future__ import annotations

from config import CSRE_AMBIGUITY_MARGIN, DICTIONARY_MAX_CONTEXT_LENGTH, DICTIONARY_MAX_SELECTION_LENGTH, DICTIONARY_RESPONSE_VERSION

from .classification import FUNCTION_CLASSES, SelectionClassifier
from .context import WordNetContextResolver
from .linguistics import LinguisticAnalyzer
from .models import HighlightRequest, ServiceResult
from .providers import EnglishWordNetProvider, OfflinePronunciationProvider
from .ranking import CandidateRanker
from .terminology import GlossaryResolver, normalize_term

NAMED_CLASSES = {"named_person", "named_place", "organization", "title"}


class ResponseComposer:
    def compose(
        self,
        request: HighlightRequest,
        routing: dict,
        dictionary: ServiceResult,
        pronunciation: ServiceResult,
        context: ServiceResult,
        glossary: ServiceResult,
        analysis: dict,
        classification: dict,
        candidates: list[dict],
    ) -> dict:
        forms = analysis.get("forms", {})
        story_or_named = classification.get("primary_class") in NAMED_CLASSES
        lemma = (analysis.get("lemma") if story_or_named else dictionary.data.get("lemma")) or analysis.get("lemma") or normalize_term(request.selected_text)
        forms = {"original": request.selected_text, "lower": request.selected_text.strip().lower(), "lemma": lemma, "normalized": normalize_term(request.selected_text), **forms}
        resolution = {
            "schema_version": "csre_v1",
            "classification": classification,
            "morphology": {
                key: analysis.get(key)
                for key in ("lemma", "pos", "tag", "dependency", "governor_lemma", "governor_pos", "number", "person", "tense", "possessive", "derivation", "tokens")
            },
            "named_entity": {"label": analysis.get("entity_type") or None, "confidence": analysis.get("confidence", 0.0)},
            "route": {"primary": routing["primary"], "popup_action": routing["popup_action"], "suppression_reason": routing.get("suppression_reason")},
            "ranked_candidates": candidates,
            "display_order": ["contextual", "story", "general", "pronunciation"],
        }
        diagnostics = [
            {"stage": "linguistic_analysis", "provider": analysis.get("provider"), "confidence": analysis.get("confidence")},
            {"stage": "classification", "primary_class": classification.get("primary_class"), "evidence": classification.get("evidence", [])},
        ]
        return {
            "schema_version": DICTIONARY_RESPONSE_VERSION,
            "query": {
                "selected_text": request.selected_text,
                "normalized_text": normalize_term(request.selected_text),
                "lemma": lemma,
                "forms": forms,
                "language": request.language,
                "chapter_index": request.chapter_index,
                "knowledge_as_of_chapter": request.knowledge_as_of_chapter,
            },
            "routing": routing,
            "resolution": resolution,
            "context": context.to_dict(),
            "general_dictionary": dictionary.to_dict(),
            "story_glossary": glossary.to_dict(),
            "pronunciation": pronunciation.to_dict(),
            "diagnostics": diagnostics,
        }


class HighlightResolver:
    def __init__(self, db, dictionary=None, pronunciation=None, context=None, glossary=None, composer=None, linguistics=None, classifier=None, ranker=None):
        self.db = db
        self.dictionary = dictionary or EnglishWordNetProvider()
        self.pronunciation = pronunciation or OfflinePronunciationProvider()
        self.context = context or WordNetContextResolver(self.dictionary)
        self.glossary = glossary or (GlossaryResolver(db) if db is not None else None)
        self.composer = composer or ResponseComposer()
        self.linguistics = linguistics or LinguisticAnalyzer()
        self.classifier = classifier or SelectionClassifier()
        self.ranker = ranker or CandidateRanker()

    def resolve(self, request: HighlightRequest, chapter_text: str = "") -> dict:
        self._validate(request, chapter_text)
        window = self.linguistics.build_context(request, chapter_text)
        analysis = self.linguistics.analyze(request, window)
        knowledge_chapter = request.chapter_index if request.knowledge_as_of_chapter is None else request.knowledge_as_of_chapter

        # Story resolution is deliberately attempted before any general provider.
        glossary = (
            self._guard(lambda: self.glossary.lookup(request.selected_text, knowledge_chapter), "book_graph")
            if self.glossary is not None and knowledge_chapter >= 0
            else ServiceResult("unavailable", {"reason": "graph_not_committed"}, "book_graph", "knowledge_object_v1")
        )
        classification = self.classifier.classify(analysis, glossary)
        story_eligible = self._story_eligible(glossary, analysis, classification)
        primary_class = classification["primary_class"]
        suppressed = primary_class in FUNCTION_CLASSES and not request.explain_function_words

        if suppressed:
            dictionary = ServiceResult("not_applicable", {"reason": "function_word_suppressed", "lemma": analysis.get("lemma")}, "classification_router", "csre_v1")
            pronunciation = ServiceResult("not_applicable", {"reason": "function_word_suppressed"}, "classification_router", "csre_v1")
            context = ServiceResult("not_applicable", {"reason": "function_word_suppressed"}, "classification_router", "csre_v1")
        elif primary_class in FUNCTION_CLASSES:
            meaning = self.classifier.grammatical_explanation(primary_class, analysis)
            context = ServiceResult("ok", {"meaning": meaning, "confidence": classification["confidence"], "source": "deterministic_grammar"}, "selection_classifier", "csre_v1")
            dictionary = ServiceResult("not_applicable", {"reason": "grammatical_explanation"}, "classification_router", "csre_v1")
            pronunciation = ServiceResult("not_applicable", {"reason": "grammatical_explanation"}, "classification_router", "csre_v1")
        elif primary_class in NAMED_CLASSES:
            context = self._named_context(request.selected_text, primary_class, glossary if story_eligible else None)
            dictionary = ServiceResult("not_applicable", {"reason": "named_reference", "lemma": analysis.get("lemma")}, "classification_router", "csre_v1")
            pronunciation = self._guard(lambda: self.pronunciation.lookup(request.selected_text.strip(), request.language), "pronunciation")
        else:
            pos_hint = self._pos_hint(primary_class, analysis)
            dictionary = self._guard(lambda: self.dictionary.lookup(analysis.get("lemma") or request.selected_text, request.language, pos_hint), "dictionary")
            pronunciation = self._guard(lambda: self.pronunciation.lookup(analysis.get("lemma") or request.selected_text, request.language), "pronunciation")
            if len(normalize_term(request.selected_text).split()) > 1 and not window.sentence:
                context = ServiceResult("not_applicable", {"reason": "multiword_without_context"}, "wordnet_wsd", "wsd_v1")
            else:
                context = self._guard(lambda: self._resolve_context(request, window.surrounding_text or window.sentence, pos_hint, dictionary), "wordnet_wsd")
            if primary_class == "unknown" and context.status not in {"ok"}:
                context = ServiceResult("not_found", {"meaning": "No reliable explanation could be determined.", "confidence": 0.0, "source": "safe_fallback"}, "selection_classifier", "csre_v1")

        story_match = story_eligible
        candidates = self.ranker.rank(analysis, classification, glossary, dictionary)
        if not story_eligible:
            for candidate in candidates:
                if candidate["source"] == "story_glossary":
                    candidate["accepted"] = False
                    candidate["rejection_reasons"] = sorted(set([*candidate.get("rejection_reasons", []), "context_or_case_mismatch"]))
        ambiguous = bool(glossary.data.get("ambiguous"))
        if len(candidates) > 1 and abs(candidates[0]["score"] - candidates[1]["score"]) < CSRE_AMBIGUITY_MARGIN and candidates[0]["source"] == candidates[1]["source"]:
            ambiguous = True
            classification["ambiguous"] = True
        if suppressed:
            primary = "none"
        elif story_match:
            primary = "story_glossary"
        elif context.status == "ok":
            primary = "context"
        else:
            primary = "general_dictionary"
        routing = {
            "primary": primary,
            "story_object_match": story_match,
            "object_kind": glossary.data.get("object_kind") if story_match else None,
            "object_id": glossary.data.get("object_id") if story_match else None,
            "confidence": (glossary.data.get("confidence") or {}).get("existence") if story_match else classification.get("confidence"),
            "ambiguous": ambiguous,
            "popup_action": "suppress_popup" if suppressed else "show_popup",
            "suppression_reason": f"function_word:{primary_class}" if suppressed else None,
        }
        response_glossary = glossary
        if glossary.status == "ok" and not glossary.data.get("ambiguous") and not story_eligible:
            response_glossary = ServiceResult("not_found", {"reason": "context_or_case_mismatch", "candidates": []}, glossary.provider, glossary.provider_version)
        return self.composer.compose(request, routing, dictionary, pronunciation, context, response_glossary, analysis, classification, candidates)

    @staticmethod
    def _story_eligible(glossary: ServiceResult, analysis: dict, classification: dict) -> bool:
        if glossary.status != "ok" or glossary.data.get("ambiguous"):
            return False
        surface = str(analysis.get("forms", {}).get("original") or "").strip()
        names = [str(glossary.data.get("canonical_name") or ""), *[str(item.get("alias") or "") for item in glossary.data.get("aliases", [])]]
        exact_case = surface in names
        casefold_match = surface.casefold() in {name.casefold() for name in names if name}
        if casefold_match and not exact_case and analysis.get("pos") != "PROPN":
            return False
        category = str(glossary.data.get("category") or "").casefold()
        primary = classification.get("primary_class")
        if category in {"person", "character"} and primary not in {"named_person", "object"}:
            return False
        if primary in FUNCTION_CLASSES:
            return False
        return exact_case or casefold_match or bool(glossary.data.get("object_kind") == "terminology")

    @staticmethod
    def _pos_hint(primary_class: str, analysis: dict) -> str | None:
        linguistic = {"NOUN": "noun", "PROPN": "noun", "VERB": "verb", "AUX": "verb", "ADJ": "adjective", "ADV": "adverb"}.get(str(analysis.get("pos") or "").upper())
        return linguistic or {"verb": "verb", "adjective": "adjective", "vocabulary": "noun"}.get(primary_class)

    def _resolve_context(self, request: HighlightRequest, sentence: str, pos_hint: str | None, dictionary: ServiceResult) -> ServiceResult:
        try:
            return self.context.resolve(
                request.selected_text,
                sentence,
                request.language,
                request.allow_ai_fallback,
                pos_hint=pos_hint,
                dictionary_result=dictionary,
            )
        except TypeError:
            # Compatibility for injected v1 context providers.
            return self.context.resolve(request.selected_text, sentence, request.language, request.allow_ai_fallback)

    @staticmethod
    def _named_context(selected_text: str, primary_class: str, glossary: ServiceResult | None) -> ServiceResult:
        labels = {"named_person": "a person", "named_place": "a place", "organization": "an organization", "title": "a named title or reference"}
        surface = selected_text.strip()
        if glossary is not None and glossary.status == "ok":
            canonical = str(glossary.data.get("canonical_name") or surface)
            category = str(glossary.data.get("category") or labels.get(primary_class, "a story entity")).replace("_", " ")
            meaning = f"Here, “{surface}” refers to {canonical}, {category} in the story."
            source = "spoiler_safe_story_entity"
        else:
            meaning = f"Here, “{surface}” refers to {labels.get(primary_class, 'a named reference')} in this passage."
            source = "deterministic_named_reference"
        return ServiceResult("ok", {"meaning": meaning, "confidence": 0.8, "source": source}, "selection_classifier", "csre_v1")

    @staticmethod
    def _guard(call, provider: str) -> ServiceResult:
        try:
            return call()
        except Exception as exc:
            return ServiceResult("error", {"reason": type(exc).__name__}, provider, "")

    @staticmethod
    def _validate(request: HighlightRequest, chapter_text: str):
        if not request.selected_text.strip() or len(request.selected_text) > DICTIONARY_MAX_SELECTION_LENGTH or "\x00" in request.selected_text:
            raise ValueError("invalid selected_text")
        if request.chapter_index < 0:
            raise ValueError("invalid chapter_index")
        context_fields = ("context_text", "sentence_text", "previous_sentence", "next_sentence", "paragraph_text")
        for field in context_fields:
            value = getattr(request, field)
            if value and len(value) > DICTIONARY_MAX_CONTEXT_LENGTH:
                raise ValueError(f"{field} is too long")
        if request.selection_start is not None or request.selection_end is not None:
            if request.selection_start is None or request.selection_end is None or request.selection_start < 0 or request.selection_end <= request.selection_start:
                raise ValueError("invalid selection bounds")
            if chapter_text and request.selection_end > len(chapter_text):
                raise ValueError("selection bounds exceed chapter")
        if request.sentence_selection_start is not None or request.sentence_selection_end is not None:
            start, end = request.sentence_selection_start, request.sentence_selection_end
            if start is None or end is None or start < 0 or end <= start:
                raise ValueError("invalid sentence selection bounds")
            sentence = request.sentence_text or request.context_text or ""
            if sentence and end > len(sentence):
                raise ValueError("sentence selection bounds exceed sentence")
