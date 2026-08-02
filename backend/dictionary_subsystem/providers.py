from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Protocol

from config import DICTIONARY_CACHE_SIZE, DICTIONARY_RESPONSE_VERSION

from .cache import LRUCache
from .models import ServiceResult


class DictionaryProvider(Protocol):
    def lookup(self, term: str, language: str = "en", pos_hint: str | None = None) -> ServiceResult: ...


class PronunciationProvider(Protocol):
    def lookup(self, term: str, language: str = "en") -> ServiceResult: ...


class EnglishWordNetProvider:
    provider = "open_english_wordnet"
    provider_version = "oewn-via-wn"

    def __init__(self, cache_size: int = DICTIONARY_CACHE_SIZE):
        self.cache = LRUCache[ServiceResult](cache_size)
        self._nlp = None

    def _lemma(self, term: str) -> tuple[str, str | None]:
        normalized = " ".join(str(term or "").strip().split())
        try:
            if self._nlp is None:
                from .linguistics import LinguisticAnalyzer

                self._nlp = LinguisticAnalyzer._pipeline()
            if self._nlp is None:
                return normalized.lower(), None
            doc = self._nlp(normalized)
            token = next((item for item in doc if not item.is_space), None)
            if token:
                lemma = token.lemma_ if token.lemma_ and token.lemma_ != "-PRON-" else token.text.lower()
                return lemma.lower(), token.pos_.lower() or None
        except (ImportError, OSError):
            pass
        return normalized.lower(), None

    @staticmethod
    def _safe_call(obj, name: str, default):
        value = getattr(obj, name, None)
        if value is None:
            return default
        try:
            return value() if callable(value) else value
        except Exception:
            return default

    def lookup(self, term: str, language: str = "en", pos_hint: str | None = None) -> ServiceResult:
        if language.lower() != "en":
            return ServiceResult("unavailable", provider=self.provider, provider_version=self.provider_version)
        lemma, detected_pos = self._lemma(term)
        pos = (pos_hint or detected_pos or "").lower()
        key = f"{DICTIONARY_RESPONSE_VERSION}|{language}|{lemma}|{pos}|{self.provider_version}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            import wn
        except ImportError:
            return self.cache.put(key, ServiceResult(
                "unavailable", {"lemma": lemma, "reason": "optional_dependency_unavailable"},
                self.provider, self.provider_version,
            ))
        # ``wn`` keeps a process-wide SQLite connection pool. Highlight
        # requests run in FastAPI worker threads, while warmup and tests may
        # subsequently query from another thread. Configure the connection
        # before its first use so the local, read-only lexicon can be reused
        # safely instead of failing with sqlite3.ProgrammingError.
        wn.config.allow_multithreading = True
        bundled_wn = Path(getattr(sys, "_MEIPASS", "")) / "wn_data"
        if getattr(sys, "frozen", False) and (bundled_wn / "wn.db").is_file():
            wn.config.data_directory = bundled_wn
        pos_map = {"noun": "n", "propn": "n", "verb": "v", "adj": "a", "adjective": "a", "adv": "r", "adverb": "r"}
        kwargs = {"pos": pos_map[pos]} if pos in pos_map else {}
        try:
            synsets = list(wn.synsets(lemma, lang="en", **kwargs))
        except Exception as exc:
            return self.cache.put(key, ServiceResult(
                "unavailable", {"lemma": lemma, "reason": f"wordnet_dataset_unavailable:{type(exc).__name__}"},
                self.provider, self.provider_version,
            ))
        # Contextual POS is ranking guidance, not a hard dictionary gate. EPUB
        # fragments can mis-tag ordinary words, so retry without the filter
        # before reporting that a common English entry does not exist.
        if not synsets and kwargs:
            try:
                synsets = list(wn.synsets(lemma, lang="en"))
            except Exception:
                synsets = []
        if not synsets:
            try:
                from wn.morphy import morphy
                forms = morphy(lemma, kwargs.get("pos"))
                candidates = sorted(
                    {candidate for values in forms.values() for candidate in values if candidate != lemma},
                    key=lambda candidate: (len(candidate), candidate),
                )
                for candidate in candidates:
                    candidate_synsets = list(wn.synsets(candidate, lang="en", **kwargs))
                    if candidate_synsets:
                        lemma, synsets = candidate, candidate_synsets
                        break
            except Exception:
                pass
        senses = []
        for synset in synsets[:20]:
            words = self._safe_call(synset, "words", []) or []
            synonyms = sorted({str(self._safe_call(word, "lemma", "") or word).replace("_", " ") for word in words})
            examples = list(self._safe_call(synset, "examples", []) or [])
            hypernyms = self._safe_call(synset, "hypernyms", []) or []
            hyponyms = self._safe_call(synset, "hyponyms", []) or []
            antonyms = set()
            for word in words:
                for antonym in self._safe_call(word, "antonyms", []) or []:
                    antonyms.add(str(self._safe_call(antonym, "lemma", "") or antonym).replace("_", " "))
            senses.append({
                "synset_id": str(getattr(synset, "id", "")),
                "pos": str(self._safe_call(synset, "pos", "")),
                "definition": str(self._safe_call(synset, "definition", "")),
                "examples": examples,
                "synonyms": [item for item in synonyms if item],
                "antonyms": sorted(item for item in antonyms if item),
                "semantic_parents": [str(getattr(item, "id", item)) for item in hypernyms],
                "semantic_children": [str(getattr(item, "id", item)) for item in hyponyms],
            })
        result = ServiceResult(
            "ok" if senses else "not_found",
            {"term": term, "lemma": lemma, "part_of_speech": pos or None, "senses": senses, "etymology": {"status": "unavailable"}},
            self.provider, self.provider_version,
        )
        return self.cache.put(key, result)


