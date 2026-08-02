from __future__ import annotations

import hashlib
import re
from typing import Callable, Protocol

from config import DICTIONARY_CACHE_SIZE, DICTIONARY_WSD_CONFIDENCE_THRESHOLD, DICTIONARY_WSD_MARGIN_THRESHOLD, WSD_CONTEXT_CUES

from .cache import LRUCache
from .models import ServiceResult


class ContextResolver(Protocol):
    def resolve(
        self,
        term: str,
        sentence: str,
        language: str = "en",
        allow_ai: bool = False,
        *,
        pos_hint: str | None = None,
        dictionary_result: ServiceResult | None = None,
    ) -> ServiceResult: ...


class WordNetContextResolver:
    provider = "wordnet_wsd"
    provider_version = "wsd_v2"

    def __init__(self, dictionary_provider, ai_fallback: Callable[[str, str], str | None] | None = None):
        self.dictionary = dictionary_provider
        self.ai_fallback = ai_fallback
        self.cache = LRUCache[ServiceResult](DICTIONARY_CACHE_SIZE)

    @staticmethod
    def _words(value: str) -> set[str]:
        stop = {"a", "an", "and", "as", "at", "be", "by", "for", "from", "he", "her", "his", "i", "in", "is", "it", "me", "my", "of", "on", "or", "our", "she", "that", "the", "their", "them", "they", "this", "to", "was", "we", "with", "you", "your", "gave", "have", "had", "one", "something", "somebody", "much", "lot"}
        return {word for word in re.findall(r"[^\W\d_]+", value.casefold(), flags=re.UNICODE) if len(word) > 2 and word not in stop}

    @staticmethod
    def _contextualize(term: str, definition: str) -> str:
        clean = " ".join(str(definition or "").strip().rstrip(".").split())
        return f"Here, “{term.strip()}” means {clean}." if clean else "No reliable contextual meaning was found."

    def resolve(
        self,
        term: str,
        sentence: str,
        language: str = "en",
        allow_ai: bool = False,
        *,
        pos_hint: str | None = None,
        dictionary_result: ServiceResult | None = None,
    ) -> ServiceResult:
        if not sentence:
            return ServiceResult("unavailable", {"reason": "context_missing"}, self.provider, self.provider_version)
        key = hashlib.sha256(f"{language}|{term.casefold()}|{sentence.strip().casefold()}|{pos_hint}|{allow_ai}|{self.provider_version}".encode()).hexdigest()
        cached = self.cache.get(key)
        if cached:
            return cached
        dictionary = dictionary_result or self.dictionary.lookup(term, language, pos_hint)
        senses = dictionary.data.get("senses", []) if dictionary.status == "ok" else []
        if not senses:
            return self.cache.put(key, ServiceResult("not_found", {"confidence": 0.0, "reason": "dictionary_senses_unavailable"}, self.provider, self.provider_version))

        context_words = self._words(sentence) - self._words(term)
        context_cues = {name for name, terms in WSD_CONTEXT_CUES.items() if context_words & set(terms)}
        scored = []
        for index, sense in enumerate(senses):
            signature = self._words(" ".join([
                str(sense.get("definition", "")),
                *(sense.get("examples") or []),
                *(sense.get("synonyms") or []),
            ])) - self._words(term)
            direct_overlap = len(context_words & signature)
            sense_cues = {name for name, terms in WSD_CONTEXT_CUES.items() if signature & set(terms)}
            cue_overlap = len(context_cues & sense_cues)
            frequency_prior = max(0.0, 0.12 - index * 0.015)
            score = direct_overlap * 0.55 + cue_overlap * 0.35 + frequency_prior
            scored.append((score, sense, {"direct_overlap": direct_overlap, "cue_overlap": cue_overlap, "frequency_prior": frequency_prior}))
        scored.sort(key=lambda item: item[0], reverse=True)
        top_score = scored[0][0]
        margin = top_score - (scored[1][0] if len(scored) > 1 else 0.0)
        has_context_evidence = bool(scored[0][2]["direct_overlap"] or scored[0][2]["cue_overlap"])
        confidence = min(1.0, 0.4 + top_score * 0.5) if has_context_evidence else 0.4

        if allow_ai and self.ai_fallback and (confidence < DICTIONARY_WSD_CONFIDENCE_THRESHOLD or margin < DICTIONARY_WSD_MARGIN_THRESHOLD):
            meaning = self.ai_fallback(term, sentence)
            if meaning:
                return self.cache.put(key, ServiceResult("ok", {"meaning": meaning, "confidence": 0.45, "score_margin": margin, "source": "gemini_fallback"}, self.provider, self.provider_version))

        source = "deterministic_context" if has_context_evidence else "pos_frequency_fallback"
        result = ServiceResult(
            "ok",
            {
                "meaning": self._contextualize(term, scored[0][1].get("definition", "")),
                "sense": scored[0][1],
                "confidence": confidence,
                "score_margin": margin,
                "score_components": scored[0][2],
                "source": source,
            },
            self.provider,
            self.provider_version,
        )
        return self.cache.put(key, result)
