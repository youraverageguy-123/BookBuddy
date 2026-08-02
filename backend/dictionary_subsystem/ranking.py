from __future__ import annotations

from typing import Any
import re


class CandidateRanker:
    def rank(self, analysis: dict, classification: dict, glossary, dictionary) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if glossary.status == "ok":
            if glossary.data.get("ambiguous"):
                for candidate in glossary.data.get("candidates", []):
                    candidates.append(self._story(candidate, analysis, accepted=False))
            else:
                candidates.append(self._story(glossary.data, analysis, accepted=True))
        if dictionary.status == "ok":
            expected = self._wordnet_pos(classification.get("primary_class", ""))
            for index, sense in enumerate(dictionary.data.get("senses", [])[:8]):
                pos_agreement = 1.0 if not expected or sense.get("pos") == expected else 0.0
                signature = self._terms(" ".join([str(sense.get("definition", "")), *(sense.get("examples") or []), *(sense.get("synonyms") or [])]))
                context_terms = set(analysis.get("context_terms", [])) - self._terms(str(analysis.get("forms", {}).get("original", "")))
                context_similarity = len(signature & context_terms) / max(1, len(signature | context_terms))
                components = {"context_similarity": context_similarity, "pos_agreement": pos_agreement, "exact_case": 0.5, "lemma_agreement": 1.0, "ner_agreement": 0.0, "story_evidence": 0.0, "provider_confidence": max(0.2, 1.0 - index * 0.1)}
                score = 0.3 * context_similarity + 0.2 * pos_agreement + 0.1 * components["exact_case"] + 0.1 + 0.05 * components["provider_confidence"]
                candidates.append({"source": "general_dictionary", "candidate_id": sense.get("synset_id"), "label": sense.get("definition", ""), "score": round(score, 4), "score_components": components, "accepted": False, "rejection_reasons": [] if pos_agreement else ["part_of_speech_mismatch"]})
        candidates.sort(key=lambda item: (-item["score"], item["source"], str(item.get("candidate_id"))))
        return candidates

    @staticmethod
    def _story(data: dict, analysis: dict, accepted: bool) -> dict:
        canonical = str(data.get("canonical_name") or "")
        surface = str(analysis.get("forms", {}).get("original") or "").strip()
        exact_case = 1.0 if canonical == surface else 0.7 if canonical.casefold() == surface.casefold() else 0.3
        raw_confidence = data.get("confidence", 0.0)
        story_confidence = float(raw_confidence.get("existence", 0.0) if isinstance(raw_confidence, dict) else raw_confidence or 0.0)
        components = {"context_similarity": 0.5, "pos_agreement": 0.7, "exact_case": exact_case, "lemma_agreement": 1.0, "ner_agreement": 0.7 if analysis.get("entity_type") else 0.0, "story_evidence": story_confidence, "provider_confidence": story_confidence}
        score = min(1.0, 0.3 + 0.1 * exact_case + 0.3 * story_confidence + 0.1 * components["ner_agreement"])
        return {"source": "story_glossary", "candidate_id": data.get("object_id"), "label": canonical, "score": round(score, 4), "score_components": components, "accepted": accepted, "rejection_reasons": [] if accepted else ["ambiguous_story_match"]}

    @staticmethod
    def _wordnet_pos(primary_class: str) -> str:
        return {"verb": "v", "adjective": "a", "vocabulary": "n"}.get(primary_class, "")

    @staticmethod
    def _terms(value: str) -> set[str]:
        return set(re.findall(r"[^\W\d_]+", value.casefold(), flags=re.UNICODE))