_ARPABET_IPA = {
    "AA":"ɑ", "AE":"æ", "AH":"ʌ", "AO":"ɔ", "AW":"aʊ", "AY":"aɪ", "B":"b", "CH":"tʃ", "D":"d",
    "DH":"ð", "EH":"ɛ", "ER":"ɝ", "EY":"eɪ", "F":"f", "G":"ɡ", "HH":"h", "IH":"ɪ", "IY":"i",
    "JH":"dʒ", "K":"k", "L":"l", "M":"m", "N":"n", "NG":"ŋ", "OW":"oʊ", "OY":"ɔɪ", "P":"p",
    "R":"r", "S":"s", "SH":"ʃ", "T":"t", "TH":"θ", "UH":"ʊ", "UW":"u", "V":"v", "W":"w",
    "Y":"j", "Z":"z", "ZH":"ʒ"
}


class OfflinePronunciationProvider:
    provider = "offline_pronunciation"
    provider_version = "pronunciation_v1"

    def __init__(self, corpus_root: str = "", index_path: str = "", cache_size: int = DICTIONARY_CACHE_SIZE):
        self.root = Path(corpus_root).resolve() if corpus_root else None
        self.index_path = Path(index_path).resolve() if index_path else None
        self.cache = LRUCache[ServiceResult](cache_size)
        self._records: dict[str, list[dict]] | None = None
        self._audio: dict[str, Path] = {}

    def _load(self):
        if self._records is not None:
            return
        self._records = {}
        if not self.root or not self.index_path or not self.index_path.is_file():
            return
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("records", [])
        for record in records:
            key = f"{record.get('language', 'en').lower()}|{str(record.get('term', '')).lower()}"
            copied = dict(record)
            audio_path = copied.get("audio_path")
            if audio_path:
                path = (self.root / audio_path).resolve()
                if self.root in path.parents and path.is_file():
                    audio_id = hashlib.sha256(f"{key}|{copied.get('variant', '')}|{audio_path}".encode()).hexdigest()[:32]
                    copied["audio_id"] = audio_id
                    self._audio[audio_id] = path
            self._records.setdefault(key, []).append(copied)

    def audio_path(self, audio_id: str) -> Path | None:
        self._load()
        path = self._audio.get(str(audio_id))
        if not path or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            return None
        return path

    @staticmethod
    def _cmu(term: str) -> list[dict]:
        try:
            import cmudict
            pronunciations = cmudict.dict().get(term.lower(), [])
        except ImportError:
            return []
        results = []
        for index, phones in enumerate(pronunciations[:5]):
            ipa_parts, human = [], []
            for phone in phones:
                stress = phone[-1] if phone[-1:].isdigit() else ""
                base = re.sub(r"\d", "", phone)
                symbol = _ARPABET_IPA.get(base, base.lower())
                if stress == "1":
                    symbol = "ˈ" + symbol
                elif stress == "2":
                    symbol = "ˌ" + symbol
                ipa_parts.append(symbol)
                human.append(base.upper() if stress == "1" else base.lower())
            results.append({"variant": str(index + 1), "ipa": "/" + "".join(ipa_parts) + "/", "human_phonetic": "-".join(human), "audio": {"status": "unavailable"}})
        return results

    def lookup(self, term: str, language: str = "en") -> ServiceResult:
        key = f"{language.lower()}|{term.lower().strip()}"
        cached = self.cache.get(key)
        if cached:
            return cached
        self._load()
        variants = []
        for record in (self._records or {}).get(key, []):
            variants.append({
                "variant": record.get("variant", "default"), "ipa": record.get("ipa"),
                "human_phonetic": record.get("human_phonetic"), "speaker": record.get("speaker"),
                "license": record.get("license"),
                "audio": {"status": "recorded", "audio_id": record["audio_id"]} if record.get("audio_id") else {"status": "unavailable"},
            })
        if not variants and language.lower() == "en":
            variants = self._cmu(term)
        result = ServiceResult("ok" if variants else "unavailable", {"term": term, "variants": variants}, self.provider, self.provider_version)
        return self.cache.put(key, result)
