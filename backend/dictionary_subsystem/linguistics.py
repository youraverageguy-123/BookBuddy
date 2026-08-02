from __future__ import annotations

import re
import threading
import os
from pathlib import Path
from typing import Any

from .models import ContextWindow, HighlightRequest
from .terminology import normalize_term


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class LinguisticAnalyzer:
    """Optional spaCy-backed analysis that never changes the raw selection."""

    _nlp = None
    _load_attempted = False
    _load_failure_reason = ""
    _lock = threading.Lock()

    @classmethod
    def _pipeline(cls):
        if cls._load_attempted:
            return cls._nlp
        with cls._lock:
            if cls._load_attempted:
                return cls._nlp
            cls._load_attempted = True
            try:
                import spacy
                try:
                    cls._nlp = spacy.load("en_core_web_sm")
                except OSError:
                    # PyInstaller bundles the model package and its data, but
                    # a one-file executable does not retain the wheel metadata
                    # spaCy uses to discover installed pipeline packages.
                    # Loading through the package keeps the frozen and source
                    # runtimes behaviorally equivalent.
                    import en_core_web_sm

                    cls._nlp = en_core_web_sm.load()
            except (ImportError, OSError) as exc:
                cls._nlp = None
                cls._load_failure_reason = f"{type(exc).__name__}: {exc}"
                diagnostic_path = os.environ.get("BOOKBUDDY_DIAGNOSTIC_LOG")
                if diagnostic_path:
                    try:
                        with Path(diagnostic_path).open("a", encoding="utf-8") as handle:
                            handle.write(f"linguistics:model_unavailable:{cls._load_failure_reason}\n")
                    except OSError:
                        pass
        return cls._nlp

    @classmethod
    def warmup(cls) -> bool:
        """Load the optional local model before the first reader selection."""
        return cls._pipeline() is not None

    @staticmethod
    def build_context(request: HighlightRequest, chapter_text: str = "") -> ContextWindow:
        sentence = request.sentence_text or request.context_text or ""
        paragraph = request.paragraph_text or request.context_text or sentence
        previous, following = request.previous_sentence or "", request.next_sentence or ""
        start, end = request.sentence_selection_start, request.sentence_selection_end

        if not sentence and chapter_text:
            selected = request.selected_text.strip()
            if request.selection_start is not None and request.selection_end is not None:
                chapter_start, chapter_end = request.selection_start, request.selection_end
            else:
                match = re.search(re.escape(selected), chapter_text)
                if match is None:
                    match = re.search(re.escape(selected), chapter_text, flags=re.IGNORECASE)
                chapter_start, chapter_end = match.span() if match else (0, 0)
            left = max(chapter_text.rfind(mark, 0, chapter_start) for mark in (".", "!", "?", "\n")) + 1
            rights = [chapter_text.find(mark, chapter_end) for mark in (".", "!", "?", "\n")]
            rights = [value for value in rights if value >= 0]
            right = min(rights) + 1 if rights else min(len(chapter_text), chapter_end + 500)
            sentence = chapter_text[left:right].strip()
            paragraph = sentence
            start = max(0, chapter_start - left)
            end = max(start, chapter_end - left)

        if sentence and (not previous or not following) and paragraph:
            parts = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
            selected = request.selected_text.strip()
            index = next((i for i, part in enumerate(parts) if sentence.strip() == part), -1)
            if index < 0:
                index = next((i for i, part in enumerate(parts) if selected in part), -1)
            if index >= 0:
                sentence = parts[index]
                previous = previous or (parts[index - 1] if index > 0 else "")
                following = following or (parts[index + 1] if index + 1 < len(parts) else "")

        return ContextWindow(sentence, previous, following, paragraph, start, end)

    def analyze(self, request: HighlightRequest, window: ContextWindow) -> dict[str, Any]:
        original = request.selected_text
        surface = original.strip()
        forms = {
            "original": original,
            "lower": surface.lower(),
            "normalized": normalize_term(surface),
            "lemma": normalize_term(surface),
        }
        casing = {
            "is_upper": surface.isupper(),
            "is_title": surface.istitle(),
            "is_lower": surface.islower(),
            "is_mixed": bool(surface) and not (surface.isupper() or surface.istitle() or surface.islower()),
        }
        fallback = {
            "provider": "deterministic_fallback",
            "confidence": 0.35,
            "forms": forms,
            "casing": casing,
            "tokens": [{"text": surface, "lemma": forms["lemma"], "pos": "", "tag": "", "dependency": "", "entity_type": ""}],
            "lemma": forms["lemma"], "pos": "", "tag": "", "dependency": "", "entity_type": "",
            "number": None, "person": None, "tense": None, "possessive": surface.endswith("'s"), "derivation": None,
            "nearby_nouns": [], "nearby_verbs": [], "nearby_adjectives": [],
            "context_terms": sorted(set(re.findall(r"[^\W\d_]+", f"{window.surrounding_text} {window.paragraph}".casefold(), flags=re.UNICODE))),
        }
        nlp = self._pipeline()
        if nlp is None or not window.sentence:
            return fallback
        doc = nlp(window.sentence)
        span_tokens = self._selected_tokens(doc, surface, window.selection_start, window.selection_end)
        if not span_tokens:
            return fallback
        head = next((token for token in span_tokens if token.head not in span_tokens), span_tokens[0])
        lemmas = [token.lemma_ if token.lemma_ and token.lemma_ != "-PRON-" else token.text for token in span_tokens]
        lemma = " ".join(lemmas).strip()
        forms["lemma"] = lemma if lemma == surface and any(char.isupper() for char in surface) else lemma.lower()
        entity = next((ent.label_ for ent in doc.ents if any(token.i >= ent.start and token.i < ent.end for token in span_tokens)), "")
        morph = head.morph.to_dict()
        governor = head.head if head.head not in span_tokens else None
        return {
            "provider": "spacy", "confidence": 0.9, "forms": forms, "casing": casing,
            "tokens": [{"text": token.text, "lemma": token.lemma_, "pos": token.pos_, "tag": token.tag_, "dependency": token.dep_, "entity_type": token.ent_type_} for token in span_tokens],
            "lemma": forms["lemma"], "pos": head.pos_, "tag": head.tag_, "dependency": head.dep_, "entity_type": entity,
            "governor_lemma": governor.lemma_ if governor is not None else "", "governor_pos": governor.pos_ if governor is not None else "",
            "number": morph.get("Number"), "person": morph.get("Person"), "tense": morph.get("Tense"),
            "possessive": morph.get("Poss") == "Yes" or surface.endswith("'s"),
            "derivation": "inflected" if forms["lemma"].casefold() != surface.casefold() else None,
            "nearby_nouns": [token.lemma_ for token in doc if token.pos_ in {"NOUN", "PROPN"} and token not in span_tokens][:8],
            "nearby_verbs": [token.lemma_ for token in doc if token.pos_ in {"VERB", "AUX"} and token not in span_tokens][:8],
            "nearby_adjectives": [token.lemma_ for token in doc if token.pos_ == "ADJ" and token not in span_tokens][:8],
            "context_terms": sorted(set(re.findall(r"[^\W\d_]+", f"{window.surrounding_text} {window.paragraph}".casefold(), flags=re.UNICODE))),
        }

    @staticmethod
    def _selected_tokens(doc, surface: str, start: int | None, end: int | None):
        if start is not None and end is not None and 0 <= start < end <= len(doc.text):
            span = doc.char_span(start, end, alignment_mode="expand")
            if span is not None and span.text.strip().casefold() == surface.casefold():
                return list(span)
        exact = re.search(re.escape(surface), doc.text)
        if exact is None:
            exact = re.search(re.escape(surface), doc.text, flags=re.IGNORECASE)
        if exact is None:
            return []
        span = doc.char_span(*exact.span(), alignment_mode="expand")
        return list(span) if span is not None else []
