import sqlite3
import os
import re
import json
import hashlib
import unicodedata
import uuid
from contextlib import contextmanager
from collections import OrderedDict
from config import (
    ACTIVE_ENTITY_LIMIT,
    ALIAS_ACCEPTED_CONFIDENCE,
    ALIAS_ACCEPTED_SUPPORT,
    ALIAS_BASE_CONFIDENCE,
    ALIAS_EXPIRED_CONFIDENCE,
    ALIAS_REVIEW_CONFIDENCE,
    ALIAS_SUPPORT_CONFIDENCE_BOOST,
    CONFIDENCE_DECAY_AFTER_CHAPTERS,
    CONFIDENCE_DECAY_FACTOR,
    ENTITY_BASE_CONFIDENCE,
    ENTITY_REVIEW_CONFIDENCE,
    ENTITY_SUPPORT_CONFIDENCE_BOOST,
    ENTITY_TYPE_CHANGE_CONFIDENCE,
    ENTITY_TYPE_CHANGE_SUPPORT,
    EVENT_CONTEXT_LIMIT,
    BOOKBUDDY_VERSION,
    CACHE_VERSION,
    GEMINI_MODEL_NAME,
    GRAPH_SCHEMA_VERSION,
    IMAGE_EVIDENCE_SCHEMA_VERSION,
    INHERITED_GRAPH_CONFIDENCE,
    LIFE_STATUS_DECAY_AFTER_CHAPTERS,
    LIFE_STATUS_DECAY_FACTOR,
    LOCAL_GRAPH_CONFIDENCE,
    MEMORY_CARD_LIMIT,
    MEMORY_CARD_RELATIONSHIP_LIMIT,
    MEMORY_CARD_RECENT_EVENT_LIMIT,
    NORMALIZATION_VERSION,
    PROMPT_VERSION,
    REPLAY_VERSION,
    RELATIONSHIP_BASE_CONFIDENCE,
    RELATIONSHIP_CONTRADICTION_DELTA,
    REGEX_CACHE_SIZE,
    SEARCH_TERMS_LONG_TEXT_TERM_LIMIT,
    SEARCH_TERMS_LONG_TEXT_TOKEN_LIMIT,
    SNAPSHOT_CONTRACT_VERSION,
    RESOLVER_VERSIONS,
)

SEARCH_TERM_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "he", "her", "him", "his", "i", "in", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "she", "that", "the", "their", "them", "they",
    "this", "to", "was", "we", "with", "you", "your",
}

TITLE_PREFIXES = {
    "baron", "captain", "chief", "commander", "count", "countess", "doctor",
    "dr", "duke", "duchess", "emperor", "empress", "governor", "king",
    "lady", "lord", "magistrate", "major", "minister", "miss", "mr", "mrs",
    "ms", "officer", "president", "prince", "princess", "professor", "queen",
    "senator", "sir", "warden",
}

TITLE_PREFIX_CLASSES = {
    "mr": "masculine",
    "sir": "masculine",
    "mrs": "feminine",
    "ms": "feminine",
    "miss": "feminine",
    "lady": "feminine",
}

LOW_INFORMATION_SUFFIXES = {
    "boy", "brother", "child", "daughter", "father", "friend", "girl",
    "guard", "husband", "man", "mother", "servant", "sister", "son",
    "uncle", "wife", "woman",
}

KINSHIP_TERMS = {
    "aunt", "brother", "child", "daughter", "father", "husband", "mother",
    "sister", "son", "uncle", "wife",
}

GROUP_COLLECTIVE_TERMS = {
    "army", "brothers", "clan", "crew", "family", "faction", "folk",
    "gang", "guards", "house", "nobles", "order", "people", "school",
    "sisters", "team", "tribe",
}

REFERENCE_ENTITY_TYPES = {"CONCEPT_OR_LORE", "REFERENCE", "WORK_OF_ART"}
ACTIVE_NARRATIVE_ENTITY_TYPES = {"INDIVIDUAL", "GROUP", "LOCATION"}

PARTICIPATION_PROMOTION_THRESHOLD = 3.0

DEFAULT_ENTITY_ONTOLOGY = {
    "entity_category": "UNKNOWN",
    "species_or_kind": "unknown",
    "sentience": "unknown",
    "narrative_role": "unknown",
    "story_role": "unknown",
    "functional_role": "",
    "active_status": "uncertain",
    "identity_status": "unknown",
    "entity_persistence": "persistent",
    "canonical_identity": "",
    "body_form": "",
    "embodiment": "unknown",
    "agency_score": 0.0,
    "can_speak": "unknown",
    "can_move": "unknown",
    "can_think": "unknown",
    "can_remember": "unknown",
    "can_make_decisions": "unknown",
    "can_form_relationships": "unknown",
    "ontology_confidence": 0.5,
    "ontology_evidence": "",
    "literal_status": "literal",
    "interpretation_status": "actual",
    "language_status": "natural_language",
    "translation_status": "not_applicable",
    "raw_surface_form": "",
    "social_status": "",
}

UNKNOWN_ONTOLOGY_VALUES = {"", "unknown", "uncertain", None}
ENTITY_CATEGORY_VALUES = {"CHARACTER", "GROUP", "LOCATION", "OBJECT", "CONCEPT", "REFERENCE", "UNKNOWN"}
ACTIVE_STATUS_VALUES = {
    "active_participant",
    "referenced_only",
    "historical_only",
    "symbolic_only",
    "uncertain",
}
SENTIENCE_VALUES = {"true", "false", "unknown", "sentient", "non_sentient"}
IDENTITY_STATUS_VALUES = {"confirmed", "probable", "possible", "conflicted", "unknown"}
ENTITY_PERSISTENCE_VALUES = {
    "persistent",
    "temporary",
    "scene_only",
    "flashback_only",
    "dream_only",
    "hallucination_only",
}
INTERPRETATION_STATUS_VALUES = {
    "literal",
    "symbolic",
    "imagined",
    "metaphorical",
    "historical_reference",
    "uncertain",
    "actual",
    "dream",
    "hallucination",
    "reported",
    "recalled",
}
ONTOLOGY_SOURCE_VALUES = {
    "explicit_text",
    "dialogue",
    "speech",
    "event",
    "relationship",
    "resolver",
    "parser_rule",
    "LLM",
    "manual",
    "graph_inference",
    "ingest",
}
CAPABILITY_FIELDS = (
    "can_speak",
    "can_move",
    "can_think",
    "can_remember",
    "can_make_decisions",
    "can_form_relationships",
)
ONTOLOGY_FIELDS = (
    "entity_category",
    "species_or_kind",
    "sentience",
    "narrative_role",
    "story_role",
    "functional_role",
    "active_status",
    "identity_status",
    "entity_persistence",
    "canonical_identity",
    "body_form",
    "embodiment",
    "agency_score",
    *CAPABILITY_FIELDS,
    "ontology_confidence",
    "ontology_evidence",
    "literal_status",
    "interpretation_status",
    "language_status",
    "translation_status",
    "raw_surface_form",
    "social_status",
)
AGENCY_SURFACE_CLASSES = {"proper_name", "compound_name", "place_name"}
ACTIVE_GRAPH_STATUSES = {"active_participant", "uncertain"}

LIFE_ACTUAL_STATUS_VALUES = {"alive", "dead", "missing", "unknown"}
LIFE_BELIEF_STATUS_VALUES = {"alive", "dead", "missing", "unknown"}
LIFE_APPEARANCE_STATUS_VALUES = {
    "possible_alive",
    "observed_alive",
    "confirmed_alive",
    "appears_dead",
    "unknown",
}
LIFE_BELIEF_OWNER_TYPES = {"reader", "narrator", "character", "group", "unknown"}
LIFE_PARTICIPATION_TYPES = {
    "active_scene",
    "flashback",
    "memory",
    "vision",
    "letter",
    "recording",
    "historical_reference",
    "dream",
    "hallucination",
}
LIFE_OBSERVATION_TYPES = {
    "direct",
    "reported",
    "assumed",
    "rumor",
    "historical",
    "vision",
    "dream",
    "flashback",
}
LIFE_STATUS_REASONS = {
    "battle",
    "execution",
    "disease",
    "accident",
    "suicide",
    "reported",
    "rumor",
    "fake",
    "supernatural",
    "unknown",
}
LIFE_MISSING_SUBTYPES = {"lost", "captured", "escaped", "disappeared", "unknown_location", "missing"}
LIFE_IDENTITY_CONTINUITY_MODES = {
    "same_identity",
    "copy",
    "reconstructed",
    "revived",
    "reincarnated",
    "alternate_self",
    "unknown",
}
LEGACY_SIGNAL_TYPES = {
    "grief",
    "memorial",
    "revenge",
    "lineage",
    "inheritance",
    "political_claim",
    "memory",
    "honor",
    "hatred",
    "historical_reference",
    "familial",
    "legacy",
}

REFERENCE_OBJECT_TERMS = (
    "law", "laws", "theorem", "theory", "equation", "formula", "symphony",
    "sonata", "song", "poem", "play", "novel", "book", "painting",
    "portrait", "statue", "memorial", "academy", "institute", "school",
    "house", "order", "prize", "award", "ship", "ships", "vessel",
    "vessels", "frigate", "cruiser", "fleet", "law", "laws", "code",
    "codes", "treaty", "treaties", "pact", "charter", "doctrine",
    "doctrines", "principle", "principles", "planet", "moon", "station",
    "city", "town", "settlement", "colony", "province", "kingdom",
    "empire", "artifact", "artefact", "relic", "weapon", "sword",
    "title", "epithet", "rank", "office", "medal", "foundation",
    "hospital", "library", "hall", "tower", "gate", "bridge",
)

REFERENCE_SUBTYPE_KEYWORDS = {
    "scientific_reference": {"law", "laws", "theorem", "theory", "equation", "formula", "principle", "principles"},
    "legal_reference": {"law", "laws", "code", "codes", "treaty", "treaties", "pact", "charter"},
    "doctrinal_reference": {"doctrine", "doctrines", "creed", "creeds"},
    "artwork_reference": {"symphony", "sonata", "song", "poem", "play", "novel", "book", "painting", "portrait"},
    "commemorative_reference": {"memorial", "statue", "monument", "prize", "award", "medal"},
    "institution_reference": {"academy", "institute", "school", "house", "order", "foundation", "hospital", "library"},
    "vehicle_reference": {"ship", "ships", "vessel", "vessels", "frigate", "cruiser", "fleet"},
    "place_reference": {"planet", "moon", "station", "city", "town", "settlement", "colony", "province", "kingdom", "empire"},
    "artifact_reference": {"artifact", "artefact", "relic", "weapon", "sword"},
    "title_reference": {"title", "epithet", "rank", "office"},
}

NAME_SEMANTIC_RELATION_TYPES = {
    "namesake",
    "eponym_attribution",
    "homonym_collision",
    "rename",
    "possessive_reference",
    "same_surface_distinct_referent",
}

POSSESSIVE_SUFFIX_PATTERN = r"(?:'s|\u2019s)"

PARTICIPATION_ACTION_PATTERNS = (
    r"\b{name}\b\s+(?:said|asked|replied|whispered|shouted|entered|left|walked|looked|stood|sat|opened|closed|took|gave|struck|killed|helped|watched|turned|smiled|laughed|cried|nodded)",
    r"(?:said|asked|replied|whispered|shouted)\s+\b{name}\b",
)

RELATIONSHIP_PARTICIPATION_PATTERN = r"\b{name}\b\s+(?:trusted|hated|loved|feared|betrayed|helped|admired|followed|opposed)\b"

RELIGIOUS_TITLE_TERMS = {
    "abbot", "abbess", "archbishop", "bishop", "brother", "cardinal",
    "father", "mother", "pope", "priest", "rabbi", "sister",
}

OCCUPATIONAL_TITLE_TERMS = {
    "captain", "doctor", "dr", "guard", "lieutenant", "nurse", "officer",
    "professor", "teacher",
}

ROLE_OR_TITLE_TERMS = TITLE_PREFIXES | KINSHIP_TERMS | RELIGIOUS_TITLE_TERMS | OCCUPATIONAL_TITLE_TERMS

def _is_title_prefix(token: str) -> bool:
    token = str(token or "").lower()
    if token in TITLE_PREFIXES:
        return True
    return token.startswith("arch") and token[4:] in TITLE_PREFIXES

def _name_tokens(value: str) -> list[str]:
    return [token for token in str(value or "").lower().split() if token]

def _strip_title_tokens(tokens: list[str]) -> list[str]:
    stripped = list(tokens)
    while len(stripped) > 1 and _is_title_prefix(stripped[0]):
        stripped.pop(0)
    return stripped

def _title_prefix_class(value: str) -> str:
    tokens = _name_tokens(value)
    if not tokens:
        return ""
    token = tokens[0]
    return TITLE_PREFIX_CLASSES.get(token, "")

def _title_category(value: str) -> str:
    tokens = _name_tokens(value)
    token_set = set(tokens)
    if token_set & RELIGIOUS_TITLE_TERMS:
        return "religious_title"
    if token_set & KINSHIP_TERMS:
        return "kinship"
    if token_set & OCCUPATIONAL_TITLE_TERMS:
        return "occupational_title"
    if tokens and _is_title_prefix(tokens[0]):
        return "noble_or_formal_title"
    if tokens:
        return "descriptor"
    return "unknown"

def _regex_name(value: str) -> str:
    return re.escape(" ".join(str(value or "").split()))

def _window_around(text: str, surface: str, radius: int = 180) -> str:
    if not text or not surface:
        return ""
    match = re.search(rf"\b{_regex_name(surface)}\b", text, flags=re.IGNORECASE)
    if not match:
        return " ".join(str(text or "")[: radius * 2].split())
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return " ".join(text[start:end].split())

def _infer_reference_subtype(context: str) -> str:
    tokens = set(re.findall(r"\b[\w']+\b", str(context or "").lower()))
    for subtype, keywords in REFERENCE_SUBTYPE_KEYWORDS.items():
        if tokens & keywords:
            return subtype
    if re.search(r"\b(?:named|renamed|called)\s+(?:after|for)\s+[A-Z][\w.'-]{2,}", str(context or ""), flags=re.IGNORECASE):
        return "namesake_reference"
    return "reference"

def _infer_name_semantic_relations_legacy(surface: str, context: str, reference_subtype: str = "reference") -> list[dict]:
    surface = " ".join(str(surface or "").split())
    if not surface:
        return []
    text = " ".join(str(context or "").split())
    if not text:
        return []

    surface_pattern = _regex_name(surface)
    reference_object_terms = "|".join(re.escape(term) for term in REFERENCE_OBJECT_TERMS)
    relations: list[dict] = []

    def _append(relation_type: str, target_surface: str = "", source_surface: str = "", reason: str = ""):
        if relation_type not in NAME_SEMANTIC_RELATION_TYPES:
            return
        relations.append({
            "relation_type": relation_type,
            "source_surface": source_surface or surface,
            "target_surface": target_surface or "",
            "reason": reason or relation_type,
            "reference_subtype": reference_subtype,
            "evidence": text[:500],
        })

    if re.search(rf"\b(?:named|called)\s+(?:after|for)\s+{surface_pattern}\b", text, flags=re.IGNORECASE):
        _append("namesake", target_surface=surface, reason="named_after_phrase")

    if re.search(rf"\b{surface_pattern}\s*(?:'s|â€™s)\s+(?:{reference_object_terms})\b", text, flags=re.IGNORECASE):
        relation_type = "eponym_attribution"
        if reference_subtype in {"legal_reference", "scientific_reference", "doctrinal_reference"}:
            relation_type = "eponym_attribution"
        elif reference_subtype in {"vehicle_reference", "place_reference", "artifact_reference", "institution_reference", "commemorative_reference"}:
            relation_type = "possessive_reference"
        _append(relation_type, target_surface=surface, reason="possessive_reference_object")

    if re.search(rf"\b(?:renamed|renames|rename|formerly|once called|previously called)\b", text, flags=re.IGNORECASE):
        _append("rename", reason="rename_language")

    if re.search(r"\b(?:homonym|homonyms)\b", text, flags=re.IGNORECASE):
        _append("homonym_collision", target_surface=surface, reason="homonym_language")

    if re.search(rf"\b(?:same name|same-named|namesake|not the same|different .*{surface_pattern}|another .*{surface_pattern})\b", text, flags=re.IGNORECASE):
        _append("same_surface_distinct_referent", target_surface=surface, reason="same_surface_language")

    return relations

def _infer_name_semantic_relations(surface: str, context: str, reference_subtype: str = "reference") -> list[dict]:
    surface = " ".join(str(surface or "").split())
    text = " ".join(str(context or "").split())
    if not surface or not text:
        return []

    surface_pattern = _regex_name(surface)
    reference_object_terms = "|".join(re.escape(term) for term in REFERENCE_OBJECT_TERMS)
    relations: list[dict] = []

    def _append(relation_type: str, target_surface: str = "", source_surface: str = "", reason: str = ""):
        if relation_type not in NAME_SEMANTIC_RELATION_TYPES:
            return
        relations.append({
            "relation_type": relation_type,
            "source_surface": source_surface or surface,
            "target_surface": target_surface or "",
            "reason": reason or relation_type,
            "reference_subtype": reference_subtype,
            "evidence": text[:500],
        })

    if re.search(rf"\b(?:named|called)\s+(?:after|for)\s+{surface_pattern}\b", text, flags=re.IGNORECASE):
        _append("namesake", target_surface=surface, reason="named_after_phrase")

    if re.search(rf"\b{surface_pattern}\s*{POSSESSIVE_SUFFIX_PATTERN}\s+(?:{reference_object_terms})\b", text, flags=re.IGNORECASE):
        relation_type = "eponym_attribution"
        if reference_subtype in {
            "vehicle_reference",
            "place_reference",
            "artifact_reference",
            "institution_reference",
            "commemorative_reference",
        }:
            relation_type = "possessive_reference"
        _append(relation_type, target_surface=surface, reason="possessive_reference_object")

    if re.search(r"\b(?:renamed|renames|rename|formerly|once called|previously called)\b", text, flags=re.IGNORECASE):
        _append("rename", reason="rename_language")

    if re.search(r"\b(?:homonym|homonyms)\b", text, flags=re.IGNORECASE):
        _append("homonym_collision", target_surface=surface, reason="homonym_language")

    if re.search(rf"\b(?:same name|same-named|namesake|not the same|different .*{surface_pattern}|another .*{surface_pattern})\b", text, flags=re.IGNORECASE):
        _append("same_surface_distinct_referent", target_surface=surface, reason="same_surface_language")

    return relations

CONFLICT_SEVERITY = {
    "identity_corruption": 1,
    "false_merge": 2,
    "merge_conflict": 2,
    "entity_type_collision": 3,
    "type_conflict": 3,
    "alias_collision": 4,
    "alias_ambiguity": 4,
    "relationship_contradiction": 5,
    "ambiguous_unresolved_mention": 6,
    "alias_rejected": 6,
    "alias_self": 6,
}

class BookDatabase:
    # Top-K Configurable limit to prevent LLM prompt token explosion
    ACTIVE_ENTITY_LIMIT = ACTIVE_ENTITY_LIMIT 

    def __init__(self, db_dir: str):
        self.db_path = os.path.join(db_dir, "graph.db")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._regex_cache = OrderedDict()
        self._search_terms_cache = OrderedDict()
        self._defer_search_sync_depth = 0
        self._dirty_entity_search_ids = set()
        self._initialize_schema()

    def _get_connection(self):
        return self._conn

    def close(self):
        self.flush_dirty_entity_search_terms()
        self._conn.close()

    def get_image_parse_cache(self, image_hash: str, parser_fingerprint: str) -> dict | None:
        """Read source-independent image parser output by exact content hash."""
        if not image_hash or not parser_fingerprint:
            return None
        cursor = self._get_connection().cursor()
        cursor.execute(
            """
            SELECT parse_output_json
            FROM image_parse_cache
            WHERE image_hash = ? AND parser_fingerprint = ?
            """,
            (image_hash, parser_fingerprint),
        )
        row = cursor.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("image_cache_deserialize_failed") from exc

    def put_image_parse_cache(self, image_hash: str, parser_fingerprint: str, parse_output: dict) -> None:
        """Persist a stable parse result or failure without occurrence metadata."""
        if not image_hash or not parser_fingerprint:
            return
        payload = json.dumps(parse_output or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO image_parse_cache (image_hash, parser_fingerprint, parse_output_json)
                VALUES (?, ?, ?)
                ON CONFLICT(image_hash, parser_fingerprint) DO UPDATE SET
                    parse_output_json = excluded.parse_output_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (image_hash, parser_fingerprint, payload),
            )

    def persist_image_evidence(
        self,
        chapter_evidence_revision_id: int,
        chapter: int,
        evidence: list[dict],
        *,
        conn=None,
    ) -> None:
        """Persist immutable image evidence and occurrence-specific provenance."""
        conn = conn or self._get_connection()
        normalized = [item for item in (evidence or []) if isinstance(item, dict)]
        incoming_hashes = [
            hashlib.sha256(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            for item in normalized
        ]
        active_rows = conn.execute(
            """
            SELECT chapter_evidence_revision_id, payload_hash
            FROM image_evidence_revisions
            WHERE chapter = ? AND is_active = 1
            ORDER BY occurrence_order
            """,
            (int(chapter),),
        ).fetchall()
        if (
            len(active_rows) == len(incoming_hashes)
            and all(int(row[0]) == int(chapter_evidence_revision_id) for row in active_rows)
            and [row[1] for row in active_rows] == incoming_hashes
        ):
            return
        conn.execute(
            "UPDATE image_evidence_revisions SET is_active = 0 WHERE chapter = ? AND is_active = 1",
            (int(chapter),),
        )
        for item in normalized:
            descriptor = item.get("descriptor") or {}
            occurrence_order = int(descriptor.get("occurrence_order", 0) or 0)
            payload_json = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            previous = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM image_evidence_revisions WHERE chapter = ? AND occurrence_order = ?",
                (int(chapter), occurrence_order),
            ).fetchone()[0]
            revision = int(previous or 0) + 1
            cursor = conn.execute(
                """
                INSERT INTO image_evidence_revisions (
                    chapter_evidence_revision_id, chapter, occurrence_order,
                    revision,
                    image_hash, parser_fingerprint, schema_version,
                    payload_json, payload_hash, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    int(chapter_evidence_revision_id), int(chapter), occurrence_order, revision,
                    str(descriptor.get("image_hash", "")),
                    str(item.get("parser_fingerprint", "")),
                    str(item.get("image_evidence_schema_version", IMAGE_EVIDENCE_SCHEMA_VERSION)),
                    payload_json, payload_hash,
                ),
            )
            conn.execute(
                """
                INSERT INTO image_occurrence_provenance (
                    image_evidence_revision_id, chapter, occurrence_order,
                    source_locator, document_item_id, member_path, caption_text,
                    alt_text, perceptual_hash, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(cursor.lastrowid), int(chapter), occurrence_order,
                    str(descriptor.get("source_locator", "")),
                    str(descriptor.get("document_item_id", "")),
                    str(descriptor.get("member_path", "")),
                    str(descriptor.get("caption_text", "")),
                    str(descriptor.get("alt_text", "")),
                    str(descriptor.get("perceptual_hash", "")),
                    json.dumps(descriptor.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
                ),
            )

    def _backfill_image_evidence_v2(self, conn) -> None:
        """Idempotently normalize active authoritative v2 chapter payloads."""
        rows = conn.execute(
            """
            SELECT id, chapter, payload_json
            FROM chapter_evidence_revisions
            WHERE is_active = 1
            ORDER BY chapter
            """
        ).fetchall()
        for evidence_id, chapter, payload_json in rows:
            try:
                payload = json.loads(payload_json)
            except (TypeError, json.JSONDecodeError):
                continue
            if (
                payload.get("image_evidence_schema_version") != IMAGE_EVIDENCE_SCHEMA_VERSION
                or not isinstance(payload.get("image_evidence"), list)
            ):
                continue
            self.persist_image_evidence(
                int(evidence_id),
                int(chapter),
                payload["image_evidence"],
                conn=conn,
            )

    def active_image_evidence(self, chapter: int | None = None) -> list[dict]:
        """Return active image evidence rows for diagnostics and replay verification."""
        conn = self._get_connection()
        query = """
            SELECT r.id, r.chapter, r.occurrence_order, r.revision,
                   r.image_hash, r.parser_fingerprint, r.schema_version,
                   r.payload_json, p.source_locator, p.document_item_id,
                   p.member_path, p.caption_text, p.alt_text,
                   p.perceptual_hash, p.metadata_json
            FROM image_evidence_revisions r
            JOIN image_occurrence_provenance p ON p.image_evidence_revision_id = r.id
            WHERE r.is_active = 1
        """
        parameters: tuple = ()
        if chapter is not None:
            query += " AND r.chapter = ?"
            parameters = (int(chapter),)
        query += " ORDER BY r.chapter, r.occurrence_order"
        rows = conn.execute(query, parameters).fetchall()
        result = []
        for row in rows:
            try:
                payload = json.loads(row[7])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            result.append({"id": int(row[0]), "chapter": int(row[1]), "occurrence_order": int(row[2]), "revision": int(row[3]), "payload": payload})
        return result

    @staticmethod
    def normalize_alias_key(value: str) -> str:
        value = unicodedata.normalize("NFKC", str(value or ""))
        value = " ".join(str(value or "").lower().strip().split())
        value = re.sub(r"[^\w\s]", "", value)
        return " ".join(value.split())

    def default_entity_ontology(self, entity_type: str | None, name: str = "") -> dict:
        ontology = dict(DEFAULT_ENTITY_ONTOLOGY)
        entity_type = str(entity_type or "").upper()
        if entity_type == "INDIVIDUAL":
            ontology.update({
                "entity_category": "CHARACTER",
                "active_status": "active_participant",
                "can_form_relationships": "unknown",
            })
        elif entity_type == "GROUP":
            ontology.update({
                "entity_category": "GROUP",
                "active_status": "active_participant",
                "sentience": "false",
                "can_form_relationships": "true",
            })
        elif entity_type == "LOCATION":
            ontology.update({
                "entity_category": "LOCATION",
                "active_status": "active_participant",
                "sentience": "false",
            })
        elif entity_type in REFERENCE_ENTITY_TYPES:
            ontology.update({
                "entity_category": "REFERENCE",
                "active_status": "referenced_only",
                "sentience": "unknown",
            })
        if name:
            ontology["raw_surface_form"] = name
        return ontology

    def normalize_entity_ontology(self, ontology: dict | None, entity_type: str | None = None, name: str = "") -> dict:
        normalized = self.default_entity_ontology(entity_type, name)
        if ontology:
            normalized.update({key: value for key, value in ontology.items() if key in ONTOLOGY_FIELDS and value is not None})

        category = str(normalized.get("entity_category") or "UNKNOWN").strip().upper()
        if category not in ENTITY_CATEGORY_VALUES:
            category = "UNKNOWN"
        normalized["entity_category"] = category

        sentience = str(normalized.get("sentience") or "unknown").strip().lower()
        if sentience == "sentient":
            sentience = "true"
        elif sentience == "non_sentient":
            sentience = "false"
        if sentience not in {"true", "false", "unknown"}:
            sentience = "unknown"
        normalized["sentience"] = sentience

        for field in CAPABILITY_FIELDS:
            value = str(normalized.get(field) or "unknown").strip().lower()
            if value in {"yes", "1", "true"}:
                value = "true"
            elif value in {"no", "0", "false"}:
                value = "false"
            elif value not in {"true", "false", "unknown"}:
                value = "unknown"
            normalized[field] = value

        active_status = str(normalized.get("active_status") or "uncertain").strip().lower()
        normalized["active_status"] = active_status if active_status in ACTIVE_STATUS_VALUES else "uncertain"

        identity_status = str(normalized.get("identity_status") or "unknown").strip().lower()
        normalized["identity_status"] = identity_status if identity_status in IDENTITY_STATUS_VALUES else "unknown"

        persistence = str(normalized.get("entity_persistence") or "persistent").strip().lower()
        normalized["entity_persistence"] = persistence if persistence in ENTITY_PERSISTENCE_VALUES else "persistent"

        interpretation = str(normalized.get("interpretation_status") or "actual").strip().lower()
        if "," in interpretation:
            values = [item.strip() for item in interpretation.split(",") if item.strip()]
            interpretation = "|".join(item for item in values if item in INTERPRETATION_STATUS_VALUES) or "uncertain"
        elif interpretation not in INTERPRETATION_STATUS_VALUES:
            interpretation = "uncertain"
        normalized["interpretation_status"] = interpretation

        literal_status = str(normalized.get("literal_status") or "literal").strip().lower()
        normalized["literal_status"] = literal_status or "literal"

        try:
            normalized["agency_score"] = float(normalized.get("agency_score") or 0.0)
        except (TypeError, ValueError):
            normalized["agency_score"] = 0.0
        try:
            normalized["ontology_confidence"] = max(0.0, min(1.0, float(normalized.get("ontology_confidence") or 0.5)))
        except (TypeError, ValueError):
            normalized["ontology_confidence"] = 0.5
        return normalized

    def get_entity_ontology(self, entity_id: int, cursor=None) -> dict | None:
        close_after = False
        if cursor is None:
            conn = self._get_connection()
            cursor = conn.cursor()
            close_after = False
        columns = ", ".join(ONTOLOGY_FIELDS)
        cursor.execute(f"SELECT {columns} FROM entities WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        if close_after:
            cursor.close()
        if not row:
            return None
        return dict(zip(ONTOLOGY_FIELDS, row))

    def record_entity_ontology_evidence(
        self,
        entity_id: int,
        ontology_field: str,
        old_value: str | None,
        new_value: str | None,
        chapter_idx: int | None = None,
        confidence: float = 0.5,
        source_text: str = "",
        ontology_source: str = "LLM",
        conn=None,
    ) -> int | None:
        if ontology_field not in ONTOLOGY_FIELDS or not entity_id:
            return None
        ontology_source = ontology_source if ontology_source in ONTOLOGY_SOURCE_VALUES else "LLM"
        conn = conn or self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO entity_ontology_evidence (
                entity_id, ontology_field, old_value, new_value,
                confidence, chapter, source_text, ontology_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_id,
            ontology_field,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
            max(0.0, min(1.0, float(confidence or 0.0))),
            chapter_idx,
            source_text,
            ontology_source,
        ))
        evidence_id = cursor.lastrowid
        self.record_resolver_decision(
            "ontology",
            "entity",
            entity_id,
            chapter_idx,
            "field_updated",
            confidence=confidence,
            supporting_evidence=[{"table": "entity_ontology_evidence", "id": evidence_id}],
            metadata={"field": ontology_field, "old_value": old_value, "new_value": new_value},
            conn=conn,
        )
        return evidence_id

    def record_entity_state_transition(
        self,
        entity_id: int,
        state_field: str,
        old_state: str | None,
        new_state: str | None,
        chapter_idx: int | None = None,
        trigger_event: int | None = None,
        confidence: float = 0.5,
        reason: str = "",
        source: str = "LLM",
        conn=None,
    ) -> int | None:
        if not entity_id or not state_field:
            return None
        source = source if source in ONTOLOGY_SOURCE_VALUES else "LLM"
        conn = conn or self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO entity_state_history (
                entity_id, state_field, old_state, new_state, chapter,
                trigger_event, confidence, reason, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_id,
            state_field,
            None if old_state is None else str(old_state),
            None if new_state is None else str(new_state),
            chapter_idx,
            trigger_event,
            max(0.0, min(1.0, float(confidence or 0.0))),
            reason,
            source,
        ))
        return cursor.lastrowid

    def update_entity_ontology(
        self,
        entity_id: int,
        ontology_updates: dict | None,
        chapter_idx: int | None = None,
        confidence: float = 0.5,
        source_text: str = "",
        ontology_source: str = "LLM",
        trigger_event: int | None = None,
        reason: str = "",
    ) -> dict | None:
        if not entity_id or not ontology_updates:
            return None
        normalized = self.normalize_entity_ontology(ontology_updates)
        update_fields = [field for field in ONTOLOGY_FIELDS if field in ontology_updates]
        if not update_fields:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            current = self.get_entity_ontology(entity_id, cursor)
            if not current:
                return None
            changed = {}
            for field in update_fields:
                old_value = current.get(field)
                new_value = normalized.get(field)
                if new_value in UNKNOWN_ONTOLOGY_VALUES and old_value not in UNKNOWN_ONTOLOGY_VALUES:
                    continue
                if str(old_value or "") == str(new_value or ""):
                    continue
                changed[field] = new_value
                self.record_entity_ontology_evidence(
                    entity_id,
                    field,
                    old_value,
                    new_value,
                    chapter_idx=chapter_idx,
                    confidence=confidence,
                    source_text=source_text,
                    ontology_source=ontology_source,
                    conn=conn,
                )
                if field in {
                    "entity_category",
                    "species_or_kind",
                    "sentience",
                    "active_status",
                    "identity_status",
                    "entity_persistence",
                    "literal_status",
                    "interpretation_status",
                    *CAPABILITY_FIELDS,
                }:
                    self.record_entity_state_transition(
                        entity_id,
                        field,
                        old_value,
                        new_value,
                        chapter_idx=chapter_idx,
                        trigger_event=trigger_event,
                        confidence=confidence,
                        reason=reason or source_text,
                        source=ontology_source,
                        conn=conn,
                    )
            if changed:
                assignments = ", ".join(f"{field} = ?" for field in changed)
                cursor.execute(
                    f"UPDATE entities SET {assignments} WHERE id = ?",
                    (*[changed[field] for field in changed], entity_id),
                )
            return {**current, **changed}

    def record_entity_semantic_relation(
        self,
        source_entity_id: int | None,
        target_entity_id: int | None = None,
        relation_type: str = "",
        relation_category: str = "semantic",
        source_surface: str = "",
        target_surface: str = "",
        chapter_idx: int | None = None,
        confidence: float = 0.55,
        source_text: str = "",
        ontology_source: str = "LLM",
        status: str = "observed",
    ) -> int | None:
        relation_type = self.normalize_alias_key(relation_type)
        if not relation_type:
            return None
        ontology_source = ontology_source if ontology_source in ONTOLOGY_SOURCE_VALUES else "LLM"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entity_semantic_relations (
                    source_entity_id, target_entity_id, relation_type,
                    relation_category, source_surface, target_surface,
                    chapter, confidence, source_text, ontology_source, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_entity_id,
                target_entity_id,
                relation_type,
                relation_category or "semantic",
                source_surface,
                target_surface,
                chapter_idx,
                max(0.0, min(1.0, float(confidence or 0.0))),
                source_text,
                ontology_source,
                status or "observed",
            ))
            return cursor.lastrowid

    def record_language_observation(
        self,
        surface_text: str,
        chapter_idx: int | None = None,
        language: str = "unknown",
        writing_system: str = "unknown",
        translation_status: str = "unknown",
        decoder_source: str = "",
        resolved_chapter: int | None = None,
        confidence: float = 0.5,
        source_section_type: str = "CHAPTER",
        source_quote: str = "",
    ) -> int | None:
        surface_text = " ".join(str(surface_text or "").split())
        if not surface_text:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO language_observations (
                    surface_text, normalized_text, language, writing_system,
                    translation_status, decoder_source, first_seen,
                    resolved_chapter, confidence, source_section_type, source_quote
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                surface_text,
                self.normalize_alias_key(surface_text),
                language or "unknown",
                writing_system or "unknown",
                translation_status or "unknown",
                decoder_source,
                chapter_idx,
                resolved_chapter,
                max(0.0, min(1.0, float(confidence or 0.0))),
                source_section_type or "CHAPTER",
                source_quote,
            ))
            return cursor.lastrowid

    def _normalize_choice(self, value: str | None, allowed: set[str], default: str) -> str:
        normalized = self.normalize_alias_key(value).replace(" ", "_")
        return normalized if normalized in allowed else default

    def record_life_status_evidence(
        self,
        entity_id: int,
        subject_surface: str = "",
        chapter_idx: int | None = None,
        linked_event_id: int | None = None,
        supersedes_evidence_id: int | None = None,
        actual_status: str = "unknown",
        belief_status: str = "unknown",
        appearance_status: str = "unknown",
        belief_owner_type: str = "unknown",
        belief_owner_entity_id: int | None = None,
        reader_visible: bool = True,
        participation_type: str = "active_scene",
        observation_type: str = "direct",
        status_reason: str = "unknown",
        missing_subtype: str | None = None,
        identity_continuity_mode: str = "unknown",
        identity_evidence_id: int | None = None,
        concealment_alias_id: int | None = None,
        confidence: float = 0.5,
        last_observation_chapter: int | None = None,
        last_confirmation_chapter: int | None = None,
        story_time_text: str = "",
        story_time_confidence: float = 0.0,
        narrative_order: int | None = None,
        timeline_position: float | None = None,
        evidence_text: str = "",
        evidence_source_type: str = "observed_fact",
        actuality_status: str = "actual",
        source_pov_id: int | None = None,
        source_speaker_id: int | None = None,
        narrator_entity_id: int | None = None,
        scene_scope: str | None = None,
        source_section_type: str = "CHAPTER",
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
    ) -> int | None:
        if not entity_id:
            return None
        actual_status = self._normalize_choice(actual_status, LIFE_ACTUAL_STATUS_VALUES, "unknown")
        belief_status = self._normalize_choice(belief_status, LIFE_BELIEF_STATUS_VALUES, "unknown")
        appearance_status = self._normalize_choice(appearance_status, LIFE_APPEARANCE_STATUS_VALUES, "unknown")
        belief_owner_type = self._normalize_choice(belief_owner_type, LIFE_BELIEF_OWNER_TYPES, "unknown")
        participation_type = self._normalize_choice(participation_type, LIFE_PARTICIPATION_TYPES, "active_scene")
        observation_type = self._normalize_choice(observation_type, LIFE_OBSERVATION_TYPES, "direct")
        status_reason = self._normalize_choice(status_reason, LIFE_STATUS_REASONS, "unknown")
        missing_subtype = self._normalize_choice(missing_subtype, LIFE_MISSING_SUBTYPES, "missing") if missing_subtype else None
        identity_continuity_mode = self._normalize_choice(
            identity_continuity_mode,
            LIFE_IDENTITY_CONTINUITY_MODES,
            "unknown",
        )
        if participation_type in {
            "flashback", "memory", "vision", "letter", "recording",
            "historical_reference", "dream", "hallucination",
        }:
            actual_status = "unknown"
        if observation_type in {"reported", "assumed", "rumor", "vision", "dream", "flashback"}:
            actual_status = "unknown"
        confidence = max(0.0, min(1.0, float(confidence if confidence is not None else 0.0)))
        inherited_confidence = max(0.01, min(1.0, float(inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE)))
        last_observation_chapter = last_observation_chapter if last_observation_chapter is not None else chapter_idx
        if actual_status in {"alive", "dead"} and confidence >= 0.8:
            last_confirmation_chapter = last_confirmation_chapter if last_confirmation_chapter is not None else chapter_idx
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO life_status_evidence (
                    entity_id, subject_surface, linked_event_id, supersedes_evidence_id,
                    actual_status, belief_status, appearance_status,
                    belief_owner_type, belief_owner_entity_id, reader_visible,
                    participation_type, observation_type, status_reason, missing_subtype,
                    identity_continuity_mode, identity_evidence_id,
                    concealment_alias_id, confidence, chapter,
                    last_observation_chapter, last_confirmation_chapter,
                    story_time_text, story_time_confidence, narrative_order,
                    timeline_position, evidence_text, evidence_source_type,
                    actuality_status, source_pov_id, source_speaker_id,
                    narrator_entity_id, scene_scope, source_section_type,
                    boundary_title_id, boundary_book_id, boundary_volume_id,
                    session_id, source_session, inherited_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_id,
                subject_surface,
                linked_event_id,
                supersedes_evidence_id,
                actual_status,
                belief_status,
                appearance_status,
                belief_owner_type,
                belief_owner_entity_id,
                1 if reader_visible else 0,
                participation_type,
                observation_type,
                status_reason,
                missing_subtype,
                identity_continuity_mode,
                identity_evidence_id,
                concealment_alias_id,
                confidence,
                chapter_idx,
                last_observation_chapter,
                last_confirmation_chapter,
                story_time_text,
                max(0.0, min(1.0, float(story_time_confidence or 0.0))),
                narrative_order,
                timeline_position,
                evidence_text,
                evidence_source_type or "observed_fact",
                actuality_status or "actual",
                source_pov_id,
                source_speaker_id,
                narrator_entity_id,
                scene_scope,
                source_section_type or "CHAPTER",
                boundary_title_id,
                boundary_book_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence,
            ))
            evidence_id = cursor.lastrowid
            state_value = actual_status if actual_status != "unknown" else belief_status
            cursor.execute("""
                INSERT INTO entity_state_history (
                    entity_id, state_field, old_state, new_state, chapter,
                    trigger_event, confidence, reason, source, status_domain,
                    belief_scope, source_entity_id, speaker_entity_id,
                    narrator_entity_id, evidence_source_type, actuality_status,
                    transition_type, story_time_text, story_time_confidence,
                    scene_scope, boundary_title_id, boundary_book_id,
                    boundary_volume_id, session_id, source_session,
                    inherited_confidence
                )
                VALUES (?, 'life_status', NULL, ?, ?, ?, ?, ?, 'life_status_resolver',
                        'literal_life', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_id,
                state_value,
                chapter_idx,
                linked_event_id,
                confidence,
                evidence_text,
                belief_owner_type,
                belief_owner_entity_id,
                source_speaker_id,
                narrator_entity_id,
                evidence_source_type or "observed_fact",
                actuality_status or "actual",
                status_reason,
                story_time_text,
                max(0.0, min(1.0, float(story_time_confidence or 0.0))),
                scene_scope,
                boundary_title_id,
                boundary_book_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence,
            ))
        try:
            from life_status_resolver import LifeStatusResolver
            LifeStatusResolver(self).resolve_entity(entity_id)
        except Exception as exc:
            self.record_conflict(
                "life_status_resolver_error",
                chapter_idx or 0,
                {"entity_id": entity_id, "evidence_id": evidence_id, "error": str(exc)},
                entity_id,
                severity=4,
            )
        return evidence_id

    def record_legacy_signal(
        self,
        entity_id: int,
        subject_surface: str = "",
        signal_type: str = "legacy",
        chapter_idx: int | None = None,
        evidence_text: str = "",
        confidence: float = 0.5,
        historical_importance: float = 0.0,
        emotional_importance: float = 0.0,
        political_importance: float = 0.0,
        familial_importance: float = 0.0,
        memory_strength: float = 0.0,
        linked_event_id: int | None = None,
        source_pov_id: int | None = None,
        source_speaker_id: int | None = None,
        narrator_entity_id: int | None = None,
        scene_scope: str | None = None,
        source_section_type: str = "CHAPTER",
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
    ) -> int | None:
        if not entity_id:
            return None
        signal_type = self._normalize_choice(signal_type, LEGACY_SIGNAL_TYPES, "legacy")
        confidence = max(0.0, min(1.0, float(confidence if confidence is not None else 0.0)))
        inherited_confidence = max(0.01, min(1.0, float(inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE)))
        dimensions = {
            "historical_importance": max(0.0, min(1.0, float(historical_importance or 0.0))),
            "emotional_importance": max(0.0, min(1.0, float(emotional_importance or 0.0))),
            "political_importance": max(0.0, min(1.0, float(political_importance or 0.0))),
            "familial_importance": max(0.0, min(1.0, float(familial_importance or 0.0))),
            "memory_strength": max(0.0, min(1.0, float(memory_strength or 0.0))),
        }
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entity_legacy_signals (
                    entity_id, subject_surface, signal_type, chapter,
                    evidence_text, confidence, historical_importance,
                    emotional_importance, political_importance,
                    familial_importance, memory_strength, linked_event_id,
                    source_pov_id, source_speaker_id, narrator_entity_id,
                    scene_scope, source_section_type, boundary_title_id,
                    boundary_book_id, boundary_volume_id, session_id,
                    source_session, inherited_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_id,
                subject_surface,
                signal_type,
                chapter_idx,
                evidence_text,
                confidence,
                dimensions["historical_importance"],
                dimensions["emotional_importance"],
                dimensions["political_importance"],
                dimensions["familial_importance"],
                dimensions["memory_strength"],
                linked_event_id,
                source_pov_id,
                source_speaker_id,
                narrator_entity_id,
                scene_scope,
                source_section_type or "CHAPTER",
                boundary_title_id,
                boundary_book_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence,
            ))
            signal_id = cursor.lastrowid
            cursor.execute("""
                SELECT COALESCE(SUM(confidence), 0.0),
                       COALESCE(MAX(memory_strength), 0.0),
                       COALESCE(MAX(historical_importance), 0.0),
                       COALESCE(MAX(emotional_importance), 0.0),
                       COALESCE(MAX(political_importance), 0.0),
                       COALESCE(MAX(familial_importance), 0.0)
                FROM entity_legacy_signals
                WHERE entity_id = ?
            """, (entity_id,))
            legacy_total, memory_max, historical, emotional, political, familial = cursor.fetchone()
            cursor.execute("""
                UPDATE entities
                SET legacy_importance = ?,
                    memory_strength = ?,
                    historical_importance = ?,
                    emotional_importance = ?,
                    political_importance = ?,
                    familial_importance = ?
                WHERE id = ?
            """, (
                min(1.0, float(legacy_total or 0.0) / 4.0),
                memory_max or 0.0,
                historical or 0.0,
                emotional or 0.0,
                political or 0.0,
                familial or 0.0,
                entity_id,
            ))
            return signal_id

    def entity_can_participate_in_events(self, entity_id: int, cursor=None) -> bool:
        ontology = self.get_entity_ontology(entity_id, cursor)
        if not ontology:
            return False
        category = str(ontology.get("entity_category") or "UNKNOWN").upper()
        active_status = str(ontology.get("active_status") or "uncertain").lower()
        persistence = str(ontology.get("entity_persistence") or "persistent").lower()
        interpretation = str(ontology.get("interpretation_status") or "actual").lower()
        if active_status in {"referenced_only", "historical_only", "symbolic_only"}:
            return False
        if persistence in {"dream_only", "hallucination_only"} or any(
            marker in interpretation for marker in ("dream", "hallucination", "imagined", "metaphorical")
        ):
            return False
        return category in {"CHARACTER", "GROUP", "LOCATION", "OBJECT"}

    def entity_can_form_social_edges(self, entity_id: int, cursor=None) -> bool:
        ontology = self.get_entity_ontology(entity_id, cursor)
        if not ontology:
            return False
        category = str(ontology.get("entity_category") or "UNKNOWN").upper()
        if category in {"REFERENCE", "CONCEPT"}:
            return False
        if category == "GROUP":
            return True
        if str(ontology.get("can_form_relationships") or "unknown").lower() == "true":
            return True
        if str(ontology.get("sentience") or "unknown").lower() == "true":
            return True
        return False

    def ontology_compatibility_reason(self, left: dict, right: dict) -> str | None:
        left_category = str(left.get("entity_category") or "UNKNOWN").upper()
        right_category = str(right.get("entity_category") or "UNKNOWN").upper()
        left_species = str(left.get("species_or_kind") or "unknown").lower()
        right_species = str(right.get("species_or_kind") or "unknown").lower()
        left_active = str(left.get("active_status") or "uncertain").lower()
        right_active = str(right.get("active_status") or "uncertain").lower()

        certain_categories = {left_category, right_category} - {"UNKNOWN"}
        if len(certain_categories) > 1:
            compatible_pairs = {
                frozenset({"CHARACTER", "OBJECT"}),
                frozenset({"CHARACTER", "LOCATION"}),
            }
            pair = frozenset({left_category, right_category})
            if pair not in compatible_pairs:
                return f"incompatible ontology categories: {left_category} vs {right_category}"
            if pair == frozenset({"CHARACTER", "OBJECT"}) and "object" not in {left_species, right_species, "unknown"}:
                return f"incompatible character/object species evidence: {left_species} vs {right_species}"
            if pair == frozenset({"CHARACTER", "LOCATION"}) and "location" not in {left_species, right_species, "place", "unknown"}:
                return f"incompatible character/location ontology: {left_species} vs {right_species}"

        if "REFERENCE" in {left_category, right_category} and certain_categories - {"REFERENCE", "UNKNOWN"}:
            if left_active == "active_participant" or right_active == "active_participant":
                return "reference entity conflicts with active participant"
        if "LOCATION" in {left_category, right_category} and "animal" in {left_species, right_species}:
            return "location cannot merge with animal ontology"
        return None

    def classify_mention_surface(self, surface_form: str, entity_type: str | None = None) -> dict:
        mention_key = self.normalize_alias_key(surface_form)
        tokens = _name_tokens(mention_key)
        title_category = _title_category(mention_key)
        if not mention_key:
            mention_class = "empty"
        elif mention_key in KINSHIP_TERMS:
            mention_class = "kinship"
        elif title_category in {"religious_title", "occupational_title"} and all(token in ROLE_OR_TITLE_TERMS for token in tokens):
            mention_class = "title"
        elif entity_type == "LOCATION":
            mention_class = "location"
        elif mention_key in GROUP_COLLECTIVE_TERMS or entity_type == "GROUP":
            mention_class = "group"
        elif entity_type in REFERENCE_ENTITY_TYPES:
            mention_class = "reference"
        elif len(tokens) == 1 and tokens[0].endswith("s") and tokens[0] not in KINSHIP_TERMS:
            mention_class = "group"
        else:
            mention_class = "entity"
        return {
            "mention_key": mention_key,
            "mention_class": mention_class,
            "title_category": title_category,
        }

    def score_narrative_participation(
        self,
        surface_form: str,
        context_text: str = "",
        entity_type: str | None = None,
        evidence_roles: list[str] | None = None,
    ) -> dict:
        surface = " ".join(str(surface_form or "").split())
        context = _window_around(context_text, surface) if context_text else ""
        participation_score = 0.0
        reference_score = 0.0
        breakdown = []

        classification = self.classify_mention_surface(surface, entity_type)
        if entity_type in REFERENCE_ENTITY_TYPES or classification["mention_class"] == "reference":
            reference_score += 4.0
            breakdown.append({"kind": "reference_entity_type", "delta": -4.0})
        if classification["mention_class"] in {"kinship", "title"}:
            reference_score += 2.0
            breakdown.append({"kind": f"{classification['mention_class']}_surface", "delta": -2.0})

        for role in evidence_roles or []:
            if role == "pov":
                participation_score += 5.0
                breakdown.append({"kind": "pov", "delta": 5.0})
            elif role == "relationship":
                participation_score += 3.0
                breakdown.append({"kind": "relationship", "delta": 3.0})
            elif role == "event":
                participation_score += 3.0
                breakdown.append({"kind": "event", "delta": 3.0})
            elif role == "setting":
                participation_score += 3.0
                breakdown.append({"kind": "setting", "delta": 3.0})

        if context:
            name_pattern = _regex_name(surface)
            reference_object_terms = "|".join(re.escape(term) for term in REFERENCE_OBJECT_TERMS)
            for pattern in PARTICIPATION_ACTION_PATTERNS:
                if re.search(pattern.format(name=name_pattern), context, flags=re.IGNORECASE):
                    participation_score += 3.0
                    breakdown.append({"kind": "acts_or_speaks", "delta": 3.0})
                    break
            if re.search(RELATIONSHIP_PARTICIPATION_PATTERN.format(name=name_pattern), context, flags=re.IGNORECASE):
                participation_score += 3.0
                breakdown.append({"kind": "relationship_language", "delta": 3.0})
            if entity_type == "LOCATION" and re.search(
                rf"\b(?:in|at|to|from|inside|near|through|around)\s+(?:the\s+)?{name_pattern}\b",
                context,
                flags=re.IGNORECASE,
            ):
                participation_score += 3.0
                breakdown.append({"kind": "setting_language", "delta": 3.0})
            if re.search(rf"\b{name_pattern}\s*(?:'s|’s)\s+(?:{reference_object_terms})\b", context, flags=re.IGNORECASE):
                reference_score += 3.0
                breakdown.append({"kind": "attribution", "delta": -3.0})
            if re.search(rf"\b(?:named|renamed|called)\s+(?:after|for)\s+{name_pattern}\b", context, flags=re.IGNORECASE):
                reference_score += 3.0
                breakdown.append({"kind": "named_after", "delta": -3.0})
            if re.search(rf"\b{name_pattern}\s+(?:memorial|statue|monument|academy|institute|prize|award)\b", context, flags=re.IGNORECASE):
                reference_score += 3.0
                breakdown.append({"kind": "commemorative_or_institutional_name", "delta": -3.0})

        net_score = participation_score - reference_score
        reference_subtype = _infer_reference_subtype(context or surface)
        promotion_state = "active_candidate" if net_score >= PARTICIPATION_PROMOTION_THRESHOLD else "reference"
        return {
            "participation_score": round(participation_score, 4),
            "reference_score": round(reference_score, 4),
            "net_score": round(net_score, 4),
            "promotion_state": promotion_state,
            "reference_subtype": reference_subtype,
            "reference_context": context,
            "breakdown": breakdown,
        }

    def record_reference_mention(
        self,
        surface_form: str,
        chapter_idx: int,
        entity_type_guess: str | None = None,
        context_text: str = "",
        narrator_entity_id: int | None = None,
        scene_scope: str | None = None,
        source_section_type: str = "CHAPTER",
        source_quote: str = "",
        evidence_roles: list[str] | None = None,
        linked_entity_id: int | None = None,
    ) -> int | None:
        normalized = self.normalize_alias_key(surface_form)
        if not normalized:
            return None
        score = self.score_narrative_participation(surface_form, context_text, entity_type_guess, evidence_roles)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reference_mentions (
                    surface_form, normalized_form, chapter, entity_type_guess,
                    reference_subtype, reference_context, participation_score,
                    reference_score, score_breakdown, promotion_state,
                    linked_entity_id, narrator_entity_id, scene_scope,
                    source_section_type, source_quote
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                surface_form,
                normalized,
                chapter_idx,
                entity_type_guess,
                score["reference_subtype"],
                score["reference_context"],
                score["participation_score"],
                score["reference_score"],
                json.dumps(score["breakdown"], ensure_ascii=False, sort_keys=True),
                score["promotion_state"],
                linked_entity_id,
                narrator_entity_id,
                scene_scope,
                source_section_type,
                source_quote or score["reference_context"],
            ))
            reference_mention_id = cursor.lastrowid

        for relation in _infer_name_semantic_relations(surface_form, score["reference_context"], score["reference_subtype"]):
            self.record_name_semantic_relation(
                relation.get("relation_type", ""),
                chapter_idx=chapter_idx,
                source_surface=relation.get("source_surface") or surface_form,
                target_surface=relation.get("target_surface") or "",
                reference_mention_id=reference_mention_id,
                reference_subtype=relation.get("reference_subtype") or score["reference_subtype"],
                relation_context=score["reference_context"],
                source_section_type=source_section_type,
                source_quote=source_quote or relation.get("evidence") or score["reference_context"],
                reason=relation.get("reason", ""),
                confidence=0.7,
            )
        return reference_mention_id

    def record_name_semantic_relation(
        self,
        relation_type: str,
        chapter_idx: int | None = None,
        source_surface: str = "",
        target_surface: str = "",
        source_entity_id: int | None = None,
        target_entity_id: int | None = None,
        reference_mention_id: int | None = None,
        reference_subtype: str = "reference",
        relation_context: str = "",
        source_section_type: str = "CHAPTER",
        source_quote: str = "",
        confidence: float = 0.55,
        status: str = "observed",
        reason: str = "",
    ) -> int | None:
        relation_type = str(relation_type or "").strip()
        if relation_type not in NAME_SEMANTIC_RELATION_TYPES:
            return None
        source_normalized = self.normalize_alias_key(source_surface)
        target_normalized = self.normalize_alias_key(target_surface)
        if not source_normalized and not target_normalized and not (source_entity_id or target_entity_id):
            return None
        context_payload = relation_context or reason or source_quote
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO name_semantic_relations (
                    relation_type, source_surface, source_normalized,
                    target_surface, target_normalized, source_entity_id,
                    target_entity_id, reference_mention_id, chapter,
                    reference_subtype, relation_context, source_section_type,
                    source_quote, confidence, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                relation_type,
                source_surface,
                source_normalized,
                target_surface,
                target_normalized,
                source_entity_id,
                target_entity_id,
                reference_mention_id,
                chapter_idx,
                reference_subtype or "reference",
                context_payload,
                source_section_type or "CHAPTER",
                source_quote or context_payload,
                confidence,
                status or "observed",
            ))
            return cursor.lastrowid

    def _has_name_semantic_blocker(
        self,
        cursor,
        left_key: str,
        right_key: str = "",
        relation_types: set[str] | None = None,
    ) -> str | None:
        keys = [key for key in {left_key, right_key} if key]
        if not keys:
            return None
        relation_types = relation_types or NAME_SEMANTIC_RELATION_TYPES
        placeholders = ",".join("?" for _ in relation_types)
        key_placeholders = ",".join("?" for _ in keys)
        cursor.execute(f"""
            SELECT relation_type
            FROM name_semantic_relations
            WHERE relation_type IN ({placeholders})
              AND COALESCE(status, 'observed') NOT IN ('rejected', 'resolved_as_alias')
              AND (
                  source_normalized IN ({key_placeholders})
                  OR target_normalized IN ({key_placeholders})
              )
            LIMIT 1
        """, tuple(relation_types) + tuple(keys) + tuple(keys))
        row = cursor.fetchone()
        return row[0] if row else None

    def should_promote_mention_to_active_entity(
        self,
        surface_form: str,
        entity_type: str,
        chapter_idx: int,
        context_text: str = "",
        evidence_roles: list[str] | None = None,
        ontology: dict | None = None,
    ) -> tuple[bool, dict]:
        score = self.score_narrative_participation(surface_form, context_text, entity_type, evidence_roles)
        normalized_ontology = self.normalize_entity_ontology(ontology, entity_type, surface_form)
        category = normalized_ontology.get("entity_category", "UNKNOWN")
        active_status = normalized_ontology.get("active_status", "uncertain")
        interpretation = str(normalized_ontology.get("interpretation_status") or "uncertain").lower()
        persistence = str(normalized_ontology.get("entity_persistence") or "persistent").lower()
        if category in {"REFERENCE", "CONCEPT"} or active_status in {"referenced_only", "historical_only", "symbolic_only"}:
            return False, score
        if persistence in {"dream_only", "hallucination_only"} or any(
            marker in interpretation for marker in ("dream", "hallucination", "imagined", "metaphorical")
        ):
            return False, score
        if entity_type not in ACTIVE_NARRATIVE_ENTITY_TYPES and category not in {"OBJECT", "CHARACTER", "LOCATION", "GROUP"}:
            return False, score
        if category == "OBJECT" and score["participation_score"] >= PARTICIPATION_PROMOTION_THRESHOLD:
            return True, score
        if score["promotion_state"] == "active_candidate":
            return True, score
        return False, score

    def _infer_surface_form_class(self, name: str, entity_type: str) -> str:
        stripped = str(name or "").strip()
        lower = stripped.lower()
        if entity_type == "LOCATION":
            return "place_name" if any(ch.isupper() for ch in stripped) else "location_fragment"
        if self.normalize_alias_key(lower) in KINSHIP_TERMS:
            return "kinship"
        if lower.startswith("the "):
            return "title" if stripped[4:5].isupper() else "descriptor"
        if lower in {
            "butler", "nurse", "policeman", "doctor", "reporter", "conductor",
            "chambermaid", "lieutenant", "chauffeur", "guard", "servant",
        }:
            return "role"
        if stripped and not any(ch.isupper() for ch in stripped):
            return "descriptor"
        if len(stripped.split()) == 1:
            return "proper_name"
        return "compound_name"

    def _infer_location_subtype(self, name: str) -> str | None:
        lower = str(name or "").lower()
        if not lower:
            return None
        if any(word in lower for word in ("street", "road", "avenue", "lane", "drive")):
            return "road"
        if any(word in lower for word in ("house", "hotel", "club", "building", "room", "apartment")):
            return "building"
        if any(word in lower for word in ("sound", "bay", "river", "valley", "island", "coast")):
            return "region"
        if len(lower.split()) == 1 and lower in {"sound", "valley", "island", "bay", "river"}:
            return "fragment"
        return "place"

    def _initial_importance(self, name: str, entity_type: str) -> tuple[float, float, str, str | None]:
        surface_class = self._infer_surface_form_class(name, entity_type)
        location_subtype = self._infer_location_subtype(name) if entity_type == "LOCATION" else None
        importance = 0.45
        visibility = 0.45
        if surface_class in {"proper_name", "compound_name", "place_name"}:
            importance = 0.6
            visibility = 0.6
        if surface_class in {"role", "descriptor", "kinship", "location_fragment"} or location_subtype == "fragment":
            importance = 0.2
            visibility = 0.15
        if entity_type == "GROUP":
            importance = max(importance, 0.55)
            visibility = max(visibility, 0.5)
        return importance, visibility, surface_class, location_subtype

    def _initialize_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT,
                    display_name TEXT,
                    entity_type TEXT,
                    first_seen_chapter INTEGER,
                    last_verified_chapter INTEGER,
                    mention_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.55,
                    type_support_count INTEGER DEFAULT 1,
                    importance_score REAL DEFAULT 0.45,
                    visibility_score REAL DEFAULT 0.45,
                    surface_form_class TEXT DEFAULT 'proper_name',
                    location_subtype TEXT,
                    entity_category TEXT DEFAULT 'unknown',
                    species_or_kind TEXT DEFAULT 'unknown',
                    sentience TEXT DEFAULT 'unknown',
                    narrative_role TEXT DEFAULT 'unknown',
                    story_role TEXT DEFAULT 'unknown',
                    functional_role TEXT,
                    active_status TEXT DEFAULT 'uncertain',
                    identity_status TEXT DEFAULT 'unknown',
                    entity_persistence TEXT DEFAULT 'persistent',
                    canonical_identity TEXT,
                    body_form TEXT,
                    embodiment TEXT DEFAULT 'unknown',
                    agency_score REAL DEFAULT 0.0,
                    can_speak TEXT DEFAULT 'unknown',
                    can_move TEXT DEFAULT 'unknown',
                    can_think TEXT DEFAULT 'unknown',
                    can_remember TEXT DEFAULT 'unknown',
                    can_make_decisions TEXT DEFAULT 'unknown',
                    can_form_relationships TEXT DEFAULT 'unknown',
                    ontology_confidence REAL DEFAULT 0.5,
                    ontology_evidence TEXT,
                    literal_status TEXT DEFAULT 'literal',
                    interpretation_status TEXT DEFAULT 'actual',
                    language_status TEXT DEFAULT 'natural_language',
                    translation_status TEXT DEFAULT 'not_applicable',
                    raw_surface_form TEXT,
                    social_status TEXT,
                    current_life_status TEXT DEFAULT 'unknown',
                    life_confidence REAL DEFAULT 0.0,
                    life_status_chapter INTEGER,
                    life_status_source TEXT,
                    legacy_importance REAL DEFAULT 0.0,
                    memory_strength REAL DEFAULT 0.0,
                    historical_importance REAL DEFAULT 0.0,
                    emotional_importance REAL DEFAULT 0.0,
                    political_importance REAL DEFAULT 0.0,
                    familial_importance REAL DEFAULT 0.0,
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_ontology_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    ontology_field TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    confidence REAL DEFAULT 0.5,
                    chapter INTEGER,
                    source_text TEXT,
                    ontology_source TEXT DEFAULT 'LLM',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    state_field TEXT NOT NULL,
                    old_state TEXT,
                    new_state TEXT,
                    chapter INTEGER,
                    trigger_event INTEGER,
                    confidence REAL DEFAULT 0.5,
                    reason TEXT,
                    source TEXT DEFAULT 'LLM',
                    status_domain TEXT,
                    belief_scope TEXT,
                    source_entity_id INTEGER,
                    speaker_entity_id INTEGER,
                    narrator_entity_id INTEGER,
                    evidence_source_type TEXT,
                    actuality_status TEXT,
                    transition_type TEXT,
                    story_time_text TEXT,
                    story_time_confidence REAL DEFAULT 0.0,
                    scene_scope TEXT,
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(trigger_event) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(speaker_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS life_status_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    subject_surface TEXT,
                    linked_event_id INTEGER,
                    supersedes_evidence_id INTEGER,
                    actual_status TEXT DEFAULT 'unknown',
                    belief_status TEXT DEFAULT 'unknown',
                    appearance_status TEXT DEFAULT 'unknown',
                    belief_owner_type TEXT DEFAULT 'unknown',
                    belief_owner_entity_id INTEGER,
                    reader_visible INTEGER DEFAULT 1,
                    participation_type TEXT DEFAULT 'active_scene',
                    observation_type TEXT DEFAULT 'direct',
                    status_reason TEXT DEFAULT 'unknown',
                    missing_subtype TEXT,
                    identity_continuity_mode TEXT DEFAULT 'unknown',
                    identity_evidence_id INTEGER,
                    concealment_alias_id INTEGER,
                    confidence REAL DEFAULT 0.5,
                    chapter INTEGER,
                    last_observation_chapter INTEGER,
                    last_confirmation_chapter INTEGER,
                    story_time_text TEXT,
                    story_time_confidence REAL DEFAULT 0.0,
                    narrative_order INTEGER,
                    timeline_position REAL,
                    evidence_text TEXT,
                    evidence_source_type TEXT DEFAULT 'observed_fact',
                    actuality_status TEXT DEFAULT 'actual',
                    source_pov_id INTEGER,
                    source_speaker_id INTEGER,
                    narrator_entity_id INTEGER,
                    scene_scope TEXT,
                    source_section_type TEXT DEFAULT 'CHAPTER',
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    resolver_version TEXT DEFAULT 'life_status_resolver_v1',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(linked_event_id) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(supersedes_evidence_id) REFERENCES life_status_evidence(id) ON DELETE SET NULL,
                    FOREIGN KEY(identity_evidence_id) REFERENCES identity_resolution_evidence(id) ON DELETE SET NULL,
                    FOREIGN KEY(concealment_alias_id) REFERENCES aliases(id) ON DELETE SET NULL,
                    FOREIGN KEY(belief_owner_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS life_status_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    scope_type TEXT DEFAULT 'global_story',
                    scope_owner_entity_id INTEGER,
                    actual_status TEXT DEFAULT 'unknown',
                    belief_status TEXT DEFAULT 'unknown',
                    appearance_status TEXT DEFAULT 'unknown',
                    confidence REAL DEFAULT 0.0,
                    evidence_count INTEGER DEFAULT 0,
                    latest_evidence_id INTEGER,
                    last_observation_chapter INTEGER,
                    last_confirmation_chapter INTEGER,
                    status_age INTEGER DEFAULT 0,
                    source_evidence_ids TEXT,
                    resolver_version TEXT DEFAULT 'life_status_resolver_v1',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(entity_id, scope_type, scope_owner_entity_id),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(scope_owner_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(latest_evidence_id) REFERENCES life_status_evidence(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS life_status_timeline_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    scope_type TEXT DEFAULT 'global_story',
                    scope_owner_entity_id INTEGER,
                    start_chapter INTEGER,
                    end_chapter INTEGER,
                    actual_status TEXT DEFAULT 'unknown',
                    belief_status TEXT DEFAULT 'unknown',
                    appearance_status TEXT DEFAULT 'unknown',
                    confidence REAL DEFAULT 0.0,
                    source_evidence_ids TEXT,
                    timeline_position REAL,
                    resolver_version TEXT DEFAULT 'life_status_resolver_v1',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(scope_owner_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_legacy_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    subject_surface TEXT,
                    signal_type TEXT DEFAULT 'legacy',
                    chapter INTEGER,
                    evidence_text TEXT,
                    confidence REAL DEFAULT 0.5,
                    historical_importance REAL DEFAULT 0.0,
                    emotional_importance REAL DEFAULT 0.0,
                    political_importance REAL DEFAULT 0.0,
                    familial_importance REAL DEFAULT 0.0,
                    memory_strength REAL DEFAULT 0.0,
                    linked_event_id INTEGER,
                    source_pov_id INTEGER,
                    source_speaker_id INTEGER,
                    narrator_entity_id INTEGER,
                    scene_scope TEXT,
                    source_section_type TEXT DEFAULT 'CHAPTER',
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(linked_event_id) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_semantic_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_entity_id INTEGER,
                    target_entity_id INTEGER,
                    relation_type TEXT NOT NULL,
                    relation_category TEXT DEFAULT 'semantic',
                    source_surface TEXT,
                    target_surface TEXT,
                    chapter INTEGER,
                    confidence REAL DEFAULT 0.55,
                    source_text TEXT,
                    ontology_source TEXT DEFAULT 'LLM',
                    status TEXT DEFAULT 'observed',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(target_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS language_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    surface_text TEXT NOT NULL,
                    normalized_text TEXT,
                    language TEXT DEFAULT 'unknown',
                    writing_system TEXT DEFAULT 'unknown',
                    translation_status TEXT DEFAULT 'unknown',
                    decoder_source TEXT,
                    first_seen INTEGER,
                    resolved_chapter INTEGER,
                    confidence REAL DEFAULT 0.5,
                    source_section_type TEXT DEFAULT 'CHAPTER',
                    source_quote TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_name TEXT,
                    alias_key TEXT,
                    entity_id INTEGER,
                    chapter_found INTEGER,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.35,
                    support_count INTEGER DEFAULT 1,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    status TEXT DEFAULT 'candidate',
                    UNIQUE(alias_name, entity_id),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mention_occurrences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    surface_form TEXT NOT NULL,
                    normalized_form TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    sentence_offset INTEGER,
                    paragraph_offset INTEGER,
                    speaker TEXT,
                    addressee TEXT,
                    mention_class TEXT DEFAULT 'entity',
                    title_category TEXT,
                    narrator_entity_id INTEGER,
                    scene_scope TEXT,
                    entity_type_guess TEXT,
                    confidence REAL DEFAULT 0.5,
                    source_quote TEXT,
                    linked_entity_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(linked_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS unresolved_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mention_text TEXT NOT NULL,
                    mention_key TEXT NOT NULL,
                    entity_type TEXT,
                    chapter INTEGER NOT NULL,
                    candidate_entities TEXT,
                    confidence REAL DEFAULT 0.0,
                    ambiguous INTEGER DEFAULT 1,
                    reason TEXT,
                    mention_class TEXT DEFAULT 'entity',
                    title_category TEXT,
                    speaker_entity_id INTEGER,
                    narrator_entity_id INTEGER,
                    scene_scope TEXT,
                    resolver_version TEXT DEFAULT 'resolver_v1',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(speaker_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reference_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    surface_form TEXT NOT NULL,
                    normalized_form TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    entity_type_guess TEXT,
                    reference_subtype TEXT DEFAULT 'reference',
                    reference_context TEXT,
                    participation_score REAL DEFAULT 0.0,
                    reference_score REAL DEFAULT 0.0,
                    score_breakdown TEXT,
                    promotion_state TEXT DEFAULT 'reference',
                    linked_entity_id INTEGER,
                    narrator_entity_id INTEGER,
                    scene_scope TEXT,
                    source_section_type TEXT DEFAULT 'CHAPTER',
                    source_quote TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(linked_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS name_semantic_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    relation_type TEXT NOT NULL,
                    source_surface TEXT,
                    source_normalized TEXT,
                    target_surface TEXT,
                    target_normalized TEXT,
                    source_entity_id INTEGER,
                    target_entity_id INTEGER,
                    reference_mention_id INTEGER,
                    chapter INTEGER,
                    reference_subtype TEXT DEFAULT 'reference',
                    relation_context TEXT,
                    source_section_type TEXT DEFAULT 'CHAPTER',
                    source_quote TEXT,
                    confidence REAL DEFAULT 0.55,
                    status TEXT DEFAULT 'observed',
                    resolver_version TEXT DEFAULT 'resolver_v1',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(target_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(reference_mention_id) REFERENCES reference_mentions(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kinship_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mention_text TEXT NOT NULL,
                    mention_key TEXT NOT NULL,
                    kinship_term TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    speaker_entity_id INTEGER,
                    narrator_entity_id INTEGER,
                    resolved_entity_id INTEGER,
                    candidate_entities TEXT,
                    confidence REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'unresolved',
                    evidence TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(speaker_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(resolved_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS title_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    title_text TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    chapter_found INTEGER,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.55,
                    support_count INTEGER DEFAULT 1,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    status TEXT DEFAULT 'candidate',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(entity_id, title_key),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS identity_promotions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    placeholder_entity_id INTEGER,
                    resolved_entity_id INTEGER NOT NULL,
                    chapter INTEGER NOT NULL,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.75,
                    status TEXT DEFAULT 'candidate',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(placeholder_entity_id, resolved_entity_id),
                    FOREIGN KEY(placeholder_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(resolved_entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_type_votes (
                    entity_id INTEGER,
                    entity_type TEXT,
                    support_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.55,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    PRIMARY KEY (entity_id, entity_type),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)
            
            # P0 Fix: Symmetric naming conventions to prevent future developer confusion
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS merge_candidates (
                    entity_a_id INTEGER,
                    entity_b_id INTEGER,
                    votes INTEGER DEFAULT 1,
                    score REAL DEFAULT 0.0,
                    state TEXT DEFAULT 'candidate',
                    evidence TEXT,
                    last_seen_chapter INTEGER,
                    resolver_version TEXT DEFAULT 'resolver_v1',
                    PRIMARY KEY (entity_a_id, entity_b_id),
                    FOREIGN KEY(entity_a_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_b_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS identity_resolution_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_entity_id INTEGER,
                    target_entity_id INTEGER,
                    mention_text TEXT NOT NULL,
                    mention_key TEXT NOT NULL,
                    entity_type TEXT,
                    chapter INTEGER,
                    state TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    score REAL DEFAULT 0.0,
                    margin REAL DEFAULT 0.0,
                    candidate_count INTEGER DEFAULT 0,
                    ambiguity_reason TEXT,
                    evidence_type TEXT DEFAULT 'resolver',
                    evidence TEXT,
                    resolver_version TEXT DEFAULT 'resolver_v1',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(target_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ghost_merge_candidates (
                    target_id INTEGER PRIMARY KEY,
                    votes INTEGER DEFAULT 1,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS merge_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    surviving_entity_id INTEGER,
                    losing_entity_id INTEGER,
                    surviving_name TEXT,
                    losing_name TEXT,
                    votes INTEGER DEFAULT 0,
                    score REAL DEFAULT 0.0,
                    evidence TEXT,
                    resolver_version TEXT DEFAULT 'resolver_v1',
                    reason TEXT,
                    merged_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_pov (
                    chapter INTEGER PRIMARY KEY,
                    entity_id INTEGER,
                    narrator_type TEXT DEFAULT 'unknown',
                    narrator_confidence REAL DEFAULT 0.0,
                    source_evidence TEXT,
                    scene_scope TEXT,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_evidence_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    source_hash TEXT,
                    trigger_reason TEXT NOT NULL DEFAULT 'legacy_import',
                    source_metadata_json TEXT NOT NULL DEFAULT '{}',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter, revision)
                )
            """)

            # Operational parse artifacts are intentionally separate from the
            # immutable chapter evidence revisions. Exact hashes are cache
            # identities; perceptual hashes are only occurrence diagnostics.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_parse_cache (
                    image_hash TEXT NOT NULL,
                    parser_fingerprint TEXT NOT NULL,
                    parse_output_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (image_hash, parser_fingerprint)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_evidence_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_evidence_revision_id INTEGER NOT NULL,
                    chapter INTEGER NOT NULL,
                    occurrence_order INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    image_hash TEXT NOT NULL DEFAULT '',
                    parser_fingerprint TEXT NOT NULL DEFAULT '',
                    schema_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter, occurrence_order, revision),
                    FOREIGN KEY(chapter_evidence_revision_id) REFERENCES chapter_evidence_revisions(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_occurrence_provenance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_evidence_revision_id INTEGER NOT NULL UNIQUE,
                    chapter INTEGER NOT NULL,
                    occurrence_order INTEGER NOT NULL,
                    source_locator TEXT NOT NULL DEFAULT '',
                    document_item_id TEXT NOT NULL DEFAULT '',
                    member_path TEXT NOT NULL DEFAULT '',
                    caption_text TEXT NOT NULL DEFAULT '',
                    alt_text TEXT NOT NULL DEFAULT '',
                    perceptual_hash TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(image_evidence_revision_id) REFERENCES image_evidence_revisions(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reader_snapshot_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    contract_version TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    evidence_revision_id INTEGER,
                    trigger_reason TEXT NOT NULL,
                    changed_resolvers_json TEXT NOT NULL DEFAULT '[]',
                    resolver_manifest_json TEXT NOT NULL DEFAULT '{}',
                    version_metadata_json TEXT NOT NULL DEFAULT '{}',
                    change_summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter, revision),
                    FOREIGN KEY(evidence_revision_id) REFERENCES chapter_evidence_revisions(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reader_snapshot_current (
                    chapter INTEGER PRIMARY KEY,
                    snapshot_revision_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(snapshot_revision_id) REFERENCES reader_snapshot_revisions(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_processing_checkpoints (
                    chapter INTEGER PRIMARY KEY,
                    evidence_revision_id INTEGER,
                    evidence_hash TEXT,
                    resolver_manifest_json TEXT NOT NULL DEFAULT '{}',
                    resolver_manifest_hash TEXT,
                    graph_schema_version INTEGER,
                    snapshot_revision_id INTEGER,
                    snapshot_hash TEXT,
                    parent_graph_hash TEXT,
                    state TEXT NOT NULL DEFAULT 'pending',
                    error_text TEXT,
                    completed_at TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(evidence_revision_id) REFERENCES chapter_evidence_revisions(id),
                    FOREIGN KEY(snapshot_revision_id) REFERENCES reader_snapshot_revisions(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_invalidations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_chapter INTEGER NOT NULL,
                    to_chapter INTEGER,
                    reason TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resolver_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_key TEXT NOT NULL UNIQUE,
                    resolver_key TEXT NOT NULL,
                    resolver_version TEXT NOT NULL,
                    subject_type TEXT NOT NULL,
                    subject_key TEXT NOT NULL,
                    chapter INTEGER,
                    decision TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    visibility TEXT NOT NULL DEFAULT 'engine',
                    supporting_evidence_json TEXT NOT NULL DEFAULT '[]',
                    contradicting_evidence_json TEXT NOT NULL DEFAULT '[]',
                    rejected_alternatives_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "INSERT OR REPLACE INTO schema_metadata (key, value) VALUES ('graph_schema_version', ?)",
                (str(GRAPH_SCHEMA_VERSION),)
            )
            for key, value in {
                "bookbuddy_version": BOOKBUDDY_VERSION,
                "cache_version": CACHE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "model_name": GEMINI_MODEL_NAME,
                "normalization_version": NORMALIZATION_VERSION,
                "snapshot_contract_version": SNAPSHOT_CONTRACT_VERSION,
                "replay_version": REPLAY_VERSION,
                "resolver_manifest": json.dumps(RESOLVER_VERSIONS, sort_keys=True),
                "image_evidence_schema_version": IMAGE_EVIDENCE_SCHEMA_VERSION,
            }.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO schema_metadata (key, value) VALUES (?, ?)",
                    (key, str(value)),
                )
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    rel_key TEXT PRIMARY KEY,
                    source_id INTEGER,
                    target_id INTEGER,
                    current_trust_score REAL,
                    current_hostility_score REAL DEFAULT 0.0,
                    current_respect_score REAL DEFAULT 0.0,
                    current_fear_score REAL DEFAULT 0.0,
                    relation_type TEXT DEFAULT 'interaction',
                    source_pov_id INTEGER,
                    source_speaker_id INTEGER,
                    scene_scope TEXT,
                    last_event_id INTEGER,
                    last_updated_chapter INTEGER,
                    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(last_event_id) REFERENCES events(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    event_order INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    normalized_summary TEXT NOT NULL,
                    event_type TEXT DEFAULT 'plot',
                    event_identity_key TEXT,
                    observed_by_entity_id INTEGER,
                    narrator_entity_id INTEGER,
                    narrator_scope TEXT,
                    scene_scope TEXT,
                    evidence_source_type TEXT DEFAULT 'observed_fact',
                    actuality_status TEXT DEFAULT 'actual',
                    narrative_order INTEGER,
                    story_time_text TEXT,
                    story_time_confidence REAL DEFAULT 0.0,
                    source_section_type TEXT DEFAULT 'CHAPTER',
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    confidence REAL DEFAULT 0.7,
                    source_payload TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter, normalized_summary),
                    FOREIGN KEY(observed_by_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_landmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_key TEXT UNIQUE NOT NULL,
                    lifecycle TEXT DEFAULT 'candidate',
                    landmark_type TEXT DEFAULT 'event',
                    event_state TEXT DEFAULT 'unknown',
                    event_reliability TEXT DEFAULT 'unknown',
                    reader_visibility TEXT DEFAULT 'partially_known',
                    geographic_scope TEXT DEFAULT 'unknown',
                    historical_start_text TEXT,
                    historical_end_text TEXT,
                    historical_start_sort REAL,
                    historical_end_sort REAL,
                    duration_text TEXT,
                    narrative_first_chapter INTEGER,
                    reader_known_since_chapter INTEGER,
                    story_discovery_time_text TEXT,
                    story_discovery_confidence REAL DEFAULT 0.0,
                    boundary_confidence REAL DEFAULT 0.5,
                    identity_confidence REAL DEFAULT 0.5,
                    merge_confidence REAL DEFAULT 0.0,
                    preferred_name_id INTEGER,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_names (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    landmark_id INTEGER NOT NULL,
                    name_text TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    name_role TEXT DEFAULT 'public',
                    name_source_type TEXT DEFAULT 'unknown',
                    audience_type TEXT DEFAULT 'reader',
                    source_entity_id INTEGER,
                    faction_entity_id INTEGER,
                    source_entity_text TEXT,
                    faction_text TEXT,
                    framing_polarity TEXT DEFAULT 'neutral',
                    literal_status TEXT DEFAULT 'literal',
                    first_known_chapter INTEGER,
                    narrative_order INTEGER,
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    status TEXT DEFAULT 'accepted',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(faction_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_hierarchy (
                    parent_landmark_id INTEGER NOT NULL,
                    child_landmark_id INTEGER NOT NULL,
                    relation_type TEXT DEFAULT 'contains',
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    PRIMARY KEY(parent_landmark_id, child_landmark_id, relation_type),
                    FOREIGN KEY(parent_landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(child_landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_event_links (
                    landmark_id INTEGER NOT NULL,
                    event_id INTEGER NOT NULL,
                    link_type TEXT DEFAULT 'occurrence',
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    PRIMARY KEY(landmark_id, event_id, link_type),
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_perspectives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    landmark_id INTEGER NOT NULL,
                    perspective_type TEXT DEFAULT 'neutral',
                    summary TEXT NOT NULL,
                    source_entity_id INTEGER,
                    faction_entity_id INTEGER,
                    source_entity_text TEXT,
                    faction_text TEXT,
                    chapter INTEGER,
                    reader_visibility TEXT DEFAULT 'partially_known',
                    reliability TEXT DEFAULT 'unknown',
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(faction_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_importance (
                    landmark_id INTEGER NOT NULL,
                    dimension TEXT NOT NULL,
                    score REAL NOT NULL,
                    chapter INTEGER,
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    PRIMARY KEY(landmark_id, dimension, chapter),
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_locations (
                    landmark_id INTEGER NOT NULL,
                    location_entity_id INTEGER NOT NULL,
                    location_role TEXT DEFAULT 'secondary',
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    PRIMARY KEY(landmark_id, location_entity_id, location_role),
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(location_entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_participants (
                    landmark_id INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    role TEXT DEFAULT 'participant',
                    source_event_id INTEGER,
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    PRIMARY KEY(landmark_id, entity_id, role, source_event_id),
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_event_id) REFERENCES events(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_assertions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    landmark_id INTEGER NOT NULL,
                    assertion_type TEXT NOT NULL,
                    assertion_value TEXT NOT NULL,
                    chapter INTEGER,
                    story_time_text TEXT,
                    story_time_sort REAL,
                    source_event_id INTEGER,
                    source_entity_id INTEGER,
                    confidence REAL DEFAULT 0.5,
                    evidence TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_event_id) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS landmark_resolution_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER,
                    landmark_id INTEGER,
                    chapter INTEGER,
                    decision TEXT NOT NULL,
                    identity_confidence REAL DEFAULT 0.0,
                    merge_confidence REAL DEFAULT 0.0,
                    supporting_evidence TEXT,
                    contradicting_evidence TEXT,
                    signals TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(landmark_id) REFERENCES event_landmarks(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_key TEXT UNIQUE NOT NULL,
                    representative_summary TEXT NOT NULL,
                    confidence REAL DEFAULT 0.7,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_cluster_members (
                    cluster_id INTEGER,
                    event_id INTEGER,
                    confidence REAL DEFAULT 0.7,
                    PRIMARY KEY(cluster_id, event_id),
                    FOREIGN KEY(cluster_id) REFERENCES event_clusters(id) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_participants (
                    event_id INTEGER,
                    entity_id INTEGER,
                    role TEXT DEFAULT 'participant',
                    confidence REAL DEFAULT 0.7,
                    observed_by_entity_id INTEGER,
                    scene_scope TEXT,
                    PRIMARY KEY(event_id, entity_id, role),
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(observed_by_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_consequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER,
                    consequence_type TEXT DEFAULT 'relationship_change',
                    target_entity_id INTEGER,
                    rel_key TEXT,
                    description TEXT,
                    trust_delta INTEGER,
                    confidence REAL DEFAULT 0.7,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_causal_edges (
                    parent_event_id INTEGER,
                    child_event_id INTEGER,
                    relation_type TEXT DEFAULT 'causes',
                    confidence REAL DEFAULT 0.5,
                    PRIMARY KEY(parent_event_id, child_event_id, relation_type),
                    FOREIGN KEY(parent_event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(child_event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rel_key TEXT,
                    chapter INTEGER,
                    interaction_order INTEGER,
                    interaction_type TEXT DEFAULT 'interaction',
                    trust_score INTEGER,
                    hostility_score REAL DEFAULT 0.0,
                    respect_score REAL DEFAULT 0.0,
                    fear_score REAL DEFAULT 0.0,
                    reason TEXT,
                    evidence TEXT,
                    evidence_source_type TEXT DEFAULT 'observed_fact',
                    source_pov_id INTEGER,
                    source_speaker_id INTEGER,
                    scene_scope TEXT,
                    confidence REAL DEFAULT 0.7,
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    event_id INTEGER,
                    consequence_id INTEGER,
                    FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE,
                    FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(consequence_id) REFERENCES event_consequences(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_social_edges (
                    edge_key TEXT PRIMARY KEY,
                    source_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    edge_layer TEXT DEFAULT 'cooccurrence',
                    edge_subtype TEXT DEFAULT 'general',
                    directional INTEGER DEFAULT 0,
                    support_count INTEGER DEFAULT 0,
                    shared_scene_count INTEGER DEFAULT 0,
                    shared_event_count INTEGER DEFAULT 0,
                    chapter_overlap_count INTEGER DEFAULT 0,
                    dialogue_overlap_count INTEGER DEFAULT 0,
                    familiarity_signal REAL DEFAULT 0.0,
                    trust_signal REAL DEFAULT 0.0,
                    hostility_signal REAL DEFAULT 0.0,
                    cooperation_signal REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.25,
                    promotion_state TEXT DEFAULT 'weak',
                    evidence_summary TEXT,
                    evidence_source_type TEXT DEFAULT 'observed_fact',
                    actuality_status TEXT DEFAULT 'actual',
                    source_pov_id INTEGER,
                    source_speaker_id INTEGER,
                    scene_scope TEXT,
                    first_seen_chapter INTEGER,
                    last_seen_chapter INTEGER,
                    last_event_id INTEGER,
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(last_event_id) REFERENCES events(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_social_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    edge_key TEXT NOT NULL,
                    evidence_key TEXT UNIQUE NOT NULL,
                    source_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    edge_layer TEXT DEFAULT 'cooccurrence',
                    edge_subtype TEXT DEFAULT 'general',
                    directional INTEGER DEFAULT 0,
                    chapter INTEGER,
                    event_id INTEGER,
                    evidence_scope TEXT,
                    evidence_summary TEXT,
                    shared_scene_count INTEGER DEFAULT 0,
                    shared_event_count INTEGER DEFAULT 0,
                    chapter_overlap_count INTEGER DEFAULT 0,
                    dialogue_overlap_count INTEGER DEFAULT 0,
                    familiarity_signal REAL DEFAULT 0.0,
                    trust_signal REAL DEFAULT 0.0,
                    hostility_signal REAL DEFAULT 0.0,
                    cooperation_signal REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.25,
                    evidence_source_type TEXT DEFAULT 'observed_fact',
                    actuality_status TEXT DEFAULT 'actual',
                    source_pov_id INTEGER,
                    source_speaker_id INTEGER,
                    scene_scope TEXT,
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(edge_key) REFERENCES relationship_social_edges(edge_key) ON DELETE CASCADE,
                    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_communities (
                    community_key TEXT PRIMARY KEY,
                    algorithm TEXT DEFAULT 'component_density_v1',
                    member_count INTEGER DEFAULT 0,
                    edge_count INTEGER DEFAULT 0,
                    density REAL DEFAULT 0.0,
                    cohesion_score REAL DEFAULT 0.0,
                    bridge_count INTEGER DEFAULT 0,
                    evidence_summary TEXT,
                    first_seen_chapter INTEGER,
                    last_seen_chapter INTEGER,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_community_members (
                    community_key TEXT,
                    entity_id INTEGER,
                    role TEXT DEFAULT 'member',
                    local_degree INTEGER DEFAULT 0,
                    bridge_score REAL DEFAULT 0.0,
                    cluster_strength REAL DEFAULT 0.0,
                    PRIMARY KEY(community_key, entity_id),
                    FOREIGN KEY(community_key) REFERENCES relationship_communities(community_key) ON DELETE CASCADE,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_social_metrics (
                    entity_id INTEGER PRIMARY KEY,
                    direct_degree INTEGER DEFAULT 0,
                    social_degree INTEGER DEFAULT 0,
                    community_count INTEGER DEFAULT 0,
                    local_density REAL DEFAULT 0.0,
                    bridge_score REAL DEFAULT 0.0,
                    cluster_strength REAL DEFAULT 0.0,
                    last_computed_chapter INTEGER,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_boundaries (
                    chapter INTEGER PRIMARY KEY,
                    library_id TEXT,
                    title_id TEXT,
                    book_id TEXT,
                    volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_visibility_scopes (
                    chapter INTEGER PRIMARY KEY,
                    observed_by_entity_id INTEGER,
                    narrator_entity_id INTEGER,
                    narrator_scope TEXT DEFAULT 'unknown',
                    scene_scope TEXT,
                    confidence REAL DEFAULT 0.0,
                    source_evidence TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(observed_by_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(narrator_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    metric_unit TEXT DEFAULT 'count',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conflict_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conflict_type TEXT NOT NULL,
                    entity_a_id INTEGER,
                    entity_b_id INTEGER,
                    chapter INTEGER,
                    payload TEXT,
                    resolver_key TEXT,
                    subject_type TEXT,
                    subject_key TEXT,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    alternatives_json TEXT NOT NULL DEFAULT '[]',
                    severity INTEGER DEFAULT 6,
                    status TEXT DEFAULT 'open',
                    reviewed_at TEXT,
                    resolution TEXT,
                    resolved_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_a_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(entity_b_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_search_terms (
                    entity_id INTEGER NOT NULL,
                    term TEXT NOT NULL,
                    term_type TEXT NOT NULL,
                    status TEXT DEFAULT 'accepted',
                    PRIMARY KEY(entity_id, term, term_type),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_search_terms (
                    event_id INTEGER NOT NULL,
                    term TEXT NOT NULL,
                    term_type TEXT NOT NULL,
                    PRIMARY KEY(event_id, term, term_type),
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)
            self._migrate_table_columns(conn)
            self._migrate_entities_schema(conn)
            self._migrate_relationship_history_schema(conn)
            self._backfill_image_evidence_v2(conn)
            conn.commit()

    def _add_column_if_missing(self, conn, table_name: str, column_name: str, definition: str):
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _search_terms_for_text(self, text: str, max_ngram: int = 5) -> set[str]:
        normalized = self.normalize_alias_key(text)
        if not normalized:
            return set()
        cache_key = (normalized, max_ngram)
        if len(normalized) <= 160 and cache_key in self._search_terms_cache:
            self._search_terms_cache.move_to_end(cache_key)
            return set(self._search_terms_cache[cache_key])
        raw_tokens = [token for token in normalized.split() if token not in SEARCH_TERM_STOPWORDS]
        long_text = len(raw_tokens) > SEARCH_TERMS_LONG_TEXT_TOKEN_LIMIT
        seen_tokens = set()
        tokens = []
        for token in raw_tokens:
            if len(token) <= 1 or token in seen_tokens:
                continue
            seen_tokens.add(token)
            tokens.append(token)
            if long_text and len(tokens) >= SEARCH_TERMS_LONG_TEXT_TERM_LIMIT:
                break
        terms = {normalized} if len(normalized) <= 160 else set()
        terms.update(tokens)
        ngram_cap = min(max_ngram, len(tokens))
        if long_text:
            ngram_cap = 1
        elif len(tokens) <= 5:
            ngram_cap = min(ngram_cap, 3)
        for size in range(2, ngram_cap + 1):
            for idx in range(0, len(tokens) - size + 1):
                terms.add(" ".join(tokens[idx:idx + size]))
        if len(normalized) <= 160:
            self._search_terms_cache[cache_key] = frozenset(terms)
            if len(self._search_terms_cache) > REGEX_CACHE_SIZE:
                self._search_terms_cache.popitem(last=False)
        return terms

    def _chapter_lookup_terms(self, chapter_text_lower: str) -> set[str]:
        return self._search_terms_for_text(chapter_text_lower, max_ngram=5)

    def _upsert_entity_search_term(
        self,
        conn,
        entity_id: int,
        term: str,
        term_type: str,
        status: str = "accepted",
    ):
        term_key = self.normalize_alias_key(term)
        if not entity_id or not term_key:
            return
        conn.execute("""
            INSERT INTO entity_search_terms (entity_id, term, term_type, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(entity_id, term, term_type) DO UPDATE SET
                status = excluded.status
        """, (entity_id, term_key, term_type, status))

    def _sync_entity_search_terms(self, conn, entity_id: int):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT canonical_name
            FROM entities
            WHERE id = ?
        """, (entity_id,))
        row = cursor.fetchone()
        if not row:
            return
        conn.execute("DELETE FROM entity_search_terms WHERE entity_id = ?", (entity_id,))
        canonical_name = row[0]
        for term in self._search_terms_for_text(canonical_name):
            self._upsert_entity_search_term(conn, entity_id, term, "canonical", "accepted")

        cursor.execute("""
            SELECT alias_name, alias_key, status
            FROM aliases
            WHERE entity_id = ?
              AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """, (entity_id,))
        for alias_name, alias_key, status in cursor.fetchall():
            self._upsert_entity_search_term(conn, entity_id, alias_key or alias_name, "alias", status)

        cursor.execute("""
            SELECT title_text, title_key, status
            FROM title_links
            WHERE entity_id = ?
              AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """, (entity_id,))
        for title_text, title_key, status in cursor.fetchall():
            self._upsert_entity_search_term(conn, entity_id, title_key or title_text, "title", status)

    def _mark_entity_search_dirty(self, conn, entity_id: int):
        if not entity_id:
            return
        if self._defer_search_sync_depth > 0:
            self._dirty_entity_search_ids.add(entity_id)
            return
        self._sync_entity_search_terms(conn, entity_id)

    def flush_dirty_entity_search_terms(self):
        if not self._dirty_entity_search_ids:
            return
        with self._get_connection() as conn:
            dirty_ids = sorted(self._dirty_entity_search_ids)
            self._dirty_entity_search_ids.clear()
            for entity_id in dirty_ids:
                self._sync_entity_search_terms(conn, entity_id)

    @contextmanager
    def defer_entity_search_sync(self):
        self._defer_search_sync_depth += 1
        try:
            yield
        finally:
            self._defer_search_sync_depth -= 1
            if self._defer_search_sync_depth == 0:
                self.flush_dirty_entity_search_terms()

    def _sync_event_search_terms(self, conn, event_id: int):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT summary, normalized_summary
            FROM events
            WHERE id = ?
        """, (event_id,))
        row = cursor.fetchone()
        if not row:
            return
        conn.execute("DELETE FROM event_search_terms WHERE event_id = ?", (event_id,))
        summary, normalized_summary = row
        for term in self._search_terms_for_text(summary):
            conn.execute("""
                INSERT OR IGNORE INTO event_search_terms (event_id, term, term_type)
                VALUES (?, ?, 'summary')
            """, (event_id, term))
        if normalized_summary:
            conn.execute("""
                INSERT OR IGNORE INTO event_search_terms (event_id, term, term_type)
                VALUES (?, ?, 'summary')
            """, (event_id, normalized_summary))

        cursor.execute("""
            SELECT e.canonical_name
            FROM event_participants ep
            JOIN entities e ON ep.entity_id = e.id
            WHERE ep.event_id = ?
        """, (event_id,))
        for (participant_name,) in cursor.fetchall():
            for term in self._search_terms_for_text(participant_name):
                conn.execute("""
                    INSERT OR IGNORE INTO event_search_terms (event_id, term, term_type)
                VALUES (?, ?, 'participant')
                """, (event_id, term))

        cursor.execute("""
            SELECT ln.name_text
            FROM events ev
            JOIN landmark_names ln ON ln.landmark_id = ev.landmark_id
            WHERE ev.id = ? AND COALESCE(ln.status, 'accepted') != 'rejected'
        """, (event_id,))
        for (landmark_name,) in cursor.fetchall():
            for term in self._search_terms_for_text(landmark_name):
                conn.execute("""
                    INSERT OR IGNORE INTO event_search_terms (event_id, term, term_type)
                    VALUES (?, ?, 'landmark_name')
                """, (event_id, term))

    def _ranked_entity_candidates(
        self,
        conn,
        chapter_text_lower: str,
        limit: int,
        entity_type: str | None = None,
    ) -> list[int]:
        lookup_terms = list(self._chapter_lookup_terms(chapter_text_lower))
        if not lookup_terms:
            return []
        cursor = conn.cursor()
        scores: dict[int, int] = {}
        for offset in range(0, len(lookup_terms), 800):
            chunk = lookup_terms[offset:offset + 800]
            placeholders = ",".join("?" for _ in chunk)
            params = chunk
            type_filter = ""
            if entity_type:
                type_filter = " AND e.entity_type = ?"
                params = [*params, entity_type]
            cursor.execute(f"""
                SELECT est.entity_id, COUNT(*) AS hits
                FROM entity_search_terms est
                JOIN entities e ON e.id = est.entity_id
                WHERE est.term IN ({placeholders})
                  AND est.status IN ('accepted', 'probable', 'candidate', 'review')
                  {type_filter}
                GROUP BY est.entity_id
            """, params)
            for entity_id, hits in cursor.fetchall():
                scores[entity_id] = scores.get(entity_id, 0) + hits
        if not scores:
            return []
        ranked_ids = sorted(scores, key=lambda entity_id: (-scores[entity_id], entity_id))
        placeholders = ",".join("?" for _ in ranked_ids)
        cursor.execute(f"""
            SELECT id
            FROM entities
            WHERE id IN ({placeholders})
            ORDER BY visibility_score DESC, importance_score DESC,
                     last_verified_chapter DESC, mention_count DESC
            LIMIT ?
        """, (*ranked_ids, limit))
        return [entity_id for (entity_id,) in cursor.fetchall()]

    def _ranked_event_candidates(
        self,
        conn,
        chapter_text_lower: str,
        entity_ids: list[int],
        limit: int,
    ) -> list[int]:
        lookup_terms = list(self._chapter_lookup_terms(chapter_text_lower))
        cursor = conn.cursor()
        event_ids: set[int] = set()
        for offset in range(0, len(lookup_terms), 800):
            chunk = lookup_terms[offset:offset + 800]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            cursor.execute(f"""
                SELECT event_id
                FROM event_search_terms
                WHERE term IN ({placeholders})
                GROUP BY event_id
                ORDER BY COUNT(*) DESC
                LIMIT ?
            """, (*chunk, limit * 3))
            event_ids.update(event_id for (event_id,) in cursor.fetchall())

        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            cursor.execute(f"""
                SELECT event_id
                FROM event_participants
                WHERE entity_id IN ({placeholders})
                GROUP BY event_id
                LIMIT ?
            """, (*entity_ids, limit * 3))
            event_ids.update(event_id for (event_id,) in cursor.fetchall())

        if not event_ids:
            return []
        placeholders = ",".join("?" for _ in event_ids)
        cursor.execute(f"""
            SELECT id
            FROM events
            WHERE id IN ({placeholders})
            ORDER BY COALESCE(confidence, 1.0) DESC, chapter DESC, event_order DESC
            LIMIT ?
        """, (*event_ids, limit))
        return [event_id for (event_id,) in cursor.fetchall()]

    def _context_origin_label(self, inherited_confidence: float | None, source_session: str | None = None) -> str:
        confidence = inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE
        if confidence < 0.999:
            suffix = f", source: {source_session}" if source_session else ""
            return f"inherited confidence {confidence:.2f}{suffix}"
        return "local evidence"

    def _migrate_table_columns(self, conn):
        self._add_column_if_missing(conn, "entities", "display_name", "TEXT")
        self._add_column_if_missing(conn, "entities", "confidence", "REAL DEFAULT 0.55")
        self._add_column_if_missing(conn, "entities", "type_support_count", "INTEGER DEFAULT 1")
        self._add_column_if_missing(conn, "entities", "importance_score", "REAL DEFAULT 0.45")
        self._add_column_if_missing(conn, "entities", "visibility_score", "REAL DEFAULT 0.45")
        self._add_column_if_missing(conn, "entities", "surface_form_class", "TEXT DEFAULT 'proper_name'")
        self._add_column_if_missing(conn, "entities", "location_subtype", "TEXT")
        self._add_column_if_missing(conn, "entities", "entity_category", "TEXT DEFAULT 'UNKNOWN'")
        self._add_column_if_missing(conn, "entities", "species_or_kind", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "sentience", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "narrative_role", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "story_role", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "functional_role", "TEXT")
        self._add_column_if_missing(conn, "entities", "active_status", "TEXT DEFAULT 'uncertain'")
        self._add_column_if_missing(conn, "entities", "identity_status", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "entity_persistence", "TEXT DEFAULT 'persistent'")
        self._add_column_if_missing(conn, "entities", "canonical_identity", "TEXT")
        self._add_column_if_missing(conn, "entities", "body_form", "TEXT")
        self._add_column_if_missing(conn, "entities", "embodiment", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "agency_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "can_speak", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "can_move", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "can_think", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "can_remember", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "can_make_decisions", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "can_form_relationships", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "ontology_confidence", "REAL DEFAULT 0.5")
        self._add_column_if_missing(conn, "entities", "ontology_evidence", "TEXT")
        self._add_column_if_missing(conn, "entities", "literal_status", "TEXT DEFAULT 'literal'")
        self._add_column_if_missing(conn, "entities", "interpretation_status", "TEXT DEFAULT 'actual'")
        self._add_column_if_missing(conn, "entities", "language_status", "TEXT DEFAULT 'natural_language'")
        self._add_column_if_missing(conn, "entities", "translation_status", "TEXT DEFAULT 'not_applicable'")
        self._add_column_if_missing(conn, "entities", "raw_surface_form", "TEXT")
        self._add_column_if_missing(conn, "entities", "social_status", "TEXT")
        self._add_column_if_missing(conn, "entities", "current_life_status", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "entities", "life_confidence", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "life_status_chapter", "INTEGER")
        self._add_column_if_missing(conn, "entities", "life_status_source", "TEXT")
        self._add_column_if_missing(conn, "entities", "legacy_importance", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "memory_strength", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "historical_importance", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "emotional_importance", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "political_importance", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "familial_importance", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entities", "boundary_title_id", "TEXT")
        self._add_column_if_missing(conn, "entities", "boundary_book_id", "TEXT")
        self._add_column_if_missing(conn, "entities", "boundary_volume_id", "TEXT")
        self._add_column_if_missing(conn, "entities", "session_id", "TEXT")
        self._add_column_if_missing(conn, "entities", "source_session", "TEXT")
        self._add_column_if_missing(conn, "entities", "inherited_confidence", "REAL DEFAULT 1.0")
        self._add_column_if_missing(conn, "aliases", "alias_key", "TEXT")
        self._add_column_if_missing(conn, "aliases", "confidence", "REAL DEFAULT 0.85")
        self._add_column_if_missing(conn, "aliases", "support_count", "INTEGER DEFAULT 4")
        self._add_column_if_missing(conn, "aliases", "first_seen", "INTEGER")
        self._add_column_if_missing(conn, "aliases", "last_seen", "INTEGER")
        self._add_column_if_missing(conn, "aliases", "status", "TEXT DEFAULT 'accepted'")
        self._add_column_if_missing(conn, "aliases", "validation_status", "TEXT")
        self._add_column_if_missing(conn, "aliases", "validation_reason", "TEXT")
        self._add_column_if_missing(conn, "mention_occurrences", "addressee", "TEXT")
        self._add_column_if_missing(conn, "mention_occurrences", "mention_class", "TEXT DEFAULT 'entity'")
        self._add_column_if_missing(conn, "mention_occurrences", "title_category", "TEXT")
        self._add_column_if_missing(conn, "mention_occurrences", "narrator_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "mention_occurrences", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "mention_occurrences", "mention_source_type", "TEXT DEFAULT 'narration'")
        self._add_column_if_missing(conn, "mention_occurrences", "source_section_type", "TEXT DEFAULT 'CHAPTER'")
        self._add_column_if_missing(conn, "unresolved_mentions", "mention_class", "TEXT DEFAULT 'entity'")
        self._add_column_if_missing(conn, "unresolved_mentions", "title_category", "TEXT")
        self._add_column_if_missing(conn, "unresolved_mentions", "speaker_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "unresolved_mentions", "narrator_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "unresolved_mentions", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "unresolved_mentions", "mention_source_type", "TEXT DEFAULT 'narration'")
        self._add_column_if_missing(conn, "unresolved_mentions", "source_section_type", "TEXT DEFAULT 'CHAPTER'")
        self._add_column_if_missing(conn, "reference_mentions", "reference_subtype", "TEXT DEFAULT 'reference'")
        self._add_column_if_missing(conn, "reference_mentions", "reference_context", "TEXT")
        self._add_column_if_missing(conn, "reference_mentions", "participation_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "reference_mentions", "reference_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "reference_mentions", "score_breakdown", "TEXT")
        self._add_column_if_missing(conn, "reference_mentions", "promotion_state", "TEXT DEFAULT 'reference'")
        self._add_column_if_missing(conn, "reference_mentions", "linked_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "reference_mentions", "narrator_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "reference_mentions", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "reference_mentions", "source_section_type", "TEXT DEFAULT 'CHAPTER'")
        self._add_column_if_missing(conn, "reference_mentions", "source_quote", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "relation_type", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "source_surface", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "source_normalized", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "target_surface", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "target_normalized", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "source_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "name_semantic_relations", "target_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "name_semantic_relations", "reference_mention_id", "INTEGER")
        self._add_column_if_missing(conn, "name_semantic_relations", "chapter", "INTEGER")
        self._add_column_if_missing(conn, "name_semantic_relations", "reference_subtype", "TEXT DEFAULT 'reference'")
        self._add_column_if_missing(conn, "name_semantic_relations", "relation_context", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "source_section_type", "TEXT DEFAULT 'CHAPTER'")
        self._add_column_if_missing(conn, "name_semantic_relations", "source_quote", "TEXT")
        self._add_column_if_missing(conn, "name_semantic_relations", "confidence", "REAL DEFAULT 0.55")
        self._add_column_if_missing(conn, "name_semantic_relations", "status", "TEXT DEFAULT 'observed'")
        self._add_column_if_missing(conn, "name_semantic_relations", "resolver_version", "TEXT DEFAULT 'resolver_v1'")
        self._add_column_if_missing(conn, "identity_resolution_evidence", "candidate_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "identity_resolution_evidence", "ambiguity_reason", "TEXT")
        for table_name in ("entity_state_history",):
            self._add_column_if_missing(conn, table_name, "status_domain", "TEXT")
            self._add_column_if_missing(conn, table_name, "belief_scope", "TEXT")
            self._add_column_if_missing(conn, table_name, "source_entity_id", "INTEGER")
            self._add_column_if_missing(conn, table_name, "speaker_entity_id", "INTEGER")
            self._add_column_if_missing(conn, table_name, "narrator_entity_id", "INTEGER")
            self._add_column_if_missing(conn, table_name, "evidence_source_type", "TEXT")
            self._add_column_if_missing(conn, table_name, "actuality_status", "TEXT")
            self._add_column_if_missing(conn, table_name, "transition_type", "TEXT")
            self._add_column_if_missing(conn, table_name, "story_time_text", "TEXT")
            self._add_column_if_missing(conn, table_name, "story_time_confidence", "REAL DEFAULT 0.0")
            self._add_column_if_missing(conn, table_name, "scene_scope", "TEXT")
            self._add_column_if_missing(conn, table_name, "boundary_title_id", "TEXT")
            self._add_column_if_missing(conn, table_name, "boundary_book_id", "TEXT")
            self._add_column_if_missing(conn, table_name, "boundary_volume_id", "TEXT")
            self._add_column_if_missing(conn, table_name, "session_id", "TEXT")
            self._add_column_if_missing(conn, table_name, "source_session", "TEXT")
            self._add_column_if_missing(conn, table_name, "inherited_confidence", "REAL DEFAULT 1.0")
        life_columns = {
            "subject_surface": "TEXT",
            "linked_event_id": "INTEGER",
            "supersedes_evidence_id": "INTEGER",
            "actual_status": "TEXT DEFAULT 'unknown'",
            "belief_status": "TEXT DEFAULT 'unknown'",
            "appearance_status": "TEXT DEFAULT 'unknown'",
            "belief_owner_type": "TEXT DEFAULT 'unknown'",
            "belief_owner_entity_id": "INTEGER",
            "reader_visible": "INTEGER DEFAULT 1",
            "participation_type": "TEXT DEFAULT 'active_scene'",
            "observation_type": "TEXT DEFAULT 'direct'",
            "status_reason": "TEXT DEFAULT 'unknown'",
            "missing_subtype": "TEXT",
            "identity_continuity_mode": "TEXT DEFAULT 'unknown'",
            "identity_evidence_id": "INTEGER",
            "concealment_alias_id": "INTEGER",
            "confidence": "REAL DEFAULT 0.5",
            "chapter": "INTEGER",
            "last_observation_chapter": "INTEGER",
            "last_confirmation_chapter": "INTEGER",
            "story_time_text": "TEXT",
            "story_time_confidence": "REAL DEFAULT 0.0",
            "narrative_order": "INTEGER",
            "timeline_position": "REAL",
            "evidence_text": "TEXT",
            "evidence_source_type": "TEXT DEFAULT 'observed_fact'",
            "actuality_status": "TEXT DEFAULT 'actual'",
            "source_pov_id": "INTEGER",
            "source_speaker_id": "INTEGER",
            "narrator_entity_id": "INTEGER",
            "scene_scope": "TEXT",
            "source_section_type": "TEXT DEFAULT 'CHAPTER'",
            "boundary_title_id": "TEXT",
            "boundary_book_id": "TEXT",
            "boundary_volume_id": "TEXT",
            "session_id": "TEXT",
            "source_session": "TEXT",
            "inherited_confidence": "REAL DEFAULT 1.0",
            "resolver_version": "TEXT DEFAULT 'life_status_resolver_v1'",
        }
        for column_name, definition in life_columns.items():
            self._add_column_if_missing(conn, "life_status_evidence", column_name, definition)
        legacy_columns = {
            "subject_surface": "TEXT",
            "signal_type": "TEXT DEFAULT 'legacy'",
            "chapter": "INTEGER",
            "evidence_text": "TEXT",
            "confidence": "REAL DEFAULT 0.5",
            "historical_importance": "REAL DEFAULT 0.0",
            "emotional_importance": "REAL DEFAULT 0.0",
            "political_importance": "REAL DEFAULT 0.0",
            "familial_importance": "REAL DEFAULT 0.0",
            "memory_strength": "REAL DEFAULT 0.0",
            "linked_event_id": "INTEGER",
            "source_pov_id": "INTEGER",
            "source_speaker_id": "INTEGER",
            "narrator_entity_id": "INTEGER",
            "scene_scope": "TEXT",
            "source_section_type": "TEXT DEFAULT 'CHAPTER'",
            "boundary_title_id": "TEXT",
            "boundary_book_id": "TEXT",
            "boundary_volume_id": "TEXT",
            "session_id": "TEXT",
            "source_session": "TEXT",
            "inherited_confidence": "REAL DEFAULT 1.0",
        }
        for column_name, definition in legacy_columns.items():
            self._add_column_if_missing(conn, "entity_legacy_signals", column_name, definition)
        self._add_column_if_missing(conn, "merge_audit", "score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "merge_audit", "evidence", "TEXT")
        self._add_column_if_missing(conn, "merge_audit", "resolver_version", "TEXT DEFAULT 'resolver_v1'")
        self._add_column_if_missing(conn, "chapter_pov", "narrator_type", "TEXT DEFAULT 'unknown'")
        self._add_column_if_missing(conn, "chapter_pov", "narrator_confidence", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "chapter_pov", "source_evidence", "TEXT")
        self._add_column_if_missing(conn, "chapter_pov", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "relationships", "current_trust_score", "REAL")
        self._add_column_if_missing(conn, "relationships", "current_hostility_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationships", "current_respect_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationships", "current_fear_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationships", "relation_type", "TEXT DEFAULT 'interaction'")
        self._add_column_if_missing(conn, "relationships", "source_pov_id", "INTEGER")
        self._add_column_if_missing(conn, "relationships", "source_speaker_id", "INTEGER")
        self._add_column_if_missing(conn, "relationships", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "relationships", "last_event_id", "INTEGER")
        self._add_column_if_missing(conn, "relationships", "last_updated_chapter", "INTEGER")
        self._add_column_if_missing(conn, "events", "event_identity_key", "TEXT")
        self._add_column_if_missing(conn, "events", "observed_by_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "events", "narrator_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "events", "narrator_scope", "TEXT")
        self._add_column_if_missing(conn, "events", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "events", "evidence_source_type", "TEXT DEFAULT 'observed_fact'")
        self._add_column_if_missing(conn, "events", "actuality_status", "TEXT DEFAULT 'actual'")
        self._add_column_if_missing(conn, "events", "narrative_order", "INTEGER")
        self._add_column_if_missing(conn, "events", "story_time_text", "TEXT")
        self._add_column_if_missing(conn, "events", "story_time_confidence", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "events", "source_section_type", "TEXT DEFAULT 'CHAPTER'")
        self._add_column_if_missing(conn, "events", "boundary_title_id", "TEXT")
        self._add_column_if_missing(conn, "events", "boundary_book_id", "TEXT")
        self._add_column_if_missing(conn, "events", "boundary_volume_id", "TEXT")
        self._add_column_if_missing(conn, "events", "session_id", "TEXT")
        self._add_column_if_missing(conn, "events", "source_session", "TEXT")
        self._add_column_if_missing(conn, "events", "inherited_confidence", "REAL DEFAULT 1.0")
        self._add_column_if_missing(conn, "events", "landmark_id", "INTEGER")
        self._add_column_if_missing(conn, "events", "recurring_template_id", "INTEGER")
        self._add_column_if_missing(conn, "events", "occurrence_role", "TEXT DEFAULT 'occurrence'")
        self._add_column_if_missing(conn, "events", "historical_start_text", "TEXT")
        self._add_column_if_missing(conn, "events", "historical_end_text", "TEXT")
        self._add_column_if_missing(conn, "events", "historical_start_sort", "REAL")
        self._add_column_if_missing(conn, "events", "historical_end_sort", "REAL")
        self._add_column_if_missing(conn, "events", "duration_text", "TEXT")
        self._add_column_if_missing(conn, "events", "reader_known_since_chapter", "INTEGER")
        self._add_column_if_missing(conn, "landmark_names", "source_entity_text", "TEXT")
        self._add_column_if_missing(conn, "landmark_names", "faction_text", "TEXT")
        self._add_column_if_missing(conn, "landmark_perspectives", "source_entity_text", "TEXT")
        self._add_column_if_missing(conn, "landmark_perspectives", "faction_text", "TEXT")
        self._add_column_if_missing(conn, "event_participants", "observed_by_entity_id", "INTEGER")
        self._add_column_if_missing(conn, "event_participants", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "evidence", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "hostility_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_history", "respect_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_history", "fear_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_history", "evidence_source_type", "TEXT DEFAULT 'observed_fact'")
        self._add_column_if_missing(conn, "relationship_history", "source_pov_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_history", "source_speaker_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_history", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "confidence", "REAL DEFAULT 0.7")
        self._add_column_if_missing(conn, "relationship_history", "boundary_title_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "boundary_book_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "boundary_volume_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "session_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "source_session", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "inherited_confidence", "REAL DEFAULT 1.0")
        self._add_column_if_missing(conn, "relationship_history", "event_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_history", "consequence_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_edges", "edge_layer", "TEXT DEFAULT 'cooccurrence'")
        self._add_column_if_missing(conn, "relationship_social_edges", "edge_subtype", "TEXT DEFAULT 'general'")
        self._add_column_if_missing(conn, "relationship_social_edges", "directional", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_edges", "support_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_edges", "shared_scene_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_edges", "shared_event_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_edges", "chapter_overlap_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_edges", "dialogue_overlap_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_edges", "familiarity_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_edges", "trust_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_edges", "hostility_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_edges", "cooperation_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_edges", "confidence", "REAL DEFAULT 0.25")
        self._add_column_if_missing(conn, "relationship_social_edges", "promotion_state", "TEXT DEFAULT 'weak'")
        self._add_column_if_missing(conn, "relationship_social_edges", "evidence_summary", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "evidence_source_type", "TEXT DEFAULT 'observed_fact'")
        self._add_column_if_missing(conn, "relationship_social_edges", "actuality_status", "TEXT DEFAULT 'actual'")
        self._add_column_if_missing(conn, "relationship_social_edges", "source_pov_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_edges", "source_speaker_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_edges", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "first_seen_chapter", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_edges", "last_seen_chapter", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_edges", "last_event_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_edges", "boundary_title_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "boundary_book_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "boundary_volume_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "session_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "source_session", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_edges", "inherited_confidence", "REAL DEFAULT 1.0")
        self._add_column_if_missing(conn, "relationship_social_edges", "updated_at", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "evidence_key", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "edge_layer", "TEXT DEFAULT 'cooccurrence'")
        self._add_column_if_missing(conn, "relationship_social_evidence", "edge_subtype", "TEXT DEFAULT 'general'")
        self._add_column_if_missing(conn, "relationship_social_evidence", "directional", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "event_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_evidence", "evidence_scope", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "evidence_summary", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "shared_scene_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "shared_event_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "chapter_overlap_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "dialogue_overlap_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "familiarity_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "trust_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "hostility_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "cooperation_signal", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_social_evidence", "confidence", "REAL DEFAULT 0.25")
        self._add_column_if_missing(conn, "relationship_social_evidence", "evidence_source_type", "TEXT DEFAULT 'observed_fact'")
        self._add_column_if_missing(conn, "relationship_social_evidence", "actuality_status", "TEXT DEFAULT 'actual'")
        self._add_column_if_missing(conn, "relationship_social_evidence", "source_pov_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_evidence", "source_speaker_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_social_evidence", "scene_scope", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "boundary_title_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "boundary_book_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "boundary_volume_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "session_id", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "source_session", "TEXT")
        self._add_column_if_missing(conn, "relationship_social_evidence", "inherited_confidence", "REAL DEFAULT 1.0")
        self._add_column_if_missing(conn, "relationship_communities", "source_session", "TEXT")
        self._add_column_if_missing(conn, "relationship_communities", "inherited_confidence", "REAL DEFAULT 1.0")
        self._add_column_if_missing(conn, "relationship_community_members", "bridge_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "relationship_community_members", "cluster_strength", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entity_social_metrics", "bridge_score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "entity_social_metrics", "cluster_strength", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "chapter_boundaries", "book_id", "TEXT")
        self._add_column_if_missing(conn, "merge_candidates", "score", "REAL DEFAULT 0.0")
        self._add_column_if_missing(conn, "merge_candidates", "state", "TEXT DEFAULT 'candidate'")
        self._add_column_if_missing(conn, "merge_candidates", "evidence", "TEXT")
        self._add_column_if_missing(conn, "merge_candidates", "last_seen_chapter", "INTEGER")
        self._add_column_if_missing(conn, "merge_candidates", "resolver_version", "TEXT DEFAULT 'resolver_v1'")
        self._add_column_if_missing(conn, "conflict_records", "severity", "INTEGER DEFAULT 6")
        self._add_column_if_missing(conn, "conflict_records", "resolver_key", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "subject_type", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "subject_key", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "evidence_refs_json", "TEXT NOT NULL DEFAULT '[]'")
        self._add_column_if_missing(conn, "conflict_records", "alternatives_json", "TEXT NOT NULL DEFAULT '[]'")
        self._add_column_if_missing(conn, "conflict_records", "reviewed_at", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "resolution", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "resolved_at", "TEXT")
        conn.execute("UPDATE identity_resolution_evidence SET candidate_count = COALESCE(candidate_count, 0)")
        conn.execute("UPDATE chapter_pov SET narrator_type = COALESCE(narrator_type, 'unknown')")
        conn.execute("UPDATE chapter_pov SET narrator_confidence = COALESCE(narrator_confidence, 0.0)")
        conn.execute("UPDATE events SET event_identity_key = COALESCE(event_identity_key, normalized_summary)")
        conn.execute("UPDATE events SET narrator_entity_id = COALESCE(narrator_entity_id, observed_by_entity_id)")
        conn.execute("UPDATE events SET narrator_scope = COALESCE(narrator_scope, 'unknown')")
        conn.execute("UPDATE events SET scene_scope = COALESCE(scene_scope, 'chapter:' || chapter)")
        conn.execute("UPDATE events SET evidence_source_type = COALESCE(evidence_source_type, 'observed_fact')")
        conn.execute("UPDATE events SET actuality_status = COALESCE(actuality_status, 'actual')")
        conn.execute("UPDATE events SET narrative_order = COALESCE(narrative_order, event_order)")
        conn.execute("UPDATE events SET story_time_confidence = COALESCE(story_time_confidence, 0.0)")
        conn.execute("UPDATE events SET source_section_type = COALESCE(source_section_type, 'CHAPTER')")
        conn.execute("UPDATE events SET occurrence_role = COALESCE(occurrence_role, 'occurrence')")
        conn.execute("UPDATE events SET reader_known_since_chapter = COALESCE(reader_known_since_chapter, chapter)")
        conn.execute("UPDATE mention_occurrences SET mention_source_type = COALESCE(mention_source_type, 'narration')")
        conn.execute("UPDATE mention_occurrences SET source_section_type = COALESCE(source_section_type, 'CHAPTER')")
        conn.execute("UPDATE unresolved_mentions SET mention_source_type = COALESCE(mention_source_type, 'narration')")
        conn.execute("UPDATE unresolved_mentions SET source_section_type = COALESCE(source_section_type, 'CHAPTER')")
        conn.execute("UPDATE reference_mentions SET reference_subtype = COALESCE(reference_subtype, 'reference')")
        conn.execute("UPDATE reference_mentions SET participation_score = COALESCE(participation_score, 0.0)")
        conn.execute("UPDATE reference_mentions SET reference_score = COALESCE(reference_score, 0.0)")
        conn.execute("UPDATE reference_mentions SET promotion_state = COALESCE(promotion_state, 'reference')")
        conn.execute("UPDATE reference_mentions SET source_section_type = COALESCE(source_section_type, 'CHAPTER')")
        conn.execute("UPDATE entities SET boundary_book_id = COALESCE(boundary_book_id, boundary_title_id)")
        conn.execute("UPDATE entities SET inherited_confidence = COALESCE(inherited_confidence, 1.0)")
        conn.execute("""
            UPDATE entities
            SET entity_category = COALESCE(NULLIF(entity_category, ''), CASE
                    WHEN entity_type = 'INDIVIDUAL' THEN 'CHARACTER'
                    WHEN entity_type = 'GROUP' THEN 'GROUP'
                    WHEN entity_type = 'LOCATION' THEN 'LOCATION'
                    WHEN entity_type IN ('CONCEPT_OR_LORE', 'REFERENCE', 'WORK_OF_ART') THEN 'REFERENCE'
                    ELSE 'UNKNOWN'
                END),
                species_or_kind = COALESCE(NULLIF(species_or_kind, ''), 'unknown'),
                sentience = COALESCE(NULLIF(sentience, ''), 'unknown'),
                narrative_role = COALESCE(NULLIF(narrative_role, ''), 'unknown'),
                story_role = COALESCE(NULLIF(story_role, ''), COALESCE(NULLIF(narrative_role, ''), 'unknown')),
                active_status = COALESCE(NULLIF(active_status, ''), CASE
                    WHEN entity_type IN ('INDIVIDUAL', 'GROUP', 'LOCATION') THEN 'active_participant'
                    ELSE 'referenced_only'
                END),
                identity_status = COALESCE(NULLIF(identity_status, ''), 'unknown'),
                entity_persistence = COALESCE(NULLIF(entity_persistence, ''), 'persistent'),
                embodiment = COALESCE(NULLIF(embodiment, ''), 'unknown'),
                can_speak = COALESCE(NULLIF(can_speak, ''), 'unknown'),
                can_move = COALESCE(NULLIF(can_move, ''), 'unknown'),
                can_think = COALESCE(NULLIF(can_think, ''), 'unknown'),
                can_remember = COALESCE(NULLIF(can_remember, ''), 'unknown'),
                can_make_decisions = COALESCE(NULLIF(can_make_decisions, ''), 'unknown'),
                can_form_relationships = COALESCE(NULLIF(can_form_relationships, ''), 'unknown'),
                ontology_confidence = COALESCE(ontology_confidence, 0.5),
                literal_status = COALESCE(NULLIF(literal_status, ''), 'literal'),
                interpretation_status = COALESCE(NULLIF(interpretation_status, ''), 'actual'),
                language_status = COALESCE(NULLIF(language_status, ''), 'natural_language'),
                translation_status = COALESCE(NULLIF(translation_status, ''), 'not_applicable')
        """)
        conn.execute("UPDATE relationship_history SET boundary_book_id = COALESCE(boundary_book_id, boundary_title_id)")
        conn.execute("UPDATE relationship_social_edges SET boundary_book_id = COALESCE(boundary_book_id, boundary_title_id)")
        conn.execute("UPDATE relationship_social_edges SET evidence_source_type = COALESCE(evidence_source_type, 'observed_fact')")
        conn.execute("UPDATE relationship_social_edges SET actuality_status = COALESCE(actuality_status, 'actual')")
        conn.execute("UPDATE relationship_social_edges SET promotion_state = COALESCE(promotion_state, 'weak')")
        conn.execute("UPDATE relationship_social_edges SET inherited_confidence = COALESCE(inherited_confidence, 1.0)")
        conn.execute("UPDATE relationship_social_evidence SET boundary_book_id = COALESCE(boundary_book_id, boundary_title_id)")
        conn.execute("UPDATE relationship_social_evidence SET evidence_source_type = COALESCE(evidence_source_type, 'observed_fact')")
        conn.execute("UPDATE relationship_social_evidence SET actuality_status = COALESCE(actuality_status, 'actual')")
        conn.execute("UPDATE relationship_social_evidence SET inherited_confidence = COALESCE(inherited_confidence, 1.0)")
        conn.execute("UPDATE relationship_communities SET inherited_confidence = COALESCE(inherited_confidence, 1.0)")
        conn.execute("UPDATE chapter_boundaries SET book_id = COALESCE(book_id, title_id)")
        conn.execute("UPDATE conflict_records SET severity = COALESCE(severity, 6)")
        conn.execute("UPDATE entities SET display_name = COALESCE(display_name, canonical_name)")
        conn.execute("UPDATE aliases SET first_seen = COALESCE(first_seen, chapter_found)")
        conn.execute("UPDATE aliases SET last_seen = COALESCE(last_seen, chapter_found)")
        conn.execute("UPDATE aliases SET status = COALESCE(status, 'accepted')")
        conn.execute("UPDATE aliases SET confidence = COALESCE(confidence, 0.85)")
        conn.execute("UPDATE aliases SET support_count = COALESCE(support_count, 4)")
        conn.execute("UPDATE relationship_history SET evidence = COALESCE(evidence, reason)")

        cursor = conn.cursor()
        cursor.execute("SELECT id, alias_name FROM aliases WHERE alias_key IS NULL OR alias_key = ''")
        for alias_id, alias_name in cursor.fetchall():
            conn.execute(
                "UPDATE aliases SET alias_key = ? WHERE id = ?",
                (self.normalize_alias_key(alias_name) or f"__alias_{alias_id}", alias_id),
            )
        conn.execute("""
            UPDATE aliases
            SET alias_key = '__alias_' || id
            WHERE alias_key IS NULL OR alias_key = ''
        """)

        cursor.execute("""
            SELECT entity_id, alias_key, MIN(id), SUM(support_count), MAX(confidence),
                   MAX(last_seen), GROUP_CONCAT(evidence, '\n')
            FROM aliases
            WHERE alias_key IS NOT NULL AND alias_key != ''
            GROUP BY entity_id, alias_key
            HAVING COUNT(*) > 1
        """)
        for entity_id, alias_key, keep_id, support_count, confidence, last_seen, evidence in cursor.fetchall():
            conn.execute("""
                UPDATE aliases
                SET support_count = ?, confidence = ?, last_seen = ?, evidence = ?
                WHERE id = ?
            """, (support_count, confidence, last_seen, evidence, keep_id))
            conn.execute("""
                DELETE FROM aliases
                WHERE entity_id = ? AND alias_key = ? AND id != ?
            """, (entity_id, alias_key, keep_id))

        cursor.execute("""
            SELECT id, canonical_name, entity_type
            FROM entities
            WHERE importance_score IS NULL
               OR visibility_score IS NULL
               OR surface_form_class IS NULL
               OR (entity_type = 'LOCATION' AND location_subtype IS NULL)
        """)
        for entity_id, canonical_name, entity_type in cursor.fetchall():
            importance, visibility, surface_class, location_subtype = self._initial_importance(canonical_name, entity_type)
            conn.execute("""
                UPDATE entities
                SET importance_score = COALESCE(importance_score, ?),
                    visibility_score = COALESCE(visibility_score, ?),
                    surface_form_class = COALESCE(surface_form_class, ?),
                    location_subtype = COALESCE(location_subtype, ?)
                WHERE id = ?
            """, (importance, visibility, surface_class, location_subtype, entity_id))

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_aliases_entity_alias_key
            ON aliases(entity_id, alias_key)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_chapter ON events(chapter, event_order)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_boundary ON events(session_id, boundary_title_id, boundary_volume_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_identity ON events(event_identity_key, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_scope ON events(observed_by_entity_id, narrator_entity_id, scene_scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_landmark ON events(landmark_id, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_recurrence ON events(recurring_template_id, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_identity ON event_landmarks(identity_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_timeline ON event_landmarks(historical_start_sort, narrative_first_chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmark_names_lookup ON landmark_names(name_key, status, first_known_chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmark_links_event ON landmark_event_links(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmark_hierarchy_child ON landmark_hierarchy(child_landmark_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmark_assertions_lookup ON landmark_assertions(landmark_id, assertion_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_landmark_resolution_event ON landmark_resolution_evidence(event_id, decision)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_participants_entity ON event_participants(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_participants_entity_event ON event_participants(entity_id, event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_participants_scope ON event_participants(observed_by_entity_id, scene_scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationship_history_event ON relationship_history(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationship_history_lookup ON relationship_history(rel_key, chapter, interaction_order)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationship_history_boundary ON relationship_history(session_id, source_session, inherited_confidence)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_edges_source ON relationship_social_edges(source_id, target_id, edge_layer)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_edges_target ON relationship_social_edges(target_id, source_id, edge_layer)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_edges_chapter ON relationship_social_edges(last_seen_chapter, promotion_state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_edges_boundary ON relationship_social_edges(session_id, source_session, inherited_confidence)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_social_evidence_key ON relationship_social_evidence(evidence_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_evidence_edge ON relationship_social_evidence(edge_key, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_evidence_event ON relationship_social_evidence(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_evidence_boundary ON relationship_social_evidence(session_id, source_session, inherited_confidence)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_community_members_entity ON relationship_community_members(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_metrics_bridge ON entity_social_metrics(bridge_score, social_degree)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_normalized ON mention_occurrences(normalized_form, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_class ON mention_occurrences(mention_class, title_category, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reference_mentions_lookup ON reference_mentions(normalized_form, promotion_state, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reference_mentions_subtype ON reference_mentions(reference_subtype, promotion_state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name_semantic_relation_source ON name_semantic_relations(source_normalized, relation_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name_semantic_relation_target ON name_semantic_relations(target_normalized, relation_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name_semantic_relation_entities ON name_semantic_relations(source_entity_id, target_entity_id, relation_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_ontology_evidence_entity ON entity_ontology_evidence(entity_id, ontology_field, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_state_history_entity ON entity_state_history(entity_id, state_field, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_life_status_evidence_entity ON life_status_evidence(entity_id, chapter, narrative_order)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_life_status_evidence_scope ON life_status_evidence(entity_id, belief_owner_type, belief_owner_entity_id, reader_visible)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_life_status_evidence_event ON life_status_evidence(linked_event_id, supersedes_evidence_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_life_status_evidence_boundary ON life_status_evidence(session_id, source_session, inherited_confidence)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_life_status_snapshots_entity ON life_status_snapshots(entity_id, scope_type, scope_owner_entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_life_status_timeline_entity ON life_status_timeline_segments(entity_id, start_chapter, end_chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_legacy_signals_entity ON entity_legacy_signals(entity_id, signal_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_legacy_signals_boundary ON entity_legacy_signals(session_id, source_session, inherited_confidence)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_semantic_relations_source ON entity_semantic_relations(source_entity_id, relation_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_semantic_relations_target ON entity_semantic_relations(target_entity_id, relation_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_language_observations_lookup ON language_observations(normalized_text, translation_status, first_seen)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_title_links_key ON title_links(title_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_title_links_entity_status_key ON title_links(entity_id, status, title_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_identity_promotions_resolved ON identity_promotions(resolved_entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_cluster_members_event ON event_cluster_members(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_search_terms_term ON entity_search_terms(term, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_search_terms_status_term_entity ON entity_search_terms(status, term, entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_search_terms_term ON event_search_terms(term)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_search_terms_term_event ON event_search_terms(term, event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_aliases_entity_status_key ON aliases(entity_id, status, alias_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_identity_resolution_mention ON identity_resolution_evidence(mention_key, entity_type, state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_identity_resolution_target ON identity_resolution_evidence(target_entity_id, state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_mentions_lookup ON unresolved_mentions(mention_key, entity_type, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kinship_mentions_lookup ON kinship_mentions(mention_key, chapter, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chapter_boundaries_title ON chapter_boundaries(title_id, volume_id, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chapter_boundaries_book ON chapter_boundaries(book_id, volume_id, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chapter_visibility_scope ON chapter_visibility_scopes(narrator_entity_id, observed_by_entity_id, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_performance_metrics_chapter ON performance_metrics(chapter, metric_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_merge_candidates_state_score ON merge_candidates(state, score)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conflict_records_priority ON conflict_records(status, severity, chapter)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_active_evidence_revision ON chapter_evidence_revisions(chapter) WHERE is_active = 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_revision_lookup ON chapter_evidence_revisions(chapter, revision DESC)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_active_image_evidence_occurrence ON image_evidence_revisions(chapter, occurrence_order) WHERE is_active = 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_evidence_chapter_revision ON image_evidence_revisions(chapter, revision DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_evidence_exact_hash ON image_evidence_revisions(image_hash, parser_fingerprint)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_occurrence_lookup ON image_occurrence_provenance(chapter, occurrence_order)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_revision_lookup ON reader_snapshot_revisions(chapter, revision DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_checkpoint_state ON chapter_processing_checkpoints(state, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invalidation_status ON chapter_invalidations(status, from_chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_resolver_decisions_subject ON resolver_decisions(resolver_key, subject_type, subject_key, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conflict_records_subject ON conflict_records(resolver_key, subject_type, subject_key, status)")

        cursor.execute("SELECT id FROM entities")
        for (entity_id,) in cursor.fetchall():
            self._sync_entity_search_terms(conn, entity_id)
        cursor.execute("SELECT id FROM events")
        for (event_id,) in cursor.fetchall():
            self._sync_event_search_terms(conn, event_id)
        self._backfill_social_edges_from_existing_events(conn)

    def _migrate_entities_schema(self, conn):
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'entities'")
        table_sql = (cursor.fetchone() or [""])[0] or ""
        if "canonical_name TEXT UNIQUE" in table_sql:
            cursor.execute("""
                CREATE TABLE entities_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT,
                    display_name TEXT,
                    entity_type TEXT,
                    first_seen_chapter INTEGER,
                    last_verified_chapter INTEGER,
                    mention_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.55,
                    type_support_count INTEGER DEFAULT 1,
                    importance_score REAL DEFAULT 0.45,
                    visibility_score REAL DEFAULT 0.45,
                    surface_form_class TEXT DEFAULT 'proper_name',
                    location_subtype TEXT,
                    boundary_title_id TEXT,
                    boundary_book_id TEXT,
                    boundary_volume_id TEXT,
                    session_id TEXT,
                    source_session TEXT,
                    inherited_confidence REAL DEFAULT 1.0
                )
            """)
            cursor.execute("""
                INSERT INTO entities_new (
                    id, canonical_name, display_name, entity_type,
                    first_seen_chapter, last_verified_chapter, mention_count,
                    confidence, type_support_count, importance_score,
                    visibility_score, surface_form_class, location_subtype,
                    boundary_title_id, boundary_book_id, boundary_volume_id,
                    session_id, source_session, inherited_confidence
                )
                SELECT id, canonical_name, display_name, entity_type,
                       first_seen_chapter, last_verified_chapter, mention_count,
                       confidence, type_support_count, importance_score,
                       visibility_score, surface_form_class, location_subtype,
                       boundary_title_id, boundary_book_id, boundary_volume_id,
                       session_id, source_session, inherited_confidence
                FROM entities
            """)
            cursor.execute("DROP TABLE entities")
            cursor.execute("ALTER TABLE entities_new RENAME TO entities")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name_type ON entities(lower(canonical_name), entity_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_boundary ON entities(entity_type, boundary_book_id, boundary_volume_id, session_id)")

    def _migrate_relationship_history_schema(self, conn):
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(relationship_history)")
        columns = {row[1] for row in cursor.fetchall()}

        needs_migration = (
            "interaction_order" not in columns
            or "interaction_type" not in columns
            or "hostility_score" not in columns
            or "evidence_source_type" not in columns
            or "event_id" not in columns
            or "consequence_id" not in columns
            or "boundary_book_id" not in columns
        )
        cursor.execute("PRAGMA index_list(relationship_history)")
        for _, index_name, is_unique, *_ in cursor.fetchall():
            if not is_unique:
                continue
            cursor.execute(f"PRAGMA index_info('{index_name}')")
            indexed_columns = {row[2] for row in cursor.fetchall()}
            if {"rel_key", "chapter"}.issubset(indexed_columns):
                needs_migration = True
                break

        if not needs_migration:
            return

        cursor.execute("""
            CREATE TABLE relationship_history_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rel_key TEXT,
                chapter INTEGER,
                interaction_order INTEGER,
                interaction_type TEXT DEFAULT 'interaction',
                trust_score INTEGER,
                hostility_score REAL DEFAULT 0.0,
                respect_score REAL DEFAULT 0.0,
                fear_score REAL DEFAULT 0.0,
                reason TEXT,
                evidence TEXT,
                evidence_source_type TEXT DEFAULT 'observed_fact',
                source_pov_id INTEGER,
                source_speaker_id INTEGER,
                scene_scope TEXT,
                confidence REAL DEFAULT 0.7,
                boundary_title_id TEXT,
                boundary_book_id TEXT,
                boundary_volume_id TEXT,
                session_id TEXT,
                source_session TEXT,
                inherited_confidence REAL DEFAULT 1.0,
                event_id INTEGER,
                consequence_id INTEGER,
                FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE,
                FOREIGN KEY(source_pov_id) REFERENCES entities(id) ON DELETE SET NULL,
                FOREIGN KEY(source_speaker_id) REFERENCES entities(id) ON DELETE SET NULL,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL,
                FOREIGN KEY(consequence_id) REFERENCES event_consequences(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            SELECT rel_key, chapter, trust_score, reason, evidence, confidence, event_id, consequence_id,
                   boundary_title_id, boundary_book_id, boundary_volume_id, session_id, source_session,
                   inherited_confidence
            FROM relationship_history
            ORDER BY id
        """)
        interaction_counts = {}
        for (
            rel_key, chapter, trust_score, reason, evidence, confidence, event_id, consequence_id,
            boundary_title_id, boundary_book_id, boundary_volume_id, session_id, source_session,
            inherited_confidence,
        ) in cursor.fetchall():
            count_key = (rel_key, chapter)
            interaction_counts[count_key] = interaction_counts.get(count_key, 0) + 1
            cursor.execute("""
                INSERT INTO relationship_history_new (
                    rel_key, chapter, interaction_order, interaction_type,
                    trust_score, hostility_score, respect_score, fear_score,
                    reason, evidence, evidence_source_type, confidence,
                    boundary_title_id, boundary_book_id, boundary_volume_id,
                    session_id, source_session, inherited_confidence,
                    event_id, consequence_id
                )
                VALUES (?, ?, ?, 'interaction', ?, 0.0, 0.0, 0.0, ?, ?, 'observed_fact', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rel_key,
                chapter,
                interaction_counts[count_key],
                trust_score,
                reason,
                evidence or reason,
                confidence if confidence is not None else 0.7,
                boundary_title_id,
                boundary_book_id or boundary_title_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE,
                event_id,
                consequence_id,
            ))

        cursor.execute("DROP TABLE relationship_history")
        cursor.execute("ALTER TABLE relationship_history_new RENAME TO relationship_history")

    def get_pov_for_chapter(self, chapter: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entity_id FROM chapter_pov WHERE chapter <= ? ORDER BY chapter DESC LIMIT 1", (chapter,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_pov_for_chapter(
        self,
        chapter: int,
        entity_id: int,
        narrator_type: str = "unknown",
        narrator_confidence: float = 0.0,
        source_evidence: str = "",
        scene_scope: str | None = None,
    ):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO chapter_pov (
                    chapter, entity_id, narrator_type, narrator_confidence,
                    source_evidence, scene_scope
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter) DO UPDATE SET
                    entity_id = excluded.entity_id,
                    narrator_type = excluded.narrator_type,
                    narrator_confidence = excluded.narrator_confidence,
                    source_evidence = excluded.source_evidence,
                    scene_scope = excluded.scene_scope
            """, (
                chapter,
                entity_id,
                narrator_type or "unknown",
                float(narrator_confidence or 0.0),
                source_evidence or "",
                scene_scope,
            ))

    def set_chapter_visibility_scope(
        self,
        chapter: int,
        observed_by_entity_id: int | None = None,
        narrator_entity_id: int | None = None,
        narrator_scope: str = "unknown",
        scene_scope: str | None = None,
        confidence: float = 0.0,
        source_evidence: str = "",
    ):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO chapter_visibility_scopes (
                    chapter, observed_by_entity_id, narrator_entity_id,
                    narrator_scope, scene_scope, confidence, source_evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter) DO UPDATE SET
                    observed_by_entity_id = excluded.observed_by_entity_id,
                    narrator_entity_id = excluded.narrator_entity_id,
                    narrator_scope = excluded.narrator_scope,
                    scene_scope = excluded.scene_scope,
                    confidence = excluded.confidence,
                    source_evidence = excluded.source_evidence
            """, (
                chapter,
                observed_by_entity_id,
                narrator_entity_id,
                narrator_scope or "unknown",
                scene_scope,
                float(confidence or 0.0),
                source_evidence or "",
            ))

    def set_chapter_boundary(
        self,
        chapter: int,
        library_id: str | None = None,
        title_id: str | None = None,
        book_id: str | None = None,
        volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = 1.0,
    ):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO chapter_boundaries (
                    chapter, library_id, title_id, book_id, volume_id, session_id,
                    source_session, inherited_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter) DO UPDATE SET
                    library_id = COALESCE(excluded.library_id, chapter_boundaries.library_id),
                    title_id = COALESCE(excluded.title_id, chapter_boundaries.title_id),
                    book_id = COALESCE(excluded.book_id, chapter_boundaries.book_id),
                    volume_id = COALESCE(excluded.volume_id, chapter_boundaries.volume_id),
                    session_id = COALESCE(excluded.session_id, chapter_boundaries.session_id),
                    source_session = COALESCE(excluded.source_session, chapter_boundaries.source_session),
                    inherited_confidence = excluded.inherited_confidence
            """, (
                chapter,
                library_id,
                title_id,
                book_id or title_id,
                volume_id,
                session_id,
                source_session,
                inherited_confidence,
            ))

    def record_performance_metric(
        self,
        chapter: int,
        metric_name: str,
        metric_value: float,
        metric_unit: str = "count",
    ):
        if metric_name is None:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO performance_metrics (chapter, metric_name, metric_value, metric_unit)
                VALUES (?, ?, ?, ?)
            """, (chapter, str(metric_name), float(metric_value), metric_unit))

    def get_chapter_boundary(self, chapter: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT library_id, title_id, book_id, volume_id, session_id,
                       source_session, COALESCE(inherited_confidence, 1.0)
                FROM chapter_boundaries
                WHERE chapter = ?
            """, (chapter,))
            row = cursor.fetchone()
        if not row:
            return {
                "library_id": None,
                "title_id": None,
                "book_id": None,
                "volume_id": None,
                "session_id": None,
                "source_session": None,
                "inherited_confidence": LOCAL_GRAPH_CONFIDENCE,
            }
        library_id, title_id, book_id, volume_id, session_id, source_session, inherited_confidence = row
        return {
            "library_id": library_id,
            "title_id": title_id,
            "book_id": book_id,
            "volume_id": volume_id,
            "session_id": session_id,
            "source_session": source_session,
            "inherited_confidence": inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE,
        }

    def stamp_local_chapter_boundary(
        self,
        chapter: int,
        title_id: str | None = None,
        book_id: str | None = None,
        volume_id: str | None = None,
        session_id: str | None = None,
        library_id: str | None = None,
    ):
        # Synthetic payloads and old caches may not carry title metadata. Keep
        # their chapter boundary valid without inventing a title-specific rule.
        fallback_book_id = book_id or title_id or session_id or "local_session"
        self.set_chapter_boundary(
            chapter,
            library_id=library_id,
            title_id=title_id,
            book_id=fallback_book_id,
            volume_id=volume_id,
            session_id=session_id,
            source_session=session_id,
            inherited_confidence=LOCAL_GRAPH_CONFIDENCE,
        )

    def mark_graph_as_inherited(
        self,
        parent_book: str,
        parent_session: str,
        target_book: str | None = None,
        target_session: str | None = None,
        inherited_confidence: float = INHERITED_GRAPH_CONFIDENCE,
    ):
        inherited_confidence = max(0.05, min(1.0, float(inherited_confidence)))
        source_session = "::".join(part for part in (parent_book, parent_session) if part)
        target_session_id = "::".join(part for part in (target_book, target_session) if part) or None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT chapter FROM events")
            event_chapters = {chapter for (chapter,) in cursor.fetchall()}
            cursor.execute("SELECT DISTINCT chapter FROM relationship_history WHERE chapter IS NOT NULL")
            relationship_chapters = {chapter for (chapter,) in cursor.fetchall()}
            for chapter in sorted(event_chapters | relationship_chapters):
                conn.execute("""
                    INSERT INTO chapter_boundaries (
                        chapter, library_id, title_id, book_id, volume_id, session_id,
                        source_session, inherited_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chapter) DO UPDATE SET
                        library_id = COALESCE(chapter_boundaries.library_id, excluded.library_id),
                        title_id = COALESCE(chapter_boundaries.title_id, excluded.title_id),
                        book_id = COALESCE(chapter_boundaries.book_id, excluded.book_id),
                        volume_id = COALESCE(chapter_boundaries.volume_id, excluded.volume_id),
                        session_id = COALESCE(chapter_boundaries.session_id, excluded.session_id),
                        source_session = COALESCE(chapter_boundaries.source_session, excluded.source_session),
                        inherited_confidence = MIN(
                            COALESCE(chapter_boundaries.inherited_confidence, 1.0),
                            excluded.inherited_confidence
                        )
                """, (
                    chapter,
                    parent_book,
                    parent_book,
                    parent_book,
                    parent_book,
                    target_session_id,
                    source_session,
                    inherited_confidence,
                ))
            conn.execute("""
                UPDATE events
                SET boundary_title_id = COALESCE(boundary_title_id, ?),
                    boundary_book_id = COALESCE(boundary_book_id, ?),
                    boundary_volume_id = COALESCE(boundary_volume_id, ?),
                    session_id = COALESCE(session_id, ?),
                    source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                    confidence = MIN(COALESCE(confidence, 1.0), ?)
            """, (
                parent_book,
                parent_book,
                parent_book,
                target_session_id,
                source_session,
                inherited_confidence,
                inherited_confidence,
            ))
            conn.execute("""
                UPDATE event_landmarks
                SET source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?)
            """, (source_session, inherited_confidence))
            conn.execute("""
                UPDATE relationship_history
                SET boundary_title_id = COALESCE(boundary_title_id, ?),
                    boundary_book_id = COALESCE(boundary_book_id, ?),
                    boundary_volume_id = COALESCE(boundary_volume_id, ?),
                    session_id = COALESCE(session_id, ?),
                    source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                    confidence = MIN(COALESCE(confidence, 1.0), ?)
            """, (
                parent_book,
                parent_book,
                parent_book,
                target_session_id,
                source_session,
                inherited_confidence,
                inherited_confidence,
            ))
            conn.execute("""
                UPDATE entities
                SET boundary_title_id = COALESCE(boundary_title_id, ?),
                    boundary_book_id = COALESCE(boundary_book_id, ?),
                    boundary_volume_id = COALESCE(boundary_volume_id, ?),
                    session_id = COALESCE(session_id, ?),
                    source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                    confidence = MIN(COALESCE(confidence, 1.0), ?)
            """, (
                parent_book,
                parent_book,
                parent_book,
                target_session_id,
                source_session,
                inherited_confidence,
                inherited_confidence,
            ))
            for table_name in ("life_status_evidence", "entity_legacy_signals"):
                conn.execute(f"""
                    UPDATE {table_name}
                    SET boundary_title_id = COALESCE(boundary_title_id, ?),
                        boundary_book_id = COALESCE(boundary_book_id, ?),
                        boundary_volume_id = COALESCE(boundary_volume_id, ?),
                        session_id = COALESCE(session_id, ?),
                        source_session = COALESCE(source_session, ?),
                        inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                        confidence = MIN(COALESCE(confidence, 1.0), ?)
                """, (
                    parent_book,
                    parent_book,
                    parent_book,
                    target_session_id,
                    source_session,
                    inherited_confidence,
                    inherited_confidence,
                ))
            conn.execute("""
                UPDATE entity_state_history
                SET boundary_title_id = COALESCE(boundary_title_id, ?),
                    boundary_book_id = COALESCE(boundary_book_id, ?),
                    boundary_volume_id = COALESCE(boundary_volume_id, ?),
                    session_id = COALESCE(session_id, ?),
                    source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                    confidence = MIN(COALESCE(confidence, 1.0), ?)
                WHERE state_field = 'life_status'
            """, (
                parent_book,
                parent_book,
                parent_book,
                target_session_id,
                source_session,
                inherited_confidence,
                inherited_confidence,
            ))
            conn.execute("""
                UPDATE relationship_social_edges
                SET boundary_title_id = COALESCE(boundary_title_id, ?),
                    boundary_book_id = COALESCE(boundary_book_id, ?),
                    boundary_volume_id = COALESCE(boundary_volume_id, ?),
                    session_id = COALESCE(session_id, ?),
                    source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                    confidence = MIN(COALESCE(confidence, 1.0), ?)
            """, (
                parent_book,
                parent_book,
                parent_book,
                target_session_id,
                source_session,
                inherited_confidence,
                inherited_confidence,
            ))
            conn.execute("""
                UPDATE relationship_social_evidence
                SET boundary_title_id = COALESCE(boundary_title_id, ?),
                    boundary_book_id = COALESCE(boundary_book_id, ?),
                    boundary_volume_id = COALESCE(boundary_volume_id, ?),
                    session_id = COALESCE(session_id, ?),
                    source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?),
                    confidence = MIN(COALESCE(confidence, 1.0), ?)
            """, (
                parent_book,
                parent_book,
                parent_book,
                target_session_id,
                source_session,
                inherited_confidence,
                inherited_confidence,
            ))
            conn.execute("""
                UPDATE relationship_communities
                SET source_session = COALESCE(source_session, ?),
                    inherited_confidence = MIN(COALESCE(inherited_confidence, 1.0), ?)
            """, (source_session, inherited_confidence))
            cursor.execute("SELECT DISTINCT rel_key FROM relationship_history")
            for (rel_key,) in cursor.fetchall():
                self._recalculate_relationship_snapshot(conn, rel_key)
            try:
                from life_status_resolver import LifeStatusResolver
                LifeStatusResolver(self).resolve_all()
            except Exception:
                pass
            self.refresh_social_graph_metrics()

    def record_resolver_decision(
        self,
        resolver_key: str,
        subject_type: str,
        subject_key: str | int,
        chapter: int | None,
        decision: str,
        *,
        confidence: float = 0.0,
        supporting_evidence: list | dict | str | None = None,
        contradicting_evidence: list | dict | str | None = None,
        rejected_alternatives: list | dict | str | None = None,
        visibility: str = "engine",
        resolver_version: str | None = None,
        metadata: dict | None = None,
        conn=None,
    ) -> int | None:
        """Persist an idempotent, append-only resolver decision explanation."""
        resolver_key = str(resolver_key or "").strip()
        subject_type = str(subject_type or "").strip()
        subject_key = str(subject_key or "").strip()
        decision = str(decision or "").strip()
        if not resolver_key or not subject_type or not subject_key or not decision:
            return None
        visibility = visibility if visibility in {"reader", "engine", "hidden"} else "engine"

        def _as_list(value):
            if value in (None, "", [], {}):
                return []
            return value if isinstance(value, list) else [value]

        supporting = _as_list(supporting_evidence)
        contradicting = _as_list(contradicting_evidence)
        alternatives = _as_list(rejected_alternatives)
        version = str(resolver_version or RESOLVER_VERSIONS.get(resolver_key, "resolver_v1"))
        key_payload = {
            "resolver": resolver_key,
            "version": version,
            "subject_type": subject_type,
            "subject_key": subject_key,
            "chapter": chapter,
            "decision": decision,
            "confidence": round(max(0.0, min(1.0, float(confidence or 0.0))), 6),
            "visibility": visibility,
            "supporting": supporting,
            "contradicting": contradicting,
            "alternatives": alternatives,
            "metadata": metadata or {},
        }
        decision_key = hashlib.sha256(
            json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        owns_connection = conn is None
        conn = conn or self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO resolver_decisions (
                decision_key, resolver_key, resolver_version, subject_type, subject_key,
                chapter, decision, confidence, visibility, supporting_evidence_json,
                contradicting_evidence_json, rejected_alternatives_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_key,
                resolver_key,
                version,
                subject_type,
                subject_key,
                chapter,
                decision,
                key_payload["confidence"],
                visibility,
                json.dumps(supporting, ensure_ascii=False, sort_keys=True),
                json.dumps(contradicting, ensure_ascii=False, sort_keys=True),
                json.dumps(alternatives, ensure_ascii=False, sort_keys=True),
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        cursor.execute("SELECT id FROM resolver_decisions WHERE decision_key = ?", (decision_key,))
        row = cursor.fetchone()
        if owns_connection:
            conn.commit()
        return int(row[0]) if row else None

    def get_resolver_decisions(
        self,
        *,
        resolver_key: str | None = None,
        subject_type: str | None = None,
        subject_key: str | int | None = None,
        chapter: int | None = None,
    ) -> list[dict]:
        clauses, parameters = [], []
        for column, value in (
            ("resolver_key", resolver_key),
            ("subject_type", subject_type),
            ("subject_key", None if subject_key is None else str(subject_key)),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if chapter is not None:
            clauses.append("COALESCE(chapter, -1) <= ?")
            parameters.append(int(chapter))
        statement = """
            SELECT id, resolver_key, resolver_version, subject_type, subject_key, chapter,
                   decision, confidence, visibility, supporting_evidence_json,
                   contradicting_evidence_json, rejected_alternatives_json, metadata_json, created_at
            FROM resolver_decisions
        """
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        statement += " ORDER BY COALESCE(chapter, -1), id"
        with self._get_connection() as conn:
            rows = conn.execute(statement, tuple(parameters)).fetchall()
        return [
            {
                "id": row[0],
                "resolver": row[1],
                "resolver_version": row[2],
                "subject": {"type": row[3], "key": row[4]},
                "chapter": row[5],
                "decision": row[6],
                "confidence": row[7],
                "visibility": row[8],
                "supporting_evidence": json.loads(row[9] or "[]"),
                "contradicting_evidence": json.loads(row[10] or "[]"),
                "rejected_alternatives": json.loads(row[11] or "[]"),
                "metadata": json.loads(row[12] or "{}"),
                "created_at": row[13],
            }
            for row in rows
        ]

    @staticmethod
    def _conflict_resolver_key(conflict_type: str) -> str:
        conflict_type = str(conflict_type or "")
        if "landmark" in conflict_type:
            return "landmarks"
        if "relationship" in conflict_type:
            return "relationships"
        if any(token in conflict_type for token in ("life", "dead", "death")):
            return "life_status"
        if any(token in conflict_type for token in ("ontology", "entity_type")):
            return "ontology"
        return "identity"

    def record_conflict(
        self,
        conflict_type: str,
        chapter: int,
        payload: dict,
        entity_a_id: int | None = None,
        entity_b_id: int | None = None,
        severity: int | None = None,
        *,
        resolver_key: str | None = None,
        subject_type: str | None = None,
        subject_key: str | int | None = None,
        evidence_refs: list | dict | str | None = None,
        alternatives: list | dict | str | None = None,
    ):
        priority = int(severity if severity is not None else CONFLICT_SEVERITY.get(conflict_type, 6))
        resolver_key = resolver_key or self._conflict_resolver_key(conflict_type)
        if subject_type is None and entity_a_id is not None:
            subject_type = "entity"
        if subject_key is None and entity_a_id is not None:
            subject_key = entity_a_id
        evidence_refs = evidence_refs if isinstance(evidence_refs, list) else ([evidence_refs] if evidence_refs else [])
        alternatives = alternatives if isinstance(alternatives, list) else ([alternatives] if alternatives else [])
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO conflict_records (
                    conflict_type, entity_a_id, entity_b_id, chapter, payload, resolver_key,
                    subject_type, subject_key, evidence_refs_json, alternatives_json, severity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conflict_type,
                entity_a_id,
                entity_b_id,
                chapter,
                json.dumps(payload, ensure_ascii=False),
                resolver_key,
                subject_type,
                None if subject_key is None else str(subject_key),
                json.dumps(evidence_refs, ensure_ascii=False, sort_keys=True),
                json.dumps(alternatives, ensure_ascii=False, sort_keys=True),
                priority,
            ))

    def resolve_conflict(self, conflict_id: int, status: str, resolution: str = ""):
        if status not in {"reviewed", "resolved", "rejected"}:
            raise ValueError("status must be reviewed, resolved, or rejected")
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE conflict_records
                SET status = ?,
                    reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                    resolution = ?,
                    resolved_at = CASE
                        WHEN ? IN ('resolved', 'rejected') THEN CURRENT_TIMESTAMP
                        ELSE resolved_at
                    END
                WHERE id = ?
            """, (status, resolution, status, conflict_id))

    def apply_confidence_decay(self, current_chapter: int):
        cutoff = max(0, current_chapter - CONFIDENCE_DECAY_AFTER_CHAPTERS)
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE aliases
                SET confidence = confidence * ?
                WHERE status IN ('candidate', 'probable', 'review') AND COALESCE(last_seen, chapter_found, 0) < ?
            """, (CONFIDENCE_DECAY_FACTOR, cutoff))
            conn.execute("""
                UPDATE aliases
                SET status = 'review'
                WHERE status IN ('candidate', 'probable') AND confidence < ?
            """, (ALIAS_REVIEW_CONFIDENCE,))
            conn.execute("""
                UPDATE aliases
                SET status = 'expired'
                WHERE status = 'review' AND confidence < ?
            """, (ALIAS_EXPIRED_CONFIDENCE,))
            conn.execute("""
                UPDATE entities
                SET confidence = confidence * ?
                WHERE confidence < ? AND COALESCE(last_verified_chapter, first_seen_chapter, 0) < ?
            """, (CONFIDENCE_DECAY_FACTOR, ENTITY_REVIEW_CONFIDENCE, cutoff))

    def get_resolution_matrices(self, entity_type: str):
        alias_to_id = {}
        id_to_canon = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, a.alias_name, a.alias_key
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                    AND COALESCE(a.status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
                WHERE e.entity_type = ?
            """, (entity_type,))
            
            for eid, canon, alias, alias_key in cursor.fetchall():
                id_to_canon[eid] = canon
                alias_to_id[self.normalize_alias_key(canon)] = eid
                if alias:
                    alias_to_id[alias_key or self.normalize_alias_key(alias)] = eid
            cursor.execute("""
                SELECT e.id, e.canonical_name, t.title_text, t.title_key
                FROM entities e
                JOIN title_links t ON e.id = t.entity_id
                WHERE e.entity_type = ?
                  AND COALESCE(t.status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
            """, (entity_type,))
            for eid, canon, title, title_key in cursor.fetchall():
                id_to_canon[eid] = canon
                alias_to_id[title_key or self.normalize_alias_key(title)] = eid
        return alias_to_id, id_to_canon

    def get_known_entities_text(self, entity_type: str, chapter_text_lower: str) -> str:
        active = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, GROUP_CONCAT(a.alias_name || ':' || a.status, '|') 
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                    AND COALESCE(a.status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
                WHERE e.entity_type = ?
                GROUP BY e.id, e.canonical_name
                ORDER BY e.visibility_score DESC, e.last_verified_chapter DESC, e.mention_count DESC
                LIMIT ?
            """, (entity_type, self.ACTIVE_ENTITY_LIMIT))
            
            for row in cursor.fetchall():
                entity_id = row[0]
                canon = row[1]
                aliases_raw = row[2].split('|') if row[2] else []
                aliases = [a for a in aliases_raw if a]
                alias_terms = [a.rsplit(":", 1)[0] for a in aliases]
                cursor.execute("""
                    SELECT title_text || ':' || status
                    FROM title_links
                    WHERE entity_id = ?
                      AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
                    ORDER BY confidence DESC, support_count DESC
                    LIMIT 4
                """, (entity_id,))
                titles = [title for (title,) in cursor.fetchall()]
                title_terms = [title.rsplit(":", 1)[0] for title in titles]
                
                search_terms = tuple([canon] + alias_terms + title_terms)
                
                if search_terms not in self._regex_cache:
                    pattern = r'\b(?:' + '|'.join(map(re.escape, [t.lower() for t in search_terms])) + r')\b'
                    self._regex_cache[search_terms] = re.compile(pattern)
                else:
                    self._regex_cache.move_to_end(search_terms)

                if len(self._regex_cache) > REGEX_CACHE_SIZE:
                    self._regex_cache.popitem(last=False)
                    
                if self._regex_cache[search_terms].search(chapter_text_lower):
                    active[canon] = aliases + titles
                    
        if not active:
            return f"No known {entity_type.lower()}s detected in this chapter's text yet."
            
        return "\n".join([f"- {c} (aliases/status: {', '.join(a)})" if a else f"- {c}" for c, a in active.items()])

    def add_entity(
        self,
        canonical_name: str,
        entity_type: str,
        chapter_idx: int,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
        ontology: dict | None = None,
    ) -> int:
        canonical_name = " ".join(str(canonical_name or "").split())
        normalized_ontology = self.normalize_entity_ontology(ontology, entity_type, canonical_name)
        existing_id = self._find_scoped_entity_id(
            canonical_name,
            entity_type,
            chapter_idx,
            boundary_title_id=boundary_title_id,
            boundary_book_id=boundary_book_id,
            boundary_volume_id=boundary_volume_id,
            session_id=session_id,
        )
        if existing_id:
            existing_ontology = self.get_entity_ontology(existing_id)
            if ontology and existing_ontology and self.ontology_compatibility_reason(normalized_ontology, existing_ontology):
                existing_id = None
        if existing_id:
            self.register_entity_type_vote(existing_id, entity_type, chapter_idx)
            if ontology:
                self.update_entity_ontology(
                    existing_id,
                    ontology,
                    chapter_idx=chapter_idx,
                    confidence=normalized_ontology.get("ontology_confidence", 0.5),
                    source_text=normalized_ontology.get("ontology_evidence", ""),
                    ontology_source="ingest",
                )
            self.update_entity_verification(existing_id, chapter_idx)
            return existing_id

        importance, visibility, surface_class, location_subtype = self._initial_importance(canonical_name, entity_type)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO entities (
                    canonical_name, display_name, entity_type, first_seen_chapter, last_verified_chapter,
                    mention_count, confidence, type_support_count,
                    importance_score, visibility_score, surface_form_class, location_subtype,
                    entity_category, species_or_kind, sentience, narrative_role,
                    story_role, functional_role, active_status, identity_status,
                    entity_persistence, canonical_identity, body_form, embodiment,
                    agency_score, can_speak, can_move, can_think, can_remember,
                    can_make_decisions, can_form_relationships, ontology_confidence,
                    ontology_evidence, literal_status, interpretation_status,
                    language_status, translation_status, raw_surface_form, social_status,
                    boundary_title_id, boundary_book_id, boundary_volume_id,
                    session_id, source_session, inherited_confidence
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                canonical_name,
                canonical_name,
                entity_type,
                chapter_idx,
                chapter_idx,
                ENTITY_BASE_CONFIDENCE,
                importance,
                visibility,
                surface_class,
                location_subtype,
                normalized_ontology["entity_category"],
                normalized_ontology["species_or_kind"],
                normalized_ontology["sentience"],
                normalized_ontology["narrative_role"],
                normalized_ontology["story_role"],
                normalized_ontology["functional_role"],
                normalized_ontology["active_status"],
                normalized_ontology["identity_status"],
                normalized_ontology["entity_persistence"],
                normalized_ontology["canonical_identity"],
                normalized_ontology["body_form"],
                normalized_ontology["embodiment"],
                normalized_ontology["agency_score"],
                normalized_ontology["can_speak"],
                normalized_ontology["can_move"],
                normalized_ontology["can_think"],
                normalized_ontology["can_remember"],
                normalized_ontology["can_make_decisions"],
                normalized_ontology["can_form_relationships"],
                normalized_ontology["ontology_confidence"],
                normalized_ontology["ontology_evidence"],
                normalized_ontology["literal_status"],
                normalized_ontology["interpretation_status"],
                normalized_ontology["language_status"],
                normalized_ontology["translation_status"],
                normalized_ontology["raw_surface_form"],
                normalized_ontology["social_status"],
                boundary_title_id,
                boundary_book_id or boundary_title_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence,
            ))
            entity_id = cursor.lastrowid
            for field in ONTOLOGY_FIELDS:
                value = normalized_ontology.get(field)
                if value in UNKNOWN_ONTOLOGY_VALUES and field not in {"entity_category", "active_status", "entity_persistence"}:
                    continue
                self.record_entity_ontology_evidence(
                    entity_id,
                    field,
                    None,
                    value,
                    chapter_idx=chapter_idx,
                    confidence=normalized_ontology.get("ontology_confidence", 0.5),
                    source_text=normalized_ontology.get("ontology_evidence", ""),
                    ontology_source="ingest",
                    conn=conn,
                )
            cursor.execute("""
                INSERT OR IGNORE INTO entity_type_votes (
                    entity_id, entity_type, support_count, confidence, first_seen, last_seen
                )
                VALUES (?, ?, 1, ?, ?, ?)
            """, (entity_id, entity_type, ENTITY_BASE_CONFIDENCE, chapter_idx, chapter_idx))
            self._mark_entity_search_dirty(conn, entity_id)
            return entity_id

    def _effective_identity_scope(
        self,
        chapter_idx: int,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        chapter_scope = self.get_chapter_boundary(chapter_idx)
        book_id = boundary_book_id or boundary_title_id or chapter_scope.get("book_id") or chapter_scope.get("title_id")
        return {
            "title_id": boundary_title_id or chapter_scope.get("title_id"),
            "book_id": book_id,
            "volume_id": boundary_volume_id or chapter_scope.get("volume_id"),
            "session_id": session_id or chapter_scope.get("session_id"),
        }

    def _scope_compatibility(self, candidate: dict, scope: dict) -> tuple[bool, float, str]:
        cand_book = candidate.get("boundary_book_id") or candidate.get("boundary_title_id")
        cand_volume = candidate.get("boundary_volume_id")
        cand_session = candidate.get("session_id")
        scope_book = scope.get("book_id") or scope.get("title_id")
        scope_volume = scope.get("volume_id")
        scope_session = scope.get("session_id")
        inherited_confidence = max(0.05, min(1.0, float(candidate.get("inherited_confidence") or LOCAL_GRAPH_CONFIDENCE)))

        if cand_book and scope_book and cand_book != scope_book:
            return False, 0.0, "different_book_boundary"
        if cand_volume and scope_volume and cand_volume != scope_volume:
            return False, 0.0, "different_volume_boundary"
        if cand_session and scope_session and cand_session != scope_session:
            return False, 0.0, "different_session_boundary"
        if not cand_book and not cand_session:
            return True, 0.82, "legacy_unscoped_candidate"
        if inherited_confidence < 0.999:
            return True, inherited_confidence, "inherited_candidate"
        return True, 1.0, "same_scope"

    def _find_scoped_entity_id(
        self,
        canonical_name: str,
        entity_type: str,
        chapter_idx: int,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
    ) -> int | None:
        canonical_name = " ".join(str(canonical_name or "").split())
        if not canonical_name:
            return None
        scope = self._effective_identity_scope(
            chapter_idx,
            boundary_title_id=boundary_title_id,
            boundary_book_id=boundary_book_id,
            boundary_volume_id=boundary_volume_id,
            session_id=session_id,
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id
                FROM entities
                WHERE entity_type = ?
                  AND lower(canonical_name) = lower(?)
                ORDER BY COALESCE(inherited_confidence, 1.0) DESC, id
            """, (entity_type, canonical_name))
            matches = []
            for (entity_id,) in cursor.fetchall():
                signature = self._entity_signature(cursor, entity_id)
                if not signature:
                    continue
                compatible, scope_weight, _reason = self._scope_compatibility(signature, scope)
                if compatible:
                    matches.append((scope_weight, entity_id))
        if not matches:
            return None
        matches.sort(reverse=True)
        if len(matches) > 1 and abs(matches[0][0] - matches[1][0]) < 0.001:
            return None
        return matches[0][1]

    def _entity_signature(self, cursor, entity_id: int) -> dict | None:
        cursor.execute("""
            SELECT id, canonical_name, entity_type, first_seen_chapter,
                   last_verified_chapter, mention_count, confidence,
                   surface_form_class, COALESCE(inherited_confidence, 1.0),
                   source_session, boundary_title_id, boundary_book_id,
                   boundary_volume_id, session_id, entity_category,
                   species_or_kind, sentience, active_status,
                   identity_status, entity_persistence
            FROM entities
            WHERE id = ?
        """, (entity_id,))
        row = cursor.fetchone()
        if not row:
            return None
        (
            _id,
            canonical_name,
            entity_type,
            first_seen,
            last_seen,
            mention_count,
            confidence,
            surface_class,
            inherited_confidence,
            source_session,
            boundary_title_id,
            boundary_book_id,
            boundary_volume_id,
            session_id,
            entity_category,
            species_or_kind,
            sentience,
            active_status,
            identity_status,
            entity_persistence,
        ) = row
        canonical_key = self.normalize_alias_key(canonical_name)
        tokens = _strip_title_tokens(_name_tokens(canonical_key))
        signature = {
            "id": _id,
            "canonical_name": canonical_name,
            "canonical_key": canonical_key,
            "entity_type": entity_type,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "mention_count": mention_count or 0,
            "confidence": confidence or 0.0,
            "surface_class": surface_class or "",
            "inherited_confidence": inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE,
            "source_session": source_session,
            "boundary_title_id": boundary_title_id,
            "boundary_book_id": boundary_book_id,
            "boundary_volume_id": boundary_volume_id,
            "session_id": session_id,
            "entity_category": entity_category or "UNKNOWN",
            "species_or_kind": species_or_kind or "unknown",
            "sentience": sentience or "unknown",
            "active_status": active_status or "uncertain",
            "identity_status": identity_status or "unknown",
            "entity_persistence": entity_persistence or "persistent",
            "aliases": set(),
            "titles": set(),
            "neighbors": set(),
            "social_neighbors": set(),
            "events": set(),
            "tokens": tokens,
            "title_class": _title_prefix_class(canonical_key),
        }
        cursor.execute("""
            SELECT alias_key
            FROM aliases
            WHERE entity_id = ?
              AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """, (entity_id,))
        signature["aliases"] = {alias_key for (alias_key,) in cursor.fetchall() if alias_key}
        cursor.execute("""
            SELECT title_key
            FROM title_links
            WHERE entity_id = ?
              AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """, (entity_id,))
        signature["titles"] = {title_key for (title_key,) in cursor.fetchall() if title_key}
        cursor.execute("SELECT source_id, target_id FROM relationships WHERE source_id = ? OR target_id = ?", (entity_id, entity_id))
        for source_id, target_id in cursor.fetchall():
            other_id = target_id if source_id == entity_id else source_id
            signature["neighbors"].add(other_id)
        cursor.execute("""
            SELECT source_id, target_id
            FROM relationship_social_edges
            WHERE source_id = ? OR target_id = ?
        """, (entity_id, entity_id))
        for source_id, target_id in cursor.fetchall():
            other_id = target_id if source_id == entity_id else source_id
            signature["social_neighbors"].add(other_id)
        cursor.execute("SELECT event_id FROM event_participants WHERE entity_id = ?", (entity_id,))
        signature["events"] = {event_id for (event_id,) in cursor.fetchall()}
        return signature

    def _identity_hard_rejection(self, cursor, mention_key: str, mention_type: str, candidate: dict) -> str | None:
        if candidate["entity_type"] != mention_type:
            return "entity type mismatch"
        mention_defaults = self.normalize_entity_ontology({}, mention_type, mention_key)
        ontology_rejection = self.ontology_compatibility_reason(mention_defaults, candidate)
        if ontology_rejection:
            return ontology_rejection
        mention_title_class = _title_prefix_class(mention_key)
        if mention_title_class and candidate["title_class"] and mention_title_class != candidate["title_class"]:
            return "incompatible title evidence"
        if mention_key != candidate["canonical_key"]:
            semantic_blocker = self._has_name_semantic_blocker(
                cursor,
                mention_key,
                candidate["canonical_key"],
                {
                    "namesake",
                    "eponym_attribution",
                    "homonym_collision",
                    "possessive_reference",
                    "same_surface_distinct_referent",
                },
            )
            if semantic_blocker:
                return f"name semantic relation is not identity: {semantic_blocker}"
        mention_tokens = _strip_title_tokens(_name_tokens(mention_key))
        candidate_tokens = candidate["tokens"]
        if not mention_tokens or not candidate_tokens:
            return "missing usable name tokens"
        mention_suffix = mention_tokens[-1]
        candidate_suffix = candidate_tokens[-1]
        if (
            mention_suffix in LOW_INFORMATION_SUFFIXES
            and candidate_suffix in LOW_INFORMATION_SUFFIXES
            and mention_key != candidate["canonical_key"]
            and mention_key not in candidate["aliases"]
        ):
            return "low information role-only surface"
        return None

    def _score_identity_candidate(
        self,
        cursor,
        mention_name: str,
        entity_type: str,
        candidate_id: int,
        chapter_idx: int,
        scope: dict | None = None,
    ) -> dict | None:
        mention_key = self.normalize_alias_key(mention_name)
        candidate = self._entity_signature(cursor, candidate_id)
        if not mention_key or not candidate:
            return None
        scope = scope or self._effective_identity_scope(chapter_idx)
        scope_compatible, scope_weight, scope_reason = self._scope_compatibility(candidate, scope)
        if not scope_compatible:
            return {
                "entity_id": candidate_id,
                "state": "rejected",
                "score": 0.0,
                "reason": scope_reason,
                "features": {"hard_rejection": scope_reason},
            }
        rejection = self._identity_hard_rejection(cursor, mention_key, entity_type, candidate)
        if rejection:
            return {
                "entity_id": candidate_id,
                "state": "rejected",
                "score": 0.0,
                "reason": rejection,
                "features": {"hard_rejection": rejection},
            }

        mention_tokens = _strip_title_tokens(_name_tokens(mention_key))
        candidate_terms = {candidate["canonical_key"], *candidate["aliases"], *candidate["titles"]}
        candidate_terms.discard("")
        candidate_core_terms = {" ".join(_strip_title_tokens(_name_tokens(term))) for term in candidate_terms}
        candidate_core_terms.discard("")
        mention_core = " ".join(mention_tokens)
        mention_token_set = set(mention_tokens)
        candidate_token_set = set(candidate["tokens"])
        overlap = len(mention_token_set & candidate_token_set)
        union = len(mention_token_set | candidate_token_set) or 1
        name_similarity = overlap / union
        alias_evidence = 0.0
        if mention_key in candidate_terms:
            alias_evidence = 1.0
        elif mention_core and mention_core in candidate_core_terms:
            alias_evidence = 0.85
        elif mention_tokens and candidate["tokens"]:
            if mention_core and (mention_core in candidate["canonical_key"] or candidate["canonical_key"] in mention_core):
                alias_evidence = 0.65

        mention_suffix = mention_tokens[-1] if mention_tokens else ""
        candidate_suffix = candidate["tokens"][-1] if candidate["tokens"] else ""
        suffix_overlap = bool(mention_suffix and candidate_suffix and mention_suffix == candidate_suffix)
        if suffix_overlap and mention_suffix not in LOW_INFORMATION_SUFFIXES:
            name_similarity = max(name_similarity, 0.45)

        metadata_similarity = 1.0 if candidate["entity_type"] == entity_type else 0.0
        relationship_similarity = min(len(candidate["neighbors"]), 6) / 6
        social_context_similarity = min(len(candidate["social_neighbors"]), 8) / 8
        temporal_consistency = 0.5
        if candidate["first_seen"] is not None:
            temporal_consistency = 1.0 if int(candidate["first_seen"]) <= chapter_idx else 0.2
        extraction_support = min(int(candidate["mention_count"] or 0), 10) / 10
        local_evidence_weight = max(0.05, min(1.0, float(candidate.get("inherited_confidence") or LOCAL_GRAPH_CONFIDENCE)))

        score = (
            0.40 * name_similarity
            + 0.25 * alias_evidence
            + 0.15 * metadata_similarity
            + 0.07 * relationship_similarity
            + 0.03 * social_context_similarity
            + 0.05 * temporal_consistency
            + 0.05 * extraction_support
        )
        if local_evidence_weight < 0.999:
            score *= 0.78 + (0.22 * local_evidence_weight)
        if scope_weight < 0.999:
            score *= max(0.05, min(1.0, scope_weight))

        features = {
            "name_similarity": round(name_similarity, 4),
            "alias_evidence": round(alias_evidence, 4),
            "metadata_similarity": round(metadata_similarity, 4),
            "relationship_similarity": round(relationship_similarity, 4),
            "social_context_similarity": round(social_context_similarity, 4),
            "temporal_consistency": round(temporal_consistency, 4),
            "extraction_support": round(extraction_support, 4),
            "local_evidence_weight": round(local_evidence_weight, 4),
            "scope_weight": round(scope_weight, 4),
            "scope_reason": scope_reason,
            "source_session": candidate.get("source_session"),
            "suffix_overlap": suffix_overlap,
        }
        return {
            "entity_id": candidate_id,
            "state": "candidate",
            "score": round(score, 4),
            "reason": "multi-signal identity candidate",
            "features": features,
        }

    def _identity_candidate_ids(
        self,
        cursor,
        mention_name: str,
        entity_type: str,
        limit: int = 12,
        scope: dict | None = None,
    ) -> list[int]:
        mention_key = self.normalize_alias_key(mention_name)
        if not mention_key:
            return []
        terms = self._search_terms_for_text(mention_key, max_ngram=4)
        terms.add(mention_key)
        ids: set[int] = set()
        for offset in range(0, len(terms), 800):
            chunk = list(terms)[offset:offset + 800]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            cursor.execute(f"""
                SELECT est.entity_id, COUNT(*) AS hits,
                       e.boundary_title_id, e.boundary_book_id,
                       e.boundary_volume_id, e.session_id,
                       COALESCE(e.inherited_confidence, 1.0)
                FROM entity_search_terms est
                JOIN entities e ON e.id = est.entity_id
                WHERE est.term IN ({placeholders})
                  AND e.entity_type = ?
                  AND est.status IN ('accepted', 'probable', 'candidate', 'review')
                GROUP BY est.entity_id
                ORDER BY hits DESC, e.mention_count DESC
                LIMIT ?
            """, (*chunk, entity_type, limit))
            for entity_id, _hits, boundary_title_id, boundary_book_id, boundary_volume_id, row_session_id, inherited_confidence in cursor.fetchall():
                candidate_scope = {
                    "boundary_title_id": boundary_title_id,
                    "boundary_book_id": boundary_book_id,
                    "boundary_volume_id": boundary_volume_id,
                    "session_id": row_session_id,
                    "inherited_confidence": inherited_confidence,
                }
                if not scope or self._scope_compatibility(candidate_scope, scope)[0]:
                    ids.add(entity_id)

        tokens = _strip_title_tokens(_name_tokens(mention_key))
        if tokens:
            suffix = tokens[-1]
            if suffix and suffix not in LOW_INFORMATION_SUFFIXES:
                cursor.execute("""
                    SELECT id, boundary_title_id, boundary_book_id,
                           boundary_volume_id, session_id,
                           COALESCE(inherited_confidence, 1.0)
                    FROM entities
                    WHERE entity_type = ?
                      AND lower(canonical_name) LIKE ?
                    ORDER BY mention_count DESC, id
                    LIMIT ?
                """, (entity_type, f"%{suffix}%", limit))
                for entity_id, boundary_title_id, boundary_book_id, boundary_volume_id, row_session_id, inherited_confidence in cursor.fetchall():
                    candidate_scope = {
                        "boundary_title_id": boundary_title_id,
                        "boundary_book_id": boundary_book_id,
                        "boundary_volume_id": boundary_volume_id,
                        "session_id": row_session_id,
                        "inherited_confidence": inherited_confidence,
                    }
                    if not scope or self._scope_compatibility(candidate_scope, scope)[0]:
                        ids.add(entity_id)

        return sorted(ids)[:limit]

    def record_identity_resolution_evidence(
        self,
        mention_name: str,
        entity_type: str,
        chapter_idx: int,
        state: str,
        target_entity_id: int | None = None,
        source_entity_id: int | None = None,
        confidence: float = 0.0,
        score: float = 0.0,
        margin: float = 0.0,
        candidate_count: int = 0,
        ambiguity_reason: str | None = None,
        evidence_type: str = "resolver",
        evidence: dict | str | None = None,
    ) -> int | None:
        mention_key = self.normalize_alias_key(mention_name)
        if not mention_key:
            return None
        payload = json.dumps(evidence, ensure_ascii=False, sort_keys=True) if isinstance(evidence, dict) else (evidence or "")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO identity_resolution_evidence (
                    source_entity_id, target_entity_id, mention_text, mention_key,
                    entity_type, chapter, state, confidence, score, margin,
                    candidate_count, ambiguity_reason, evidence_type, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_entity_id,
                target_entity_id,
                mention_name,
                mention_key,
                entity_type,
                chapter_idx,
                state,
                confidence,
                score,
                margin,
                int(candidate_count or 0),
                ambiguity_reason,
                evidence_type,
                payload,
            ))
            evidence_id = cursor.lastrowid
            candidate_list = evidence.get("candidates", []) if isinstance(evidence, dict) else []
            self.record_resolver_decision(
                "identity",
                "entity" if target_entity_id else "mention",
                target_entity_id if target_entity_id else mention_key,
                chapter_idx,
                state,
                confidence=confidence,
                supporting_evidence=[{"table": "identity_resolution_evidence", "id": evidence_id, "type": evidence_type}],
                rejected_alternatives=candidate_list if state != "resolved" else [],
                metadata={
                    "mention": mention_name,
                    "entity_type": entity_type,
                    "score": score,
                    "margin": margin,
                    "candidate_count": candidate_count,
                    "ambiguity_reason": ambiguity_reason,
                },
                conn=conn,
            )
            return evidence_id

    def record_unresolved_mention(
        self,
        mention_name: str,
        entity_type: str,
        chapter_idx: int,
        candidates: list[dict] | None = None,
        confidence: float = 0.0,
        ambiguous: bool = True,
        reason: str = "",
        speaker_entity_id: int | None = None,
        narrator_entity_id: int | None = None,
        scene_scope: str | None = None,
    ) -> int | None:
        mention_key = self.normalize_alias_key(mention_name)
        if not mention_key:
            return None
        classification = self.classify_mention_surface(mention_name, entity_type)
        payload = json.dumps(candidates or [], ensure_ascii=False, sort_keys=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO unresolved_mentions (
                    mention_text, mention_key, entity_type, chapter,
                    candidate_entities, confidence, ambiguous, reason,
                    mention_class, title_category, speaker_entity_id,
                    narrator_entity_id, scene_scope
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mention_name,
                mention_key,
                entity_type,
                chapter_idx,
                payload,
                confidence,
                1 if ambiguous else 0,
                reason,
                classification["mention_class"],
                classification["title_category"],
                speaker_entity_id,
                narrator_entity_id,
                scene_scope,
            ))
            return cursor.lastrowid

    def record_kinship_mention(
        self,
        mention_text: str,
        chapter_idx: int,
        speaker_entity_id: int | None = None,
        narrator_entity_id: int | None = None,
        candidates: list[dict] | None = None,
        confidence: float = 0.0,
        evidence: str = "",
        status: str = "unresolved",
        resolved_entity_id: int | None = None,
    ) -> int | None:
        mention_key = self.normalize_alias_key(mention_text)
        if not mention_key:
            return None
        kinship_term = next((token for token in _name_tokens(mention_key) if token in KINSHIP_TERMS), mention_key)
        payload = json.dumps(candidates or [], ensure_ascii=False, sort_keys=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO kinship_mentions (
                    mention_text, mention_key, kinship_term, chapter,
                    speaker_entity_id, narrator_entity_id, resolved_entity_id,
                    candidate_entities, confidence, status, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mention_text,
                mention_key,
                kinship_term,
                chapter_idx,
                speaker_entity_id,
                narrator_entity_id,
                resolved_entity_id,
                payload,
                confidence,
                status,
                evidence,
            ))
            return cursor.lastrowid

    def should_create_entity_after_resolution(self, mention_name: str, entity_type: str, resolution: dict) -> bool:
        if resolution.get("state") != "ambiguous":
            return True
        mention_key = self.normalize_alias_key(mention_name)
        tokens = _strip_title_tokens(_name_tokens(mention_key))
        if len(tokens) <= 1:
            return False
        if tokens and tokens[-1] in LOW_INFORMATION_SUFFIXES:
            return False
        if entity_type in {"INDIVIDUAL", "GROUP"} and len(resolution.get("candidates", [])) > 1:
            return False
        return resolution.get("score", 0.0) < 0.45

    def resolve_entity_reference(
        self,
        mention_name: str,
        entity_type: str,
        chapter_idx: int,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        mention_name = " ".join(str(mention_name or "").split())
        mention_key = self.normalize_alias_key(mention_name)
        if not mention_key:
            return {"state": "unresolved", "entity_id": None, "canonical_name": None, "score": 0.0, "margin": 0.0}
        scope = self._effective_identity_scope(
            chapter_idx,
            boundary_title_id=boundary_title_id,
            boundary_book_id=boundary_book_id,
            boundary_volume_id=boundary_volume_id,
            session_id=session_id,
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, canonical_name, boundary_title_id, boundary_book_id,
                       boundary_volume_id, session_id, COALESCE(inherited_confidence, 1.0)
                FROM entities
                WHERE entity_type = ?
                  AND lower(canonical_name) = lower(?)
            """, (entity_type, mention_name))
            exact_rows = cursor.fetchall()
            exact_matches = []
            for entity_id, canonical_name, row_title_id, row_book_id, row_volume_id, row_session_id, inherited_confidence in exact_rows:
                compatible, scope_weight, scope_reason = self._scope_compatibility(
                    {
                        "boundary_title_id": row_title_id,
                        "boundary_book_id": row_book_id,
                        "boundary_volume_id": row_volume_id,
                        "session_id": row_session_id,
                        "inherited_confidence": inherited_confidence,
                    },
                    scope,
                )
                if compatible:
                    exact_matches.append((scope_weight, scope_reason, entity_id, canonical_name))
            exact_matches.sort(reverse=True)
            if exact_matches and (len(exact_matches) == 1 or abs(exact_matches[0][0] - exact_matches[1][0]) >= 0.001):
                scope_weight, scope_reason, entity_id, canonical_name = exact_matches[0]
                self.record_identity_resolution_evidence(
                    mention_name,
                    entity_type,
                    chapter_idx,
                    "resolved",
                    target_entity_id=entity_id,
                    confidence=scope_weight,
                    score=scope_weight,
                    margin=1.0,
                    evidence_type="exact_canonical",
                    evidence={"scope_reason": scope_reason, "scope": scope},
                )
                return {"state": "resolved", "entity_id": entity_id, "canonical_name": canonical_name, "score": scope_weight, "margin": 1.0}
            if len(exact_matches) > 1:
                self.record_identity_resolution_evidence(
                    mention_name,
                    entity_type,
                    chapter_idx,
                    "ambiguous",
                    confidence=exact_matches[0][0],
                    score=exact_matches[0][0],
                    margin=0.0,
                    candidate_count=len(exact_matches),
                    ambiguity_reason="multiple_exact_matches_in_scope",
                    evidence_type="exact_canonical_ambiguity",
                    evidence={"candidates": exact_matches[:5], "scope": scope},
                )
                return {
                    "state": "ambiguous",
                    "entity_id": None,
                    "canonical_name": None,
                    "score": exact_matches[0][0],
                    "margin": 0.0,
                    "candidates": [{"entity_id": item[2], "canonical_name": item[3], "score": item[0], "reason": item[1]} for item in exact_matches[:5]],
                }

            candidate_ids = self._identity_candidate_ids(cursor, mention_name, entity_type, scope=scope)
            scored = [
                scored_candidate
                for candidate_id in candidate_ids
                if (scored_candidate := self._score_identity_candidate(cursor, mention_name, entity_type, candidate_id, chapter_idx, scope=scope))
            ]
            viable = [item for item in scored if item["state"] != "rejected"]
            viable.sort(key=lambda item: (-item["score"], item["entity_id"]))
            if not viable:
                self.record_identity_resolution_evidence(
                    mention_name,
                    entity_type,
                    chapter_idx,
                    "unresolved",
                    candidate_count=len(scored),
                    ambiguity_reason="no_viable_candidate",
                    evidence_type="candidate_search",
                    evidence={"candidates": scored},
                )
                return {
                    "state": "unresolved",
                    "entity_id": None,
                    "canonical_name": None,
                    "score": 0.0,
                    "margin": 0.0,
                    "candidates": scored,
                }

            best = viable[0]
            second_score = viable[1]["score"] if len(viable) > 1 else 0.0
            margin = round(best["score"] - second_score, 4)
            uniquely_supported = len(viable) == 1 and best["score"] >= 0.55
            state = "resolved" if (best["score"] >= 0.78 and margin >= 0.12) or uniquely_supported else "ambiguous"
            cursor.execute("SELECT canonical_name FROM entities WHERE id = ?", (best["entity_id"],))
            name_row = cursor.fetchone()
            canonical_name = name_row[0] if name_row else None
            self.record_identity_resolution_evidence(
                mention_name,
                entity_type,
                chapter_idx,
                state,
                target_entity_id=best["entity_id"] if state == "resolved" else None,
                confidence=best["score"],
                score=best["score"],
                margin=margin,
                candidate_count=len(viable),
                ambiguity_reason=None if state == "resolved" else "multiple_plausible_candidates",
                evidence_type="multi_signal_resolution",
                evidence={"best": best, "candidates": viable[:5]},
            )
            if state == "resolved":
                return {
                    "state": state,
                    "entity_id": best["entity_id"],
                    "canonical_name": canonical_name,
                    "score": best["score"],
                    "margin": margin,
                    "candidates": viable[:5],
                }
            return {
                "state": state,
                "entity_id": None,
                "canonical_name": None,
                "score": best["score"],
                "margin": margin,
                "candidates": viable[:5],
            }

    def resolve_or_create_entity(
        self,
        canonical_name: str,
        entity_type: str,
        chapter_idx: int,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
        ontology: dict | None = None,
    ) -> tuple[int, str]:
        resolution = self.resolve_entity_reference(
            canonical_name,
            entity_type,
            chapter_idx,
            boundary_title_id=boundary_title_id,
            boundary_book_id=boundary_book_id,
            boundary_volume_id=boundary_volume_id,
            session_id=session_id,
        )
        if resolution["state"] == "resolved" and resolution["entity_id"] and ontology:
            existing_ontology = self.get_entity_ontology(resolution["entity_id"])
            mention_ontology = self.normalize_entity_ontology(ontology, entity_type, canonical_name)
            compatibility_reason = (
                self.ontology_compatibility_reason(mention_ontology, existing_ontology)
                if existing_ontology
                else None
            )
            if compatibility_reason:
                self.record_conflict(
                    "ontology_incompatibility",
                    chapter_idx,
                    {
                        "mention": canonical_name,
                        "entity_type": entity_type,
                        "reason": compatibility_reason,
                        "incoming": mention_ontology,
                        "existing": existing_ontology,
                    },
                    resolution["entity_id"],
                    resolver_key="ontology",
                    subject_type="entity",
                    subject_key=resolution["entity_id"],
                )
                resolution = {
                    "state": "unresolved",
                    "entity_id": None,
                    "canonical_name": None,
                    "score": 0.0,
                    "margin": 0.0,
                    "candidates": [],
                }
        if resolution["state"] == "resolved" and resolution["entity_id"]:
            self.update_entity_verification(resolution["entity_id"], chapter_idx)
            if ontology:
                self.update_entity_ontology(
                    resolution["entity_id"],
                    ontology,
                    chapter_idx=chapter_idx,
                    confidence=self.normalize_entity_ontology(ontology, entity_type, canonical_name).get("ontology_confidence", 0.5),
                    source_text=self.normalize_entity_ontology(ontology, entity_type, canonical_name).get("ontology_evidence", ""),
                    ontology_source="ingest",
                )
            return resolution["entity_id"], "resolved"
        if not self.should_create_entity_after_resolution(canonical_name, entity_type, resolution):
            self.record_unresolved_mention(
                canonical_name,
                entity_type,
                chapter_idx,
                resolution.get("candidates", [])[:5],
                confidence=resolution.get("score", 0.0),
                ambiguous=True,
                reason="ambiguous_short_form",
            )
            return None, "ambiguous_unresolved"
        entity_id = self.add_entity(
            canonical_name,
            entity_type,
            chapter_idx,
            boundary_title_id=boundary_title_id,
            boundary_book_id=boundary_book_id,
            boundary_volume_id=boundary_volume_id,
            session_id=session_id,
            source_session=source_session,
            inherited_confidence=inherited_confidence,
            ontology=ontology,
        )
        state = "created_after_ambiguous" if resolution["state"] == "ambiguous" else "created"
        self.record_identity_resolution_evidence(
            canonical_name,
            entity_type,
            chapter_idx,
            state,
            target_entity_id=entity_id,
            confidence=ENTITY_BASE_CONFIDENCE,
            score=resolution.get("score", 0.0),
            margin=resolution.get("margin", 0.0),
            candidate_count=len(resolution.get("candidates", []) or []),
            ambiguity_reason=resolution["state"] if resolution["state"] != "unresolved" else None,
            evidence_type="entity_creation_fallback",
            evidence={"resolution_state": resolution["state"], "candidates": resolution.get("candidates", [])[:5]},
        )
        return entity_id, state

    def discover_aliases_from_canonical(self, entity_id: int, chapter_idx: int) -> list[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            signature = self._entity_signature(cursor, entity_id)
            if not signature:
                return []
            tokens = signature["tokens"]
            if len(tokens) < 2:
                return []
            first = tokens[0]
            candidates = []
            if signature["entity_type"] == "INDIVIDUAL":
                candidates.append(first)
            else:
                candidates.append(first)
                if len(tokens) > 2:
                    initials = "".join(token[0] for token in tokens if token)
                    if len(initials) > 1:
                        candidates.append(initials)
            candidates = [
                alias_key
                for alias_key in candidates
                if len(alias_key) > 2
                and alias_key not in LOW_INFORMATION_SUFFIXES
                and alias_key != signature["canonical_key"]
                and alias_key not in signature["aliases"]
            ]

        accepted = []
        for alias_key in candidates:
            resolution = self.resolve_entity_reference(alias_key, signature["entity_type"], chapter_idx)
            if resolution["state"] == "unresolved":
                status = self.add_alias(
                    entity_id,
                    alias_key,
                    chapter_idx,
                    f"Derived from canonical name: {signature['canonical_name']}",
                    confidence=0.45,
                    validation_status="derived_short_form",
                    validation_reason="token alias requires support",
                    initial_status="candidate",
                )
                if status != "rejected":
                    accepted.append(alias_key)
            elif resolution["state"] == "resolved" and resolution["entity_id"] == entity_id:
                status = self.add_alias(
                    entity_id,
                    alias_key,
                    chapter_idx,
                    f"Confirmed derived short form: {signature['canonical_name']}",
                    confidence=0.65,
                    validation_status="derived_short_form",
                    validation_reason="unique resolver owner",
                    initial_status="candidate",
                )
                if status != "rejected":
                    accepted.append(alias_key)
            else:
                self.record_conflict(
                    "alias_ambiguity",
                    chapter_idx,
                    {
                        "alias": alias_key,
                        "entity_id": entity_id,
                        "canonical_name": signature["canonical_name"],
                        "resolution_state": resolution["state"],
                        "candidates": resolution.get("candidates", [])[:5],
                    },
                    entity_a_id=entity_id,
                    entity_b_id=resolution.get("entity_id"),
                )
        return accepted

    def update_entity_verification(self, entity_id: int, chapter_idx: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE entities
                SET last_verified_chapter = ?,
                    mention_count = mention_count + 1,
                    confidence = MIN(1.0, confidence + ?),
                    importance_score = MIN(1.0, importance_score + 0.03),
                    visibility_score = MIN(1.0, visibility_score + 0.03)
                WHERE id = ?
            """, (chapter_idx, ENTITY_SUPPORT_CONFIDENCE_BOOST, entity_id))

    def register_entity_type_vote(self, entity_id: int, entity_type: str, chapter_idx: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entity_type FROM entities WHERE id = ?", (entity_id,))
            current = cursor.fetchone()
            if current and current[0] != entity_type:
                self.record_conflict(
                    "entity_type_collision",
                    chapter_idx,
                    {"current_type": current[0], "proposed_type": entity_type},
                    entity_a_id=entity_id,
                )
            cursor.execute("""
                INSERT INTO entity_type_votes (
                    entity_id, entity_type, support_count, confidence, first_seen, last_seen
                )
                VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(entity_id, entity_type) DO UPDATE SET
                    support_count = support_count + 1,
                    confidence = MIN(1.0, confidence + ?),
                    last_seen = excluded.last_seen
            """, (
                entity_id,
                entity_type,
                ENTITY_BASE_CONFIDENCE,
                chapter_idx,
                chapter_idx,
                ENTITY_SUPPORT_CONFIDENCE_BOOST,
            ))

            cursor.execute("""
                SELECT entity_type, support_count, confidence
                FROM entity_type_votes
                WHERE entity_id = ?
                ORDER BY support_count DESC, confidence DESC
                LIMIT 1
            """, (entity_id,))
            best_type, support_count, confidence = cursor.fetchone()
            if support_count >= ENTITY_TYPE_CHANGE_SUPPORT and confidence >= ENTITY_TYPE_CHANGE_CONFIDENCE:
                conn.execute("""
                    UPDATE entities
                    SET entity_type = ?, type_support_count = ?, confidence = MAX(confidence, ?)
                    WHERE id = ?
                """, (best_type, support_count, confidence, entity_id))

    def add_mention_occurrence(
        self,
        surface_form: str,
        chapter_idx: int,
        sentence_offset: int | None = None,
        paragraph_offset: int | None = None,
        speaker: str | None = None,
        addressee: str | None = None,
        entity_type_guess: str | None = None,
        confidence: float = 0.5,
        source_quote: str = "",
        linked_entity_id: int | None = None,
        narrator_entity_id: int | None = None,
        scene_scope: str | None = None,
        mention_source_type: str = "narration",
        source_section_type: str = "CHAPTER",
    ) -> int | None:
        surface_form = " ".join(str(surface_form or "").split())
        normalized_form = self.normalize_alias_key(surface_form)
        if not surface_form or not normalized_form:
            return None
        classification = self.classify_mention_surface(surface_form, entity_type_guess)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mention_occurrences (
                    surface_form, normalized_form, chapter, sentence_offset,
                    paragraph_offset, speaker, addressee, mention_class,
                    title_category, narrator_entity_id, scene_scope,
                    entity_type_guess, confidence, source_quote, linked_entity_id,
                    mention_source_type, source_section_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                surface_form,
                normalized_form,
                chapter_idx,
                sentence_offset,
                paragraph_offset,
                speaker,
                addressee,
                classification["mention_class"],
                classification["title_category"],
                narrator_entity_id,
                scene_scope,
                entity_type_guess,
                confidence,
                source_quote,
                linked_entity_id,
                mention_source_type,
                source_section_type,
            ))
            return cursor.lastrowid

    def add_title_link(
        self,
        entity_id: int,
        title_text: str,
        chapter_idx: int,
        evidence: str,
        confidence: float = 0.55,
        status: str = "candidate",
    ) -> str:
        title_text = " ".join(str(title_text or "").split())
        title_key = self.normalize_alias_key(title_text)
        if not title_key:
            return "rejected"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO title_links (
                    entity_id, title_text, title_key, chapter_found, evidence,
                    confidence, support_count, first_seen, last_seen, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(entity_id, title_key) DO UPDATE SET
                    title_text = excluded.title_text,
                    evidence = excluded.evidence,
                    confidence = MIN(1.0, title_links.confidence + ?),
                    support_count = title_links.support_count + 1,
                    last_seen = excluded.last_seen
            """, (
                entity_id,
                title_text,
                title_key,
                chapter_idx,
                evidence,
                confidence,
                chapter_idx,
                chapter_idx,
                status,
                ALIAS_SUPPORT_CONFIDENCE_BOOST,
            ))
            cursor.execute(
                "SELECT support_count, confidence FROM title_links WHERE entity_id = ? AND title_key = ?",
                (entity_id, title_key),
            )
            support_count, title_confidence = cursor.fetchone()
            if support_count >= ALIAS_ACCEPTED_SUPPORT:
                next_status = "accepted"
            elif support_count >= 2 or title_confidence >= ALIAS_ACCEPTED_CONFIDENCE:
                next_status = "probable"
            else:
                next_status = status
            conn.execute(
                "UPDATE title_links SET status = ? WHERE entity_id = ? AND title_key = ?",
                (next_status, entity_id, title_key),
            )
            self._mark_entity_search_dirty(conn, entity_id)
            return next_status

    def record_identity_promotion(
        self,
        placeholder_entity_id: int | None,
        resolved_entity_id: int,
        chapter_idx: int,
        evidence: str,
        confidence: float = 0.75,
        status: str = "candidate",
    ) -> int | None:
        if not resolved_entity_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO identity_promotions (
                    placeholder_entity_id, resolved_entity_id, chapter, evidence,
                    confidence, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(placeholder_entity_id, resolved_entity_id) DO UPDATE SET
                    chapter = excluded.chapter,
                    evidence = excluded.evidence,
                    confidence = MAX(identity_promotions.confidence, excluded.confidence),
                    status = excluded.status
            """, (
                placeholder_entity_id,
                resolved_entity_id,
                chapter_idx,
                evidence,
                confidence,
                status,
            ))
            cursor.execute("""
                SELECT id
                FROM identity_promotions
                WHERE placeholder_entity_id IS ? AND resolved_entity_id = ?
            """, (placeholder_entity_id, resolved_entity_id))
            row = cursor.fetchone()
            return row[0] if row else None

    def add_event_cluster_member(self, event_id: int, summary: str, confidence: float = RELATIONSHIP_BASE_CONFIDENCE):
        cluster_key = self.normalize_alias_key(summary)
        if not event_id or not cluster_key:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_clusters (cluster_key, representative_summary, confidence)
                VALUES (?, ?, ?)
                ON CONFLICT(cluster_key) DO UPDATE SET
                    confidence = MAX(event_clusters.confidence, excluded.confidence)
            """, (cluster_key, summary, confidence))
            cursor.execute("SELECT id FROM event_clusters WHERE cluster_key = ?", (cluster_key,))
            cluster_id = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO event_cluster_members (cluster_id, event_id, confidence)
                VALUES (?, ?, ?)
                ON CONFLICT(cluster_id, event_id) DO UPDATE SET
                    confidence = MAX(event_cluster_members.confidence, excluded.confidence)
            """, (cluster_id, event_id, confidence))
            return cluster_id

    def create_event_landmark(
        self,
        *,
        lifecycle: str = "candidate",
        landmark_type: str = "event",
        event_state: str = "unknown",
        reliability: str = "unknown",
        reader_visibility: str = "partially_known",
        geographic_scope: str = "unknown",
        historical_start_text: str = "",
        historical_end_text: str = "",
        historical_start_sort: float | None = None,
        historical_end_sort: float | None = None,
        duration_text: str = "",
        narrative_first_chapter: int | None = None,
        reader_known_since_chapter: int | None = None,
        story_discovery_time_text: str = "",
        story_discovery_confidence: float = 0.0,
        boundary_confidence: float = 0.5,
        identity_confidence: float = 0.5,
        merge_confidence: float = 0.0,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
    ) -> int:
        identity_key = f"lm_{uuid.uuid4().hex}"
        valid_lifecycles = {"candidate", "landmark", "historically_referenced", "legacy_landmark"}
        valid_states = {"planned", "ongoing", "completed", "remembered", "historical", "unknown"}
        valid_reliabilities = {"direct", "reported", "historical", "rumor", "legend", "myth", "unknown"}
        valid_visibility = {"hidden", "partially_known", "fully_known"}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_landmarks (
                    identity_key, lifecycle, landmark_type, event_state,
                    event_reliability, reader_visibility, geographic_scope,
                    historical_start_text, historical_end_text,
                    historical_start_sort, historical_end_sort, duration_text,
                    narrative_first_chapter, reader_known_since_chapter,
                    story_discovery_time_text, story_discovery_confidence,
                    boundary_confidence, identity_confidence, merge_confidence,
                    source_session, inherited_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                identity_key,
                lifecycle if lifecycle in valid_lifecycles else "candidate",
                landmark_type or "event",
                event_state if event_state in valid_states else "unknown",
                reliability if reliability in valid_reliabilities else "unknown",
                reader_visibility if reader_visibility in valid_visibility else "partially_known",
                geographic_scope or "unknown",
                historical_start_text or None,
                historical_end_text or None,
                historical_start_sort,
                historical_end_sort,
                duration_text or None,
                narrative_first_chapter,
                reader_known_since_chapter,
                story_discovery_time_text or None,
                max(0.0, min(1.0, float(story_discovery_confidence or 0.0))),
                max(0.0, min(1.0, float(boundary_confidence or 0.0))),
                max(0.0, min(1.0, float(identity_confidence or 0.0))),
                max(0.0, min(1.0, float(merge_confidence or 0.0))),
                source_session,
                max(0.0, min(1.0, float(inherited_confidence or 0.0))),
            ))
            return int(cursor.lastrowid)

    def get_landmark_id_by_identity(self, identity_key: str | None) -> int | None:
        if not identity_key:
            return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM event_landmarks WHERE identity_key = ?",
                (str(identity_key).strip(),),
            ).fetchone()
            return int(row[0]) if row else None

    def find_landmarks_by_reference(self, reference: str) -> list[int]:
        reference_key = self.normalize_alias_key(reference)
        if not reference_key:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM event_landmarks WHERE identity_key = ?
                UNION
                SELECT landmark_id FROM landmark_names
                WHERE name_key = ? AND COALESCE(status, 'accepted') != 'rejected'
            """, (str(reference).strip(), reference_key))
            return sorted({int(row[0]) for row in cursor.fetchall()})

    def find_latest_event_for_landmark_reference(self, reference: str) -> int | None:
        landmark_ids = self.find_landmarks_by_reference(reference)
        if len(landmark_ids) != 1:
            return None
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT event_id
                FROM landmark_event_links
                WHERE landmark_id = ?
                ORDER BY event_id DESC
                LIMIT 1
            """, (landmark_ids[0],)).fetchone()
            return int(row[0]) if row else None

    def find_structural_landmark_candidates(self, record: dict) -> list[tuple[int, float]]:
        landmark_type = str(record.get("landmark_type") or "event").strip()
        geographic_scope = str(record.get("geographic_scope") or record.get("event_scope") or "unknown").strip()
        historical_start = self.normalize_alias_key(record.get("historical_start_text") or "")
        historical_end = self.normalize_alias_key(record.get("historical_end_text") or "")
        event_state = str(record.get("event_state") or "unknown").strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, landmark_type, geographic_scope,
                       historical_start_text, historical_end_text, event_state
                FROM event_landmarks
                WHERE lifecycle != 'candidate'
                ORDER BY COALESCE(identity_confidence, 0.0) DESC, id DESC
                LIMIT 100
            """)
            candidates = []
            for landmark_id, candidate_type, candidate_scope, start_text, end_text, candidate_state in cursor.fetchall():
                score = 0.0
                if landmark_type and landmark_type == candidate_type:
                    score += 0.20
                if geographic_scope and geographic_scope != "unknown" and geographic_scope == candidate_scope:
                    score += 0.20
                if historical_start and historical_start == self.normalize_alias_key(start_text or ""):
                    score += 0.35
                if historical_end and historical_end == self.normalize_alias_key(end_text or ""):
                    score += 0.15
                if event_state and event_state != "unknown" and event_state == candidate_state:
                    score += 0.10
                if score >= 0.35:
                    candidates.append((int(landmark_id), round(score, 3)))
            return sorted(candidates, key=lambda item: item[1], reverse=True)

    def add_landmark_name(
        self,
        landmark_id: int | None,
        name_text: str,
        *,
        name_role: str = "public",
        name_source_type: str = "unknown",
        audience_type: str = "reader",
        source_entity_id: int | None = None,
        faction_entity_id: int | None = None,
        source_entity_text: str = "",
        faction_text: str = "",
        framing_polarity: str = "neutral",
        literal_status: str = "literal",
        first_known_chapter: int | None = None,
        narrative_order: int | None = None,
        confidence: float = 0.5,
        evidence: str = "",
        status: str = "accepted",
    ) -> int | None:
        name_text = " ".join(str(name_text or "").split())
        name_key = self.normalize_alias_key(name_text)
        if not landmark_id or not name_key:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM landmark_names
                WHERE landmark_id = ? AND name_key = ? AND name_role = ?
                  AND audience_type = ? AND COALESCE(source_entity_id, -1) = COALESCE(?, -1)
                  AND COALESCE(faction_entity_id, -1) = COALESCE(?, -1)
                ORDER BY id LIMIT 1
            """, (landmark_id, name_key, name_role, audience_type, source_entity_id, faction_entity_id))
            row = cursor.fetchone()
            if row:
                name_id = int(row[0])
                conn.execute("""
                    UPDATE landmark_names
                    SET confidence = MAX(confidence, ?),
                        evidence = COALESCE(NULLIF(?, ''), evidence),
                        first_known_chapter = COALESCE(first_known_chapter, ?),
                        narrative_order = COALESCE(narrative_order, ?),
                        status = CASE WHEN status = 'rejected' THEN status ELSE ? END
                    WHERE id = ?
                """, (max(0.0, min(1.0, float(confidence or 0.0))), evidence, first_known_chapter, narrative_order, status, name_id))
            else:
                cursor.execute("""
                    INSERT INTO landmark_names (
                        landmark_id, name_text, name_key, name_role, name_source_type,
                        audience_type, source_entity_id, faction_entity_id, framing_polarity,
                        source_entity_text, faction_text, literal_status, first_known_chapter, narrative_order, confidence,
                        evidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    landmark_id, name_text, name_key, name_role or "public", name_source_type or "unknown",
                    audience_type or "reader", source_entity_id, faction_entity_id, framing_polarity or "neutral",
                    source_entity_text or None, faction_text or None, literal_status or "literal", first_known_chapter, narrative_order,
                    max(0.0, min(1.0, float(confidence or 0.0))), evidence or None, status or "accepted",
                ))
                name_id = int(cursor.lastrowid)

            if name_role in {"canonical", "public", "historical", "reader"} and framing_polarity == "neutral" and literal_status == "literal":
                conn.execute("""
                    UPDATE event_landmarks
                    SET preferred_name_id = COALESCE(preferred_name_id, ?),
                        lifecycle = CASE WHEN lifecycle = 'candidate' THEN 'landmark' ELSE lifecycle END
                    WHERE id = ?
                """, (name_id, landmark_id))
            return name_id

    def add_alias(
        self,
        entity_id: int,
        alias_name: str,
        chapter_idx: int,
        evidence: str,
        confidence: float | None = None,
        validation_status: str | None = None,
        validation_reason: str | None = None,
        initial_status: str = "candidate",
    ):
        confidence = ALIAS_BASE_CONFIDENCE if confidence is None else confidence
        alias_key = self.normalize_alias_key(alias_name)
        if not alias_key:
            return "rejected"
        if initial_status not in {"candidate", "probable", "accepted", "review", "rejected"}:
            initial_status = "candidate"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO aliases (
                    alias_name, alias_key, entity_id, chapter_found, evidence, confidence,
                    support_count, first_seen, last_seen, status, validation_status,
                    validation_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id, alias_key) DO UPDATE SET
                    alias_name = CASE
                        WHEN LENGTH(excluded.alias_name) > LENGTH(aliases.alias_name)
                        THEN excluded.alias_name
                        ELSE aliases.alias_name
                    END,
                    evidence = excluded.evidence,
                    confidence = MIN(1.0, aliases.confidence + ?),
                    support_count = aliases.support_count + 1,
                    last_seen = excluded.last_seen,
                    validation_status = excluded.validation_status,
                    validation_reason = excluded.validation_reason
            """, (
                alias_name,
                alias_key,
                entity_id,
                chapter_idx,
                evidence,
                confidence,
                chapter_idx,
                chapter_idx,
                initial_status,
                validation_status,
                validation_reason,
                ALIAS_SUPPORT_CONFIDENCE_BOOST,
            ))

            cursor.execute("""
                SELECT support_count, confidence
                FROM aliases
                WHERE entity_id = ? AND alias_key = ?
            """, (entity_id, alias_key))
            support_count, alias_confidence = cursor.fetchone()
            if initial_status in {"review", "rejected"}:
                status = initial_status
            elif support_count >= ALIAS_ACCEPTED_SUPPORT:
                status = "accepted"
            elif support_count >= 2 or alias_confidence >= ALIAS_ACCEPTED_CONFIDENCE:
                status = "probable"
            else:
                status = "candidate"

            conn.execute("""
                UPDATE aliases
                SET status = ?
                WHERE entity_id = ? AND alias_key = ?
            """, (status, entity_id, alias_key))
            self._mark_entity_search_dirty(conn, entity_id)
            return status

    def link_event_to_landmark(
        self,
        landmark_id: int | None,
        event_id: int | None,
        *,
        link_type: str = "occurrence",
        confidence: float = 0.5,
        evidence: str = "",
        recurring_template_reference: str = "",
    ) -> None:
        if not landmark_id or not event_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_event_links (landmark_id, event_id, link_type, confidence, evidence)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(landmark_id, event_id, link_type) DO UPDATE SET
                    confidence = MAX(landmark_event_links.confidence, excluded.confidence),
                    evidence = COALESCE(NULLIF(excluded.evidence, ''), landmark_event_links.evidence)
            """, (landmark_id, event_id, link_type or "occurrence", max(0.0, min(1.0, float(confidence or 0.0))), evidence or None))
            conn.execute("UPDATE events SET landmark_id = COALESCE(landmark_id, ?) WHERE id = ?", (landmark_id, event_id))
            if link_type == "recurrence_instance":
                conn.execute("UPDATE events SET recurring_template_id = ? WHERE id = ?", (landmark_id, event_id))
            if recurring_template_reference:
                reference_key = self.normalize_alias_key(recurring_template_reference)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM event_landmarks WHERE identity_key = ?
                    UNION
                    SELECT landmark_id FROM landmark_names
                    WHERE name_key = ? AND COALESCE(status, 'accepted') != 'rejected'
                """, (recurring_template_reference, reference_key))
                template_ids = {int(row[0]) for row in cursor.fetchall()}
                if len(template_ids) == 1:
                    conn.execute("UPDATE events SET recurring_template_id = ? WHERE id = ?", (template_ids.pop(), event_id))

    def add_landmark_hierarchy(
        self,
        parent_landmark_id: int | None,
        child_landmark_id: int | None,
        *,
        relation_type: str = "contains",
        confidence: float = 0.5,
        evidence: str = "",
    ) -> None:
        if not parent_landmark_id or not child_landmark_id or parent_landmark_id == child_landmark_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_hierarchy (parent_landmark_id, child_landmark_id, relation_type, confidence, evidence)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(parent_landmark_id, child_landmark_id, relation_type) DO UPDATE SET
                    confidence = MAX(landmark_hierarchy.confidence, excluded.confidence),
                    evidence = COALESCE(NULLIF(excluded.evidence, ''), landmark_hierarchy.evidence)
            """, (parent_landmark_id, child_landmark_id, relation_type or "contains", max(0.0, min(1.0, float(confidence or 0.0))), evidence or None))

    def add_landmark_perspective(
        self, landmark_id: int | None, summary: str, *, perspective_type: str = "neutral",
        source_entity_id: int | None = None, faction_entity_id: int | None = None,
        source_entity_text: str = "", faction_text: str = "",
        chapter: int | None = None, reader_visibility: str = "partially_known",
        reliability: str = "unknown", confidence: float = 0.5, evidence: str = "",
    ) -> None:
        summary = " ".join(str(summary or "").split())
        if not landmark_id or not summary:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_perspectives (
                    landmark_id, perspective_type, summary, source_entity_id, faction_entity_id,
                    source_entity_text, faction_text, chapter, reader_visibility, reliability, confidence, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                landmark_id, perspective_type or "neutral", summary, source_entity_id, faction_entity_id,
                source_entity_text or None, faction_text or None, chapter, reader_visibility or "partially_known", reliability or "unknown",
                max(0.0, min(1.0, float(confidence or 0.0))), evidence or None,
            ))

    def add_landmark_importance(
        self, landmark_id: int | None, dimension: str, score: float, *,
        chapter: int | None = None, confidence: float = 0.5, evidence: str = "",
    ) -> None:
        allowed = {"political", "social", "personal", "military", "religious", "scientific", "historical"}
        if not landmark_id or dimension not in allowed:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_importance (landmark_id, dimension, score, chapter, confidence, evidence)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(landmark_id, dimension, chapter) DO UPDATE SET
                    score = MAX(landmark_importance.score, excluded.score),
                    confidence = MAX(landmark_importance.confidence, excluded.confidence),
                    evidence = COALESCE(NULLIF(excluded.evidence, ''), landmark_importance.evidence)
            """, (landmark_id, dimension, max(0.0, min(1.0, float(score or 0.0))), chapter, max(0.0, min(1.0, float(confidence or 0.0))), evidence or None))

    def add_landmark_location(
        self, landmark_id: int | None, location_entity_id: int | None, *,
        location_role: str = "secondary", confidence: float = 0.5, evidence: str = "",
    ) -> None:
        if not landmark_id or not location_entity_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_locations (landmark_id, location_entity_id, location_role, confidence, evidence)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(landmark_id, location_entity_id, location_role) DO UPDATE SET
                    confidence = MAX(landmark_locations.confidence, excluded.confidence),
                    evidence = COALESCE(NULLIF(excluded.evidence, ''), landmark_locations.evidence)
            """, (landmark_id, location_entity_id, location_role or "secondary", max(0.0, min(1.0, float(confidence or 0.0))), evidence or None))

    def add_landmark_participant(
        self, landmark_id: int | None, entity_id: int | None, *, role: str = "participant",
        source_event_id: int | None = None, confidence: float = 0.5, evidence: str = "",
    ) -> None:
        if not landmark_id or not entity_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_participants (landmark_id, entity_id, role, source_event_id, confidence, evidence)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(landmark_id, entity_id, role, source_event_id) DO UPDATE SET
                    confidence = MAX(landmark_participants.confidence, excluded.confidence),
                    evidence = COALESCE(NULLIF(excluded.evidence, ''), landmark_participants.evidence)
            """, (landmark_id, entity_id, role or "participant", source_event_id, max(0.0, min(1.0, float(confidence or 0.0))), evidence or None))

    def add_landmark_assertion(
        self, landmark_id: int | None, assertion_type: str, assertion_value: str, *,
        chapter: int | None = None, story_time_text: str = "", story_time_sort: float | None = None,
        source_event_id: int | None = None, source_entity_id: int | None = None,
        confidence: float = 0.5, evidence: str = "",
    ) -> None:
        allowed = {"state", "reliability", "visibility", "outcome", "historical_memory", "function"}
        if not landmark_id or assertion_type not in allowed or not assertion_value:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO landmark_assertions (
                    landmark_id, assertion_type, assertion_value, chapter, story_time_text,
                    story_time_sort, source_event_id, source_entity_id, confidence, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                landmark_id, assertion_type, assertion_value, chapter, story_time_text or None, story_time_sort,
                source_event_id, source_entity_id, max(0.0, min(1.0, float(confidence or 0.0))), evidence or None,
            ))
            snapshot_column = {"state": "event_state", "reliability": "event_reliability", "visibility": "reader_visibility"}.get(assertion_type)
            if snapshot_column:
                conn.execute(f"UPDATE event_landmarks SET {snapshot_column} = ? WHERE id = ?", (assertion_value, landmark_id))

    def record_landmark_resolution_evidence(
        self, event_id: int | None, landmark_id: int | None, chapter: int, *, decision: str,
        identity_confidence: float = 0.0, merge_confidence: float = 0.0,
        supporting_evidence: str = "", contradicting_evidence: str = "", signals: dict | None = None,
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO landmark_resolution_evidence (
                    event_id, landmark_id, chapter, decision, identity_confidence, merge_confidence,
                    supporting_evidence, contradicting_evidence, signals
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id, landmark_id, chapter, decision, max(0.0, min(1.0, float(identity_confidence or 0.0))),
                max(0.0, min(1.0, float(merge_confidence or 0.0))), supporting_evidence or None,
                contradicting_evidence or None, json.dumps(signals or {}, ensure_ascii=False, sort_keys=True),
            ))
            evidence_id = cursor.lastrowid
            self.record_resolver_decision(
                "landmarks",
                "landmark" if landmark_id else "event",
                landmark_id if landmark_id else (event_id or "unresolved"),
                chapter,
                decision,
                confidence=identity_confidence,
                supporting_evidence=[{"table": "landmark_resolution_evidence", "id": evidence_id}],
                contradicting_evidence=[contradicting_evidence] if contradicting_evidence else [],
                rejected_alternatives=(signals or {}).get("candidates", []),
                metadata={"event_id": event_id, "signals": signals or {}},
                conn=conn,
            )

    def get_landmark_explanation(self, landmark_id: int | None) -> dict:
        if not landmark_id:
            return {"landmark": None, "names": [], "evidence": [], "contradictions": []}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT identity_key, lifecycle, landmark_type, event_state, event_reliability,
                       reader_visibility, identity_confidence, merge_confidence
                FROM event_landmarks WHERE id = ?
            """, (landmark_id,))
            landmark = cursor.fetchone()
            cursor.execute("""
                SELECT name_text, name_role, name_source_type, audience_type, framing_polarity,
                       literal_status, confidence, evidence, status
                FROM landmark_names WHERE landmark_id = ? ORDER BY id
            """, (landmark_id,))
            names = cursor.fetchall()
            cursor.execute("""
                SELECT decision, identity_confidence, merge_confidence, supporting_evidence,
                       contradicting_evidence, signals
                FROM landmark_resolution_evidence WHERE landmark_id = ? ORDER BY id
            """, (landmark_id,))
            evidence_rows = cursor.fetchall()
        return {
            "landmark": landmark, "names": names,
            "evidence": [row for row in evidence_rows if row[3]],
            "contradictions": [row for row in evidence_rows if row[4]],
        }

    def update_event_landmark_metadata(self, event_id: int | None, landmark_id: int | None, record: dict) -> None:
        if not event_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE events
                SET landmark_id = COALESCE(?, landmark_id),
                    occurrence_role = COALESCE(NULLIF(?, ''), occurrence_role),
                    historical_start_text = COALESCE(NULLIF(?, ''), historical_start_text),
                    historical_end_text = COALESCE(NULLIF(?, ''), historical_end_text),
                    historical_start_sort = COALESCE(?, historical_start_sort),
                    historical_end_sort = COALESCE(?, historical_end_sort),
                    duration_text = COALESCE(NULLIF(?, ''), duration_text),
                    reader_known_since_chapter = COALESCE(?, reader_known_since_chapter)
                WHERE id = ?
            """, (
                landmark_id,
                str(record.get("landmark_link_type") or "occurrence"),
                str(record.get("historical_start_text") or ""),
                str(record.get("historical_end_text") or ""),
                record.get("historical_start_sort"),
                record.get("historical_end_sort"),
                str(record.get("duration_text") or ""),
                record.get("reader_known_since_chapter"),
                event_id,
            ))
            self._sync_event_search_terms(conn, event_id)

    def refresh_event_search_terms(self, event_id: int | None) -> None:
        if not event_id:
            return
        with self._get_connection() as conn:
            self._sync_event_search_terms(conn, event_id)

    def add_event(
        self,
        chapter: int,
        summary: str,
        event_order: int,
        event_type: str = "plot",
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        source_payload: dict | None = None,
        event_identity_key: str | None = None,
        observed_by_entity_id: int | None = None,
        narrator_entity_id: int | None = None,
        narrator_scope: str | None = None,
        scene_scope: str | None = None,
        evidence_source_type: str = "observed_fact",
        actuality_status: str = "actual",
        narrative_order: int | None = None,
        story_time_text: str | None = None,
        story_time_confidence: float = 0.0,
        source_section_type: str = "CHAPTER",
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
    ) -> int | None:
        summary = " ".join(str(summary or "").strip().split())
        if not summary:
            return None
        normalized_summary = self.normalize_alias_key(summary)
        if not normalized_summary:
            return None
        event_identity_key = event_identity_key or normalized_summary
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (
                    chapter, event_order, summary, normalized_summary,
                    event_type, event_identity_key, observed_by_entity_id,
                    narrator_entity_id, narrator_scope, scene_scope,
                    evidence_source_type, actuality_status, narrative_order,
                    story_time_text, story_time_confidence, source_section_type,
                    boundary_title_id, boundary_book_id, boundary_volume_id,
                    session_id, source_session, inherited_confidence,
                    confidence, source_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter, normalized_summary) DO UPDATE SET
                    summary = excluded.summary,
                    event_identity_key = COALESCE(excluded.event_identity_key, events.event_identity_key),
                    observed_by_entity_id = COALESCE(excluded.observed_by_entity_id, events.observed_by_entity_id),
                    narrator_entity_id = COALESCE(excluded.narrator_entity_id, events.narrator_entity_id),
                    narrator_scope = COALESCE(excluded.narrator_scope, events.narrator_scope),
                    scene_scope = COALESCE(excluded.scene_scope, events.scene_scope),
                    evidence_source_type = COALESCE(excluded.evidence_source_type, events.evidence_source_type),
                    actuality_status = COALESCE(excluded.actuality_status, events.actuality_status),
                    narrative_order = COALESCE(excluded.narrative_order, events.narrative_order),
                    story_time_text = COALESCE(excluded.story_time_text, events.story_time_text),
                    story_time_confidence = MAX(events.story_time_confidence, excluded.story_time_confidence),
                    source_section_type = COALESCE(excluded.source_section_type, events.source_section_type),
                    boundary_title_id = COALESCE(excluded.boundary_title_id, events.boundary_title_id),
                    boundary_book_id = COALESCE(excluded.boundary_book_id, events.boundary_book_id),
                    boundary_volume_id = COALESCE(excluded.boundary_volume_id, events.boundary_volume_id),
                    session_id = COALESCE(excluded.session_id, events.session_id),
                    source_session = COALESCE(excluded.source_session, events.source_session),
                    inherited_confidence = MAX(events.inherited_confidence, excluded.inherited_confidence),
                    confidence = MAX(events.confidence, excluded.confidence),
                    source_payload = COALESCE(excluded.source_payload, events.source_payload)
            """, (
                chapter,
                event_order,
                summary,
                normalized_summary,
                event_type,
                event_identity_key,
                observed_by_entity_id,
                narrator_entity_id,
                narrator_scope,
                scene_scope,
                evidence_source_type,
                actuality_status,
                narrative_order if narrative_order is not None else event_order,
                story_time_text,
                story_time_confidence,
                source_section_type,
                boundary_title_id,
                boundary_book_id or boundary_title_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence,
                confidence,
                json.dumps(source_payload, ensure_ascii=False) if source_payload else None,
            ))
            cursor.execute(
                "SELECT id FROM events WHERE chapter = ? AND normalized_summary = ?",
                (chapter, normalized_summary),
            )
            row = cursor.fetchone()
            event_id = row[0] if row else None
            if event_id:
                self._sync_event_search_terms(conn, event_id)
            return event_id

    def add_event_participant(
        self,
        event_id: int | None,
        entity_id: int | None,
        role: str = "participant",
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        observed_by_entity_id: int | None = None,
        scene_scope: str | None = None,
    ):
        if not event_id or not entity_id:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM entities WHERE id = ?", (entity_id,))
            if not cursor.fetchone() or not self.entity_can_participate_in_events(entity_id, cursor):
                return
            conn.execute("""
                INSERT INTO event_participants (
                    event_id, entity_id, role, confidence,
                    observed_by_entity_id, scene_scope
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, entity_id, role) DO UPDATE SET
                    confidence = MAX(event_participants.confidence, excluded.confidence),
                    observed_by_entity_id = COALESCE(excluded.observed_by_entity_id, event_participants.observed_by_entity_id),
                    scene_scope = COALESCE(excluded.scene_scope, event_participants.scene_scope)
            """, (event_id, entity_id, role, confidence, observed_by_entity_id, scene_scope))
            self._sync_event_search_terms(conn, event_id)

    def _social_edge_pair(self, source_id: int, target_id: int, directional: bool = False) -> tuple[int, int] | None:
        if not source_id or not target_id or source_id == target_id:
            return None
        source_id = int(source_id)
        target_id = int(target_id)
        if not directional and source_id > target_id:
            return target_id, source_id
        return source_id, target_id

    def _social_edge_key(
        self,
        source_id: int,
        target_id: int,
        edge_layer: str = "cooccurrence",
        edge_subtype: str = "general",
        directional: bool = False,
    ) -> str | None:
        pair = self._social_edge_pair(source_id, target_id, directional)
        if not pair:
            return None
        src, tgt = pair
        connector = "->" if directional else "--"
        layer = self.normalize_alias_key(edge_layer) or "cooccurrence"
        subtype = self.normalize_alias_key(edge_subtype) or "general"
        return f"{layer}:{subtype}:{src}{connector}{tgt}"

    def _infer_social_layer(self, cursor, source_id: int, target_id: int, default_layer: str) -> tuple[str, str]:
        cursor.execute("SELECT id, entity_type FROM entities WHERE id IN (?, ?)", (source_id, target_id))
        types = {entity_id: entity_type for entity_id, entity_type in cursor.fetchall()}
        if len(types) != 2:
            return default_layer, "general"
        source_type = types.get(source_id)
        target_type = types.get(target_id)
        if not (
            self.entity_can_form_social_edges(source_id, cursor)
            and self.entity_can_form_social_edges(target_id, cursor)
        ):
            return "", ""
        if "GROUP" in {source_type, target_type}:
            if source_type == "GROUP" and target_type == "GROUP":
                return "group_proximity", "group_to_group"
            return "group_proximity", "individual_to_group"
        return default_layer, "general"

    def _promotion_state_for_social_edge(
        self,
        edge_layer: str,
        support_count: int,
        shared_event_count: int,
        chapter_overlap_count: int,
        confidence: float,
    ) -> str:
        if edge_layer == "direct_relationship":
            return "confirmed"
        if support_count >= 5 or shared_event_count >= 3 or (chapter_overlap_count >= 3 and confidence >= 0.45):
            return "stable"
        if support_count >= 2 or shared_event_count >= 1 or confidence >= 0.45:
            return "inferred"
        return "weak"

    def _refresh_social_edge_state(self, conn, edge_key: str):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT edge_layer, COALESCE(support_count, 0),
                   COALESCE(shared_event_count, 0),
                   COALESCE(chapter_overlap_count, 0),
                   COALESCE(confidence, 0.0)
            FROM relationship_social_edges
            WHERE edge_key = ?
        """, (edge_key,))
        row = cursor.fetchone()
        if not row:
            return
        edge_layer, support_count, shared_event_count, chapter_overlap_count, confidence = row
        promotion_state = self._promotion_state_for_social_edge(
            edge_layer or "cooccurrence",
            int(support_count or 0),
            int(shared_event_count or 0),
            int(chapter_overlap_count or 0),
            float(confidence or 0.0),
        )
        conn.execute("""
            UPDATE relationship_social_edges
            SET promotion_state = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE edge_key = ?
        """, (promotion_state, edge_key))

    def _record_social_edge_evidence_conn(
        self,
        conn,
        source_id: int | None,
        target_id: int | None,
        chapter: int | None,
        edge_layer: str = "cooccurrence",
        edge_subtype: str = "general",
        directional: bool = False,
        event_id: int | None = None,
        evidence_scope: str | None = None,
        evidence_summary: str | None = None,
        shared_scene_count: int = 0,
        shared_event_count: int = 0,
        chapter_overlap_count: int = 0,
        dialogue_overlap_count: int = 0,
        familiarity_signal: float = 0.0,
        trust_signal: float = 0.0,
        hostility_signal: float = 0.0,
        cooperation_signal: float = 0.0,
        confidence: float = 0.25,
        evidence_source_type: str = "observed_fact",
        actuality_status: str = "actual",
        source_pov_id: int | None = None,
        source_speaker_id: int | None = None,
        scene_scope: str | None = None,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
        evidence_key: str | None = None,
    ) -> str | None:
        pair = self._social_edge_pair(source_id, target_id, directional)
        if not pair:
            return None
        source_id, target_id = pair
        cursor = conn.cursor()
        inferred_layer, inferred_subtype = self._infer_social_layer(cursor, source_id, target_id, edge_layer)
        if not inferred_layer:
            return None
        if edge_layer in {"cooccurrence", "chapter_copresence", "shared_event"} and inferred_layer == "group_proximity":
            edge_layer = inferred_layer
            edge_subtype = inferred_subtype
        edge_layer = self.normalize_alias_key(edge_layer) or "cooccurrence"
        edge_subtype = self.normalize_alias_key(edge_subtype) or "general"
        edge_key = self._social_edge_key(source_id, target_id, edge_layer, edge_subtype, directional)
        if not edge_key:
            return None

        confidence = max(0.01, min(1.0, float(confidence if confidence is not None else 0.25)))
        inherited_confidence = max(0.01, min(1.0, float(inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE)))
        scene_scope = scene_scope or (f"chapter:{chapter}" if chapter is not None else None)
        evidence_scope = evidence_scope or scene_scope or edge_layer
        evidence_summary = " ".join(str(evidence_summary or "").split())[:500]
        evidence_digest = self.normalize_alias_key(evidence_summary)[:120]
        if not evidence_key:
            evidence_key = "|".join(
                str(part or "")
                for part in (
                    edge_key,
                    chapter,
                    event_id,
                    evidence_scope,
                    evidence_digest,
                )
            )

        conn.execute("""
            INSERT INTO relationship_social_edges (
                edge_key, source_id, target_id, edge_layer, edge_subtype,
                directional, evidence_source_type, actuality_status,
                source_pov_id, source_speaker_id, scene_scope,
                first_seen_chapter, last_seen_chapter, last_event_id,
                boundary_title_id, boundary_book_id, boundary_volume_id,
                session_id, source_session, inherited_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_key) DO UPDATE SET
                evidence_source_type = COALESCE(excluded.evidence_source_type, relationship_social_edges.evidence_source_type),
                actuality_status = COALESCE(excluded.actuality_status, relationship_social_edges.actuality_status),
                source_pov_id = COALESCE(excluded.source_pov_id, relationship_social_edges.source_pov_id),
                source_speaker_id = COALESCE(excluded.source_speaker_id, relationship_social_edges.source_speaker_id),
                scene_scope = COALESCE(excluded.scene_scope, relationship_social_edges.scene_scope),
                first_seen_chapter = CASE
                    WHEN relationship_social_edges.first_seen_chapter IS NULL THEN excluded.first_seen_chapter
                    WHEN excluded.first_seen_chapter IS NULL THEN relationship_social_edges.first_seen_chapter
                    ELSE MIN(relationship_social_edges.first_seen_chapter, excluded.first_seen_chapter)
                END,
                last_seen_chapter = CASE
                    WHEN relationship_social_edges.last_seen_chapter IS NULL THEN excluded.last_seen_chapter
                    WHEN excluded.last_seen_chapter IS NULL THEN relationship_social_edges.last_seen_chapter
                    ELSE MAX(relationship_social_edges.last_seen_chapter, excluded.last_seen_chapter)
                END,
                last_event_id = COALESCE(excluded.last_event_id, relationship_social_edges.last_event_id),
                boundary_title_id = COALESCE(excluded.boundary_title_id, relationship_social_edges.boundary_title_id),
                boundary_book_id = COALESCE(excluded.boundary_book_id, relationship_social_edges.boundary_book_id),
                boundary_volume_id = COALESCE(excluded.boundary_volume_id, relationship_social_edges.boundary_volume_id),
                session_id = COALESCE(excluded.session_id, relationship_social_edges.session_id),
                source_session = COALESCE(excluded.source_session, relationship_social_edges.source_session),
                inherited_confidence = MIN(COALESCE(relationship_social_edges.inherited_confidence, 1.0), excluded.inherited_confidence)
        """, (
            edge_key,
            source_id,
            target_id,
            edge_layer,
            edge_subtype,
            1 if directional else 0,
            evidence_source_type or "observed_fact",
            actuality_status or "actual",
            source_pov_id,
            source_speaker_id,
            scene_scope,
            chapter,
            chapter,
            event_id,
            boundary_title_id,
            boundary_book_id or boundary_title_id,
            boundary_volume_id,
            session_id,
            source_session,
            inherited_confidence,
        ))

        cursor.execute("""
            INSERT OR IGNORE INTO relationship_social_evidence (
                edge_key, evidence_key, source_id, target_id, edge_layer,
                edge_subtype, directional, chapter, event_id, evidence_scope,
                evidence_summary, shared_scene_count, shared_event_count,
                chapter_overlap_count, dialogue_overlap_count,
                familiarity_signal, trust_signal, hostility_signal,
                cooperation_signal, confidence, evidence_source_type,
                actuality_status, source_pov_id, source_speaker_id,
                scene_scope, boundary_title_id, boundary_book_id,
                boundary_volume_id, session_id, source_session,
                inherited_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            edge_key,
            evidence_key,
            source_id,
            target_id,
            edge_layer,
            edge_subtype,
            1 if directional else 0,
            chapter,
            event_id,
            evidence_scope,
            evidence_summary,
            int(shared_scene_count or 0),
            int(shared_event_count or 0),
            int(chapter_overlap_count or 0),
            int(dialogue_overlap_count or 0),
            float(familiarity_signal or 0.0),
            float(trust_signal or 0.0),
            float(hostility_signal or 0.0),
            float(cooperation_signal or 0.0),
            confidence,
            evidence_source_type or "observed_fact",
            actuality_status or "actual",
            source_pov_id,
            source_speaker_id,
            scene_scope,
            boundary_title_id,
            boundary_book_id or boundary_title_id,
            boundary_volume_id,
            session_id,
            source_session,
            inherited_confidence,
        ))
        if cursor.rowcount <= 0:
            return edge_key

        conn.execute("""
            UPDATE relationship_social_edges
            SET support_count = COALESCE(support_count, 0) + 1,
                shared_scene_count = COALESCE(shared_scene_count, 0) + ?,
                shared_event_count = COALESCE(shared_event_count, 0) + ?,
                chapter_overlap_count = COALESCE(chapter_overlap_count, 0) + ?,
                dialogue_overlap_count = COALESCE(dialogue_overlap_count, 0) + ?,
                familiarity_signal = COALESCE(familiarity_signal, 0.0) + ?,
                trust_signal = COALESCE(trust_signal, 0.0) + ?,
                hostility_signal = COALESCE(hostility_signal, 0.0) + ?,
                cooperation_signal = COALESCE(cooperation_signal, 0.0) + ?,
                confidence = MAX(COALESCE(confidence, 0.0), ?),
                evidence_summary = COALESCE(NULLIF(?, ''), evidence_summary),
                last_seen_chapter = CASE
                    WHEN last_seen_chapter IS NULL THEN ?
                    WHEN ? IS NULL THEN last_seen_chapter
                    ELSE MAX(last_seen_chapter, ?)
                END,
                last_event_id = COALESCE(?, last_event_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE edge_key = ?
        """, (
            int(shared_scene_count or 0),
            int(shared_event_count or 0),
            int(chapter_overlap_count or 0),
            int(dialogue_overlap_count or 0),
            float(familiarity_signal or 0.0),
            float(trust_signal or 0.0),
            float(hostility_signal or 0.0),
            float(cooperation_signal or 0.0),
            confidence,
            evidence_summary,
            chapter,
            chapter,
            chapter,
            event_id,
            edge_key,
        ))
        self._refresh_social_edge_state(conn, edge_key)
        return edge_key

    def record_social_edge_evidence(self, *args, **kwargs) -> str | None:
        with self._get_connection() as conn:
            return self._record_social_edge_evidence_conn(conn, *args, **kwargs)

    def record_chapter_social_context(
        self,
        entity_ids: list[int],
        chapter: int,
        source_pov_id: int | None = None,
        scene_scope: str | None = None,
        evidence_source_type: str = "observed_fact",
        actuality_status: str = "actual",
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
        max_entities: int = 60,
    ) -> int:
        unique_ids = []
        seen = set()
        for entity_id in entity_ids or []:
            if entity_id and entity_id not in seen:
                seen.add(entity_id)
                unique_ids.append(entity_id)
        if len(unique_ids) < 2:
            return 0
        unique_ids = unique_ids[:max_entities]
        inserted = 0
        with self._get_connection() as conn:
            for idx, source_id in enumerate(unique_ids):
                for target_id in unique_ids[idx + 1:]:
                    edge_key = self._record_social_edge_evidence_conn(
                        conn,
                        source_id,
                        target_id,
                        chapter,
                        edge_layer="chapter_copresence",
                        edge_subtype="same_chapter",
                        directional=False,
                        evidence_scope=scene_scope or f"chapter:{chapter}",
                        evidence_summary="Shared chapter presence; weak familiarity signal only.",
                        shared_scene_count=1,
                        chapter_overlap_count=1,
                        familiarity_signal=0.18,
                        confidence=0.22,
                        evidence_source_type=evidence_source_type,
                        actuality_status=actuality_status,
                        source_pov_id=source_pov_id,
                        scene_scope=scene_scope or f"chapter:{chapter}",
                        boundary_title_id=boundary_title_id,
                        boundary_book_id=boundary_book_id,
                        boundary_volume_id=boundary_volume_id,
                        session_id=session_id,
                        source_session=source_session,
                        inherited_confidence=inherited_confidence,
                    )
                    if edge_key:
                        inserted += 1
        return inserted

    def _record_event_social_context_conn(self, conn, event_id: int | None, max_participants: int = 80) -> int:
        if not event_id:
            return 0
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chapter, summary, scene_scope, evidence_source_type,
                   actuality_status, observed_by_entity_id,
                   boundary_title_id, boundary_book_id, boundary_volume_id,
                   session_id, source_session, COALESCE(inherited_confidence, 1.0),
                   COALESCE(confidence, ?)
            FROM events
            WHERE id = ?
        """, (RELATIONSHIP_BASE_CONFIDENCE, event_id))
        event_row = cursor.fetchone()
        if not event_row:
            return 0
        (
            chapter,
            summary,
            scene_scope,
            evidence_source_type,
            actuality_status,
            observed_by_entity_id,
            boundary_title_id,
            boundary_book_id,
            boundary_volume_id,
            session_id,
            source_session,
            inherited_confidence,
            event_confidence,
        ) = event_row
        cursor.execute("""
            SELECT ep.entity_id
            FROM event_participants ep
            JOIN entities e ON ep.entity_id = e.id
            WHERE ep.event_id = ?
              AND e.entity_type IN ('INDIVIDUAL', 'GROUP', 'LOCATION')
            GROUP BY ep.entity_id
            ORDER BY MAX(ep.confidence) DESC, ep.entity_id
            LIMIT ?
        """, (event_id, max_participants))
        participant_ids = [entity_id for (entity_id,) in cursor.fetchall()]
        inserted = 0
        for idx, source_id in enumerate(participant_ids):
            for target_id in participant_ids[idx + 1:]:
                edge_key = self._record_social_edge_evidence_conn(
                    conn,
                    source_id,
                    target_id,
                    chapter,
                    edge_layer="shared_event",
                    edge_subtype="same_event",
                    directional=False,
                    event_id=event_id,
                    evidence_scope=scene_scope or f"event:{event_id}",
                    evidence_summary=summary,
                    shared_scene_count=1,
                    shared_event_count=1,
                    chapter_overlap_count=1,
                    familiarity_signal=0.32,
                    cooperation_signal=0.18,
                    confidence=max(0.1, min(0.65, float(event_confidence or RELATIONSHIP_BASE_CONFIDENCE) * 0.75)),
                    evidence_source_type=evidence_source_type or "observed_fact",
                    actuality_status=actuality_status or "actual",
                    source_pov_id=observed_by_entity_id,
                    scene_scope=scene_scope,
                    boundary_title_id=boundary_title_id,
                    boundary_book_id=boundary_book_id,
                    boundary_volume_id=boundary_volume_id,
                    session_id=session_id,
                    source_session=source_session,
                    inherited_confidence=inherited_confidence,
                )
                if edge_key:
                    inserted += 1
        return inserted

    def record_event_social_context(self, event_id: int | None, max_participants: int = 80) -> int:
        with self._get_connection() as conn:
            return self._record_event_social_context_conn(conn, event_id, max_participants)

    def refresh_social_graph_metrics(self, chapter: int | None = None) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT source_id, target_id
                FROM relationships
                WHERE source_id != target_id
            """)
            adjacency: dict[int, set[int]] = {}
            direct_edges = set()
            for source_id, target_id in cursor.fetchall():
                pair = tuple(sorted((source_id, target_id)))
                direct_edges.add(pair)
                adjacency.setdefault(source_id, set()).add(target_id)
                adjacency.setdefault(target_id, set()).add(source_id)

            cursor.execute("""
                SELECT source_id, target_id, promotion_state,
                       COALESCE(shared_event_count, 0), edge_layer
                FROM relationship_social_edges
                WHERE source_id != target_id
            """)
            social_edges = set()
            for source_id, target_id, promotion_state, shared_event_count, edge_layer in cursor.fetchall():
                if promotion_state == "weak" and int(shared_event_count or 0) <= 0 and edge_layer != "direct_relationship":
                    continue
                pair = tuple(sorted((source_id, target_id)))
                social_edges.add(pair)
                adjacency.setdefault(source_id, set()).add(target_id)
                adjacency.setdefault(target_id, set()).add(source_id)

            nodes = sorted(adjacency)
            visited = set()
            components = []
            for node in nodes:
                if node in visited:
                    continue
                stack = [node]
                visited.add(node)
                component = []
                while stack:
                    current = stack.pop()
                    component.append(current)
                    for neighbor in adjacency.get(current, set()):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            stack.append(neighbor)
                if len(component) >= 2:
                    components.append(sorted(component))

            articulation_nodes: set[int] = set()
            for component in components:
                component_set = set(component)
                for candidate in component:
                    remaining = component_set - {candidate}
                    if len(remaining) < 2:
                        continue
                    start = next(iter(remaining))
                    seen = {start}
                    stack = [start]
                    while stack:
                        current = stack.pop()
                        for neighbor in adjacency.get(current, set()):
                            if neighbor == candidate or neighbor not in remaining or neighbor in seen:
                                continue
                            seen.add(neighbor)
                            stack.append(neighbor)
                    if seen != remaining:
                        articulation_nodes.add(candidate)

            conn.execute("DELETE FROM relationship_community_members")
            conn.execute("DELETE FROM relationship_communities")
            entity_community_counts: dict[int, int] = {}
            entity_cluster_strengths: dict[int, float] = {}
            for component in components:
                component_edges = {
                    pair
                    for pair in direct_edges | social_edges
                    if pair[0] in component and pair[1] in component
                }
                member_count = len(component)
                possible_edges = member_count * (member_count - 1) / 2
                density = round(len(component_edges) / possible_edges, 4) if possible_edges else 0.0
                cohesion_score = round(min(1.0, density * (member_count / max(member_count, 3))), 4)
                community_key = "component:" + "-".join(str(entity_id) for entity_id in component[:80])
                first_seen = None
                last_seen = chapter
                if component_edges:
                    placeholders = ",".join("?" for _ in component)
                    cursor.execute(f"""
                        SELECT MIN(first_seen_chapter), MAX(last_seen_chapter),
                               MIN(COALESCE(inherited_confidence, 1.0)),
                               MAX(source_session)
                        FROM relationship_social_edges
                        WHERE source_id IN ({placeholders})
                          AND target_id IN ({placeholders})
                    """, (*component, *component))
                    first_seen, last_seen_social, inherited_confidence, source_session = cursor.fetchone()
                    last_seen = last_seen_social or chapter
                else:
                    inherited_confidence = LOCAL_GRAPH_CONFIDENCE
                    source_session = None
                bridge_count = sum(1 for entity_id in component if entity_id in articulation_nodes)
                conn.execute("""
                    INSERT INTO relationship_communities (
                        community_key, member_count, edge_count, density,
                        cohesion_score, bridge_count, evidence_summary,
                        first_seen_chapter, last_seen_chapter, source_session,
                        inherited_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    community_key,
                    member_count,
                    len(component_edges),
                    density,
                    cohesion_score,
                    bridge_count,
                    f"Detected dense social component with {member_count} members and {len(component_edges)} edges.",
                    first_seen,
                    last_seen,
                    source_session,
                    inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE,
                ))
                for entity_id in component:
                    local_degree = len(adjacency.get(entity_id, set()) & set(component))
                    neighbor_ids = sorted(adjacency.get(entity_id, set()) & set(component))
                    neighbor_edges = sum(
                        1
                        for idx, left in enumerate(neighbor_ids)
                        for right in neighbor_ids[idx + 1:]
                        if tuple(sorted((left, right))) in (direct_edges | social_edges)
                    )
                    possible_neighbor_edges = len(neighbor_ids) * (len(neighbor_ids) - 1) / 2
                    local_density = (neighbor_edges / possible_neighbor_edges) if possible_neighbor_edges else 0.0
                    bridge_score = 1.0 if entity_id in articulation_nodes else 0.0
                    cluster_strength = round(local_density * min(local_degree, 6) / 6, 4)
                    entity_community_counts[entity_id] = entity_community_counts.get(entity_id, 0) + 1
                    entity_cluster_strengths[entity_id] = max(entity_cluster_strengths.get(entity_id, 0.0), cluster_strength)
                    conn.execute("""
                        INSERT INTO relationship_community_members (
                            community_key, entity_id, role, local_degree,
                            bridge_score, cluster_strength
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        community_key,
                        entity_id,
                        "bridge" if bridge_score else "member",
                        local_degree,
                        bridge_score,
                        cluster_strength,
                    ))

            conn.execute("DELETE FROM entity_social_metrics")
            cursor.execute("SELECT id FROM entities WHERE entity_type IN ('INDIVIDUAL', 'GROUP', 'LOCATION')")
            for (entity_id,) in cursor.fetchall():
                direct_degree = len({
                    pair for pair in direct_edges if entity_id in pair
                })
                social_degree = len(adjacency.get(entity_id, set()))
                neighbors = sorted(adjacency.get(entity_id, set()))
                neighbor_edges = sum(
                    1
                    for idx, left in enumerate(neighbors)
                    for right in neighbors[idx + 1:]
                    if tuple(sorted((left, right))) in (direct_edges | social_edges)
                )
                possible_neighbor_edges = len(neighbors) * (len(neighbors) - 1) / 2
                local_density = round(neighbor_edges / possible_neighbor_edges, 4) if possible_neighbor_edges else 0.0
                bridge_score = 1.0 if entity_id in articulation_nodes else 0.0
                cluster_strength = entity_cluster_strengths.get(entity_id, round(local_density * min(social_degree, 6) / 6, 4))
                conn.execute("""
                    INSERT INTO entity_social_metrics (
                        entity_id, direct_degree, social_degree, community_count,
                        local_density, bridge_score, cluster_strength,
                        last_computed_chapter
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entity_id,
                    direct_degree,
                    social_degree,
                    entity_community_counts.get(entity_id, 0),
                    local_density,
                    bridge_score,
                    cluster_strength,
                    chapter,
                ))
            return {
                "communities": len(components),
                "social_edges": len(social_edges),
                "direct_edges": len(direct_edges),
                "bridge_nodes": len(articulation_nodes),
            }

    def _backfill_social_edges_from_existing_events(self, conn):
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM relationship_social_evidence")
        if cursor.fetchone()[0]:
            return
        cursor.execute("""
            SELECT r.source_id, r.target_id, rh.chapter, rh.event_id,
                   rh.evidence, rh.evidence_source_type, rh.source_pov_id,
                   rh.source_speaker_id, rh.scene_scope, rh.confidence,
                   rh.boundary_title_id, rh.boundary_book_id, rh.boundary_volume_id,
                   rh.session_id, rh.source_session, rh.inherited_confidence,
                   rh.trust_score, rh.hostility_score
            FROM relationship_history rh
            JOIN relationships r ON rh.rel_key = r.rel_key
        """)
        for (
            source_id, target_id, chapter, event_id, evidence, evidence_source_type,
            source_pov_id, source_speaker_id, scene_scope, confidence,
            boundary_title_id, boundary_book_id, boundary_volume_id, session_id,
            source_session, inherited_confidence, trust_score, hostility_score
        ) in cursor.fetchall():
            self._record_social_edge_evidence_conn(
                conn,
                source_id,
                target_id,
                chapter,
                edge_layer="direct_relationship",
                edge_subtype="explicit",
                directional=True,
                event_id=event_id,
                evidence_scope="relationship_history",
                evidence_summary=evidence,
                shared_scene_count=1,
                dialogue_overlap_count=1,
                familiarity_signal=0.55,
                trust_signal=max(float(trust_score or 0), 0.0) / 10,
                hostility_signal=max(float(hostility_score or 0.0) / 10, abs(min(float(trust_score or 0), 0.0)) / 10),
                confidence=confidence or RELATIONSHIP_BASE_CONFIDENCE,
                evidence_source_type=evidence_source_type or "observed_fact",
                source_pov_id=source_pov_id,
                source_speaker_id=source_speaker_id,
                scene_scope=scene_scope,
                boundary_title_id=boundary_title_id,
                boundary_book_id=boundary_book_id,
                boundary_volume_id=boundary_volume_id,
                session_id=session_id,
                source_session=source_session,
                inherited_confidence=inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE,
            )
        cursor.execute("SELECT id FROM events")
        for (event_id,) in cursor.fetchall():
            self._record_event_social_context_conn(conn, event_id)

    def add_event_causal_edge(
        self,
        parent_event_id: int | None,
        child_event_id: int | None,
        relation_type: str = "precedes",
        confidence: float = 0.5,
    ):
        if not parent_event_id or not child_event_id or parent_event_id == child_event_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO event_causal_edges (
                    parent_event_id, child_event_id, relation_type, confidence
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(parent_event_id, child_event_id, relation_type) DO UPDATE SET
                    confidence = MAX(event_causal_edges.confidence, excluded.confidence)
            """, (parent_event_id, child_event_id, relation_type, confidence))

    def add_event_consequence(
        self,
        event_id: int | None,
        rel_key: str | None,
        description: str,
        trust_delta: int | None = None,
        target_entity_id: int | None = None,
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        consequence_type: str = "relationship_change",
    ) -> int | None:
        if not event_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_consequences (
                    event_id, consequence_type, target_entity_id, rel_key,
                    description, trust_delta, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                consequence_type,
                target_entity_id,
                rel_key,
                description,
                trust_delta,
                confidence,
            ))
            return cursor.lastrowid

    def _recalculate_relationship_snapshot(self, conn, rel_key: str):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT trust_score, COALESCE(hostility_score, 0.0),
                   COALESCE(respect_score, 0.0), COALESCE(fear_score, 0.0),
                   COALESCE(confidence, ?), chapter, event_id
            FROM relationship_history
            WHERE rel_key = ? AND trust_score IS NOT NULL
            ORDER BY chapter, interaction_order, id
        """, (RELATIONSHIP_BASE_CONFIDENCE, rel_key))
        rows = cursor.fetchall()
        if not rows:
            return
        weight = sum(max(row[4], 0.05) for row in rows)
        current_score = round(sum(row[0] * max(row[4], 0.05) for row in rows) / weight, 3) if weight else rows[-1][0]
        current_hostility = round(sum(row[1] * max(row[4], 0.05) for row in rows) / weight, 3) if weight else rows[-1][1]
        current_respect = round(sum(row[2] * max(row[4], 0.05) for row in rows) / weight, 3) if weight else rows[-1][2]
        current_fear = round(sum(row[3] * max(row[4], 0.05) for row in rows) / weight, 3) if weight else rows[-1][3]
        last_chapter = rows[-1][5]
        last_event_id = rows[-1][6]
        conn.execute("""
            UPDATE relationships
            SET current_trust_score = ?,
                current_hostility_score = ?,
                current_respect_score = ?,
                current_fear_score = ?,
                last_updated_chapter = ?,
                last_event_id = COALESCE(?, last_event_id)
            WHERE rel_key = ?
        """, (current_score, current_hostility, current_respect, current_fear, last_chapter, last_event_id, rel_key))

    def _normalize_relationship_reason(
        self,
        trust: int | None,
        interaction_type: str,
        trust_delta: int | None,
        supplied_reason: str | None = None,
    ) -> str:
        supplied_reason = " ".join(str(supplied_reason or "").split())
        if supplied_reason:
            return supplied_reason[:240]
        direction = "neutral"
        if trust is not None and trust > 0:
            direction = "positive"
        elif trust is not None and trust < 0:
            direction = "negative"
        delta_text = f"; trust_delta={trust_delta}" if trust_delta is not None else ""
        return f"{interaction_type or 'interaction'} relationship signal: {direction}{delta_text}"

    def add_relationship_event(
        self,
        source_id: int,
        target_id: int,
        chapter: int,
        trust: int,
        evidence: str,
        interaction_type: str = "interaction",
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        event_id: int | None = None,
        consequence_description: str | None = None,
        reason: str | None = None,
        relation_type: str = "interaction",
        hostility_score: float | None = None,
        respect_score: float | None = None,
        fear_score: float | None = None,
        evidence_source_type: str = "observed_fact",
        source_pov_id: int | None = None,
        source_speaker_id: int | None = None,
        scene_scope: str | None = None,
        boundary_title_id: str | None = None,
        boundary_book_id: str | None = None,
        boundary_volume_id: str | None = None,
        session_id: str | None = None,
        source_session: str | None = None,
        inherited_confidence: float = LOCAL_GRAPH_CONFIDENCE,
    ):
        rel_key = f"{source_id}::{target_id}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM entities WHERE id IN (?, ?)", (source_id, target_id))
            if len(cursor.fetchall()) != 2:
                return
            if not (
                self.entity_can_form_social_edges(source_id, cursor)
                and self.entity_can_form_social_edges(target_id, cursor)
            ):
                return
            cursor.execute("""
                SELECT id, COALESCE(current_life_status, 'unknown')
                FROM entities
                WHERE id IN (?, ?)
            """, (source_id, target_id))
            life_statuses = {row_id: status for row_id, status in cursor.fetchall()}
            dead_ids = [
                row_id for row_id, status in life_statuses.items()
                if status == "dead"
            ]
            if dead_ids and evidence_source_type in {"observed_fact", "direct", "dialogue"}:
                evidence_key = self.normalize_alias_key(evidence)
                revival_markers = {"alive", "survived", "returned", "revived", "resurrected", "restored"}
                if not any(marker in evidence_key for marker in revival_markers):
                    self.record_conflict(
                        "relationship_with_confirmed_dead_entity",
                        chapter,
                        {
                            "source_id": source_id,
                            "target_id": target_id,
                            "dead_entity_ids": dead_ids,
                            "evidence": evidence,
                            "evidence_source_type": evidence_source_type,
                        },
                        source_id,
                        target_id,
                        severity=5,
                    )
                    return
        if hostility_score is None:
            hostility_score = abs(min(trust or 0, 0))
        if respect_score is None:
            respect_score = max(trust or 0, 0)
        if fear_score is None:
            fear_score = 0.0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conn.execute("""
                INSERT INTO relationships (
                    rel_key, source_id, target_id, relation_type,
                    source_pov_id, source_speaker_id, scene_scope
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rel_key) DO UPDATE SET
                    relation_type = excluded.relation_type,
                    source_pov_id = COALESCE(excluded.source_pov_id, relationships.source_pov_id),
                    source_speaker_id = COALESCE(excluded.source_speaker_id, relationships.source_speaker_id),
                    scene_scope = COALESCE(excluded.scene_scope, relationships.scene_scope)
            """, (rel_key, source_id, target_id, relation_type, source_pov_id, source_speaker_id, scene_scope))

            cursor.execute("""
                SELECT COALESCE(MAX(interaction_order), 0) + 1
                FROM relationship_history
                WHERE rel_key = ? AND chapter = ?
            """, (rel_key, chapter))
            interaction_order = cursor.fetchone()[0]

            cursor.execute("""
                SELECT trust_score, evidence, chapter
                FROM relationship_history
                WHERE rel_key = ?
                ORDER BY chapter DESC, interaction_order DESC
                LIMIT 1
            """, (rel_key,))
            previous = cursor.fetchone()
            previous_trust = None
            if previous:
                previous_trust, previous_evidence, previous_chapter = previous
                if (
                    previous_trust is not None
                    and trust is not None
                    and previous_trust * trust < 0
                    and abs(previous_trust - trust) >= RELATIONSHIP_CONTRADICTION_DELTA
                ):
                    self.record_conflict(
                        "relationship_contradiction",
                        chapter,
                        {
                            "rel_key": rel_key,
                            "previous_chapter": previous_chapter,
                            "previous_trust": previous_trust,
                            "previous_evidence": previous_evidence,
                            "new_trust": trust,
                            "new_evidence": evidence,
                        },
                        source_id,
                        target_id,
                    )

            trust_delta = trust - previous_trust if previous_trust is not None and trust is not None else trust
            normalized_reason = self._normalize_relationship_reason(
                trust,
                interaction_type,
                trust_delta,
                reason,
            )
            consequence_id = self.add_event_consequence(
                event_id,
                rel_key,
                consequence_description or normalized_reason,
                trust_delta=trust_delta,
                confidence=confidence,
            )

            history_cursor = conn.execute("""
                INSERT INTO relationship_history (
                    rel_key, chapter, interaction_order, interaction_type,
                    trust_score, hostility_score, respect_score, fear_score,
                    reason, evidence, evidence_source_type, source_pov_id,
                    source_speaker_id, scene_scope, confidence, boundary_title_id,
                    boundary_book_id, boundary_volume_id, session_id, source_session,
                    inherited_confidence, event_id, consequence_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rel_key,
                chapter,
                interaction_order,
                interaction_type,
                trust,
                hostility_score,
                respect_score,
                fear_score,
                normalized_reason,
                evidence,
                evidence_source_type,
                source_pov_id,
                source_speaker_id,
                scene_scope,
                confidence,
                boundary_title_id,
                boundary_book_id or boundary_title_id,
                boundary_volume_id,
                session_id,
                source_session,
                inherited_confidence,
                event_id,
                consequence_id,
            ))
            self.record_resolver_decision(
                "relationships",
                "relationship",
                rel_key,
                chapter,
                "interaction_recorded",
                confidence=confidence,
                supporting_evidence=[{"table": "relationship_history", "id": history_cursor.lastrowid}],
                metadata={
                    "source_id": source_id,
                    "target_id": target_id,
                    "interaction_type": interaction_type,
                    "evidence_source_type": evidence_source_type,
                    "event_id": event_id,
                },
                conn=conn,
            )
            self._record_social_edge_evidence_conn(
                conn,
                source_id,
                target_id,
                chapter,
                edge_layer="direct_relationship",
                edge_subtype=relation_type or interaction_type or "interaction",
                directional=True,
                event_id=event_id,
                evidence_scope=scene_scope or f"chapter:{chapter}",
                evidence_summary=evidence,
                shared_scene_count=1,
                shared_event_count=1 if event_id else 0,
                dialogue_overlap_count=1 if evidence_source_type in {"spoken_claim", "dialogic"} else 0,
                familiarity_signal=0.55,
                trust_signal=max(float(trust or 0), 0.0) / 10,
                hostility_signal=max(float(hostility_score or 0.0) / 10, abs(min(float(trust or 0), 0.0)) / 10),
                cooperation_signal=max(float(trust or 0), 0.0) / 20,
                confidence=confidence,
                evidence_source_type=evidence_source_type,
                source_pov_id=source_pov_id,
                source_speaker_id=source_speaker_id,
                scene_scope=scene_scope,
                boundary_title_id=boundary_title_id,
                boundary_book_id=boundary_book_id,
                boundary_volume_id=boundary_volume_id,
                session_id=session_id,
                source_session=source_session,
                inherited_confidence=inherited_confidence,
            )
            self._recalculate_relationship_snapshot(conn, rel_key)

    def get_memory_cards_text(self, chapter_text_lower: str, limit: int = MEMORY_CARD_LIMIT) -> str:
        matched_entities = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            candidate_ids = self._ranked_entity_candidates(conn, chapter_text_lower, limit * 2)
            if not candidate_ids:
                return "No relevant accepted/probable memory cards found for this chapter."

            placeholders = ",".join("?" for _ in candidate_ids)
            cursor.execute(f"""
                SELECT e.id, e.canonical_name, e.entity_type, e.first_seen_chapter,
                       e.last_verified_chapter, e.mention_count, e.importance_score,
                       e.visibility_score, e.surface_form_class, e.location_subtype,
                       GROUP_CONCAT(a.alias_name || ':' || a.status, '|')
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                    AND COALESCE(a.status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
                WHERE e.id IN ({placeholders})
                GROUP BY e.id, e.canonical_name, e.entity_type,
                         e.first_seen_chapter, e.last_verified_chapter, e.mention_count,
                         e.importance_score, e.visibility_score, e.surface_form_class, e.location_subtype
                ORDER BY e.visibility_score DESC, e.importance_score DESC,
                         e.last_verified_chapter DESC, e.mention_count DESC
                LIMIT ?
            """, (*candidate_ids, limit))

            for row in cursor.fetchall():
                (
                    entity_id,
                    canon,
                    entity_type,
                    first_seen,
                    last_seen,
                    mention_count,
                    importance,
                    visibility,
                    surface_class,
                    location_subtype,
                    aliases_raw,
                ) = row
                aliases = [a for a in aliases_raw.split("|") if a] if aliases_raw else []
                matched_entities.append((
                    entity_id,
                    canon,
                    entity_type,
                    first_seen,
                    last_seen,
                    mention_count,
                    aliases,
                    importance,
                    visibility,
                    surface_class,
                    location_subtype,
                ))

            cards = []
            for (
                entity_id,
                canon,
                entity_type,
                first_seen,
                last_seen,
                _mention_count,
                aliases,
                importance,
                visibility,
                surface_class,
                location_subtype,
            ) in matched_entities:
                cursor.execute("""
                    SELECT CASE WHEN r.source_id = ? THEN et.canonical_name ELSE es.canonical_name END AS other_name,
                           COALESCE(r.current_trust_score, rh.trust_score) AS trust_score,
                           rh.evidence,
                           rh.chapter,
                           ev.summary,
                           COALESCE(rh.inherited_confidence, 1.0),
                           rh.source_session
                    FROM relationship_history rh
                    JOIN relationships r ON rh.rel_key = r.rel_key
                    JOIN entities es ON r.source_id = es.id
                    JOIN entities et ON r.target_id = et.id
                    LEFT JOIN events ev ON rh.event_id = ev.id
                    WHERE r.source_id = ? OR r.target_id = ?
                    ORDER BY COALESCE(rh.inherited_confidence, 1.0) DESC,
                             rh.chapter DESC, rh.interaction_order DESC
                    LIMIT ?
                """, (entity_id, entity_id, entity_id, MEMORY_CARD_RELATIONSHIP_LIMIT))
                relationships = cursor.fetchall()

                cursor.execute("""
                    SELECT ev.chapter, ev.summary,
                           COALESCE(ev.inherited_confidence, 1.0),
                           ev.source_session
                    FROM event_participants ep
                    JOIN events ev ON ep.event_id = ev.id
                    WHERE ep.entity_id = ?
                    ORDER BY COALESCE(ev.inherited_confidence, 1.0) DESC,
                             ev.chapter DESC, ev.event_order DESC
                    LIMIT ?
                """, (entity_id, MEMORY_CARD_RECENT_EVENT_LIMIT))
                recent_events = cursor.fetchall()

                cursor.execute("""
                    SELECT title_text, status
                    FROM title_links
                    WHERE entity_id = ?
                      AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
                    ORDER BY confidence DESC, support_count DESC, last_seen DESC
                    LIMIT 5
                """, (entity_id,))
                title_links = cursor.fetchall()

                parts = [
                    f"- {canon}",
                    f"  type: {entity_type}",
                    f"  importance: {importance:.2f}",
                    f"  visibility: {visibility:.2f}",
                    f"  surface_form: {surface_class}",
                    f"  first_seen: {first_seen}",
                    f"  last_seen: {last_seen}",
                ]
                if location_subtype:
                    parts.append(f"  location_subtype: {location_subtype}")
                if aliases:
                    parts.append(f"  aliases/status: {', '.join(aliases[:5])}")
                if title_links:
                    parts.append(
                        "  titles/status: "
                        + ", ".join(f"{title}:{status}" for title, status in title_links)
                    )
                if relationships:
                    rel_text = "; ".join(
                        f"{other}: trust {trust} (ch {chapter}, {self._context_origin_label(inherited_confidence, source_session)}, event: {event_summary or 'unlinked'})"
                        for other, trust, _evidence, chapter, event_summary, inherited_confidence, source_session in relationships
                    )
                    parts.append(f"  relationship_snapshot: {rel_text}")
                if recent_events:
                    event_text = "; ".join(
                        f"ch {chapter} ({self._context_origin_label(inherited_confidence, source_session)}): {summary[:120]}"
                        for chapter, summary, inherited_confidence, source_session in recent_events
                        if summary
                    )
                    if event_text:
                        parts.append(f"  recent_events: {event_text}")
                cursor.execute("""
                    SELECT esm.social_degree, esm.community_count,
                           esm.local_density, esm.bridge_score,
                           esm.cluster_strength
                    FROM entity_social_metrics esm
                    WHERE esm.entity_id = ?
                """, (entity_id,))
                social_metrics = cursor.fetchone()
                if social_metrics:
                    social_degree, community_count, local_density, bridge_score, cluster_strength = social_metrics
                    parts.append(
                        "  social_metrics: "
                        f"social_degree {social_degree}, communities {community_count}, "
                        f"local_density {float(local_density or 0):.2f}, "
                        f"bridge {float(bridge_score or 0):.2f}, "
                        f"cluster_strength {float(cluster_strength or 0):.2f}"
                    )
                cards.append("\n".join(parts))

        if not cards:
            return "No relevant accepted/probable memory cards found for this chapter."

        return "\n\n".join(cards)

    def get_life_status_context_text(self, chapter_text_lower: str, limit: int = MEMORY_CARD_LIMIT) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            entity_ids = self._ranked_entity_candidates(conn, chapter_text_lower, limit)
            if not entity_ids:
                return "No life/death status context for current chapter entities."
            placeholders = ",".join("?" for _ in entity_ids)
            cursor.execute(f"""
                SELECT e.id, e.canonical_name, s.scope_type, owner.canonical_name,
                       s.actual_status, s.belief_status, s.appearance_status,
                       s.confidence, s.last_observation_chapter,
                       s.last_confirmation_chapter, s.status_age,
                       s.source_evidence_ids
                FROM life_status_snapshots s
                JOIN entities e ON s.entity_id = e.id
                LEFT JOIN entities owner ON s.scope_owner_entity_id = owner.id
                WHERE s.entity_id IN ({placeholders})
                ORDER BY s.confidence DESC, s.last_observation_chapter DESC
                LIMIT ?
            """, (*entity_ids, limit * 3))
            snapshots = cursor.fetchall()
            cursor.execute(f"""
                SELECT e.canonical_name, lse.chapter, lse.actual_status,
                       lse.belief_status, lse.appearance_status,
                       lse.belief_owner_type, owner.canonical_name,
                       lse.reader_visible, lse.participation_type,
                       lse.observation_type, lse.status_reason,
                       lse.confidence, lse.evidence_text,
                       COALESCE(lse.inherited_confidence, 1.0),
                       lse.source_session
                FROM life_status_evidence lse
                JOIN entities e ON lse.entity_id = e.id
                LEFT JOIN entities owner ON lse.belief_owner_entity_id = owner.id
                WHERE lse.entity_id IN ({placeholders})
                ORDER BY COALESCE(lse.inherited_confidence, 1.0) DESC,
                         lse.chapter DESC, lse.narrative_order DESC, lse.id DESC
                LIMIT ?
            """, (*entity_ids, limit * 4))
            evidence_rows = cursor.fetchall()
        if not snapshots and not evidence_rows:
            return "No life/death status context for current chapter entities."
        lines = []
        for (
            _entity_id, canon, scope_type, owner_name, actual, belief,
            appearance, confidence, last_obs, last_confirm, status_age,
            source_evidence_ids
        ) in snapshots:
            owner_text = f":{owner_name}" if owner_name else ""
            lines.append(
                f"- {canon} [{scope_type}{owner_text}]: actual={actual}, belief={belief}, "
                f"appearance={appearance}, confidence={float(confidence or 0):.2f}, "
                f"last_observed={last_obs}, last_confirmed={last_confirm}, age={status_age}, "
                f"evidence={source_evidence_ids or '[]'}"
            )
        for (
            canon, chapter, actual, belief, appearance, owner_type, owner_name,
            reader_visible, participation, observation, reason, confidence,
            evidence, inherited_confidence, source_session
        ) in evidence_rows[:limit]:
            owner_text = f"{owner_type}:{owner_name}" if owner_name else owner_type
            visibility = "reader-visible" if reader_visible else "not-reader-visible"
            lines.append(
                f"- evidence {canon} ch {chapter} ({self._context_origin_label(inherited_confidence, source_session)}): "
                f"actual={actual}, belief={belief}, appearance={appearance}, owner={owner_text}, "
                f"{visibility}, participation={participation}, observation={observation}, "
                f"reason={reason}, confidence={float(confidence or 0):.2f}; {str(evidence or '')[:160]}"
            )
        return "\n".join(lines)

    def get_relevant_events_text(
        self,
        chapter_text_lower: str,
        chapter_index: int | None = None,
        limit: int = EVENT_CONTEXT_LIMIT,
    ) -> str:
        rows = []
        current_chapter = chapter_index if chapter_index is not None else 2_147_483_647
        with self._get_connection() as conn:
            cursor = conn.cursor()
            entity_ids = self._ranked_entity_candidates(conn, chapter_text_lower, MEMORY_CARD_LIMIT * 2)
            event_ids = self._ranked_event_candidates(conn, chapter_text_lower, entity_ids, limit)
            if not event_ids:
                return "No prior event history matched this chapter's text."

            placeholders = ",".join("?" for _ in event_ids)
            cursor.execute(f"""
                SELECT ev.chapter, ev.summary, GROUP_CONCAT(e.canonical_name, ', '),
                       COALESCE(ev.inherited_confidence, 1.0), ev.source_session,
                       COALESCE(ev.occurrence_role, 'occurrence'),
                       lm.identity_key, lm.landmark_type, lm.event_state,
                       lm.event_reliability, lm.historical_start_text, lm.duration_text,
                       (
                           SELECT ln.name_text
                           FROM landmark_names ln
                           WHERE ln.landmark_id = lm.id
                             AND COALESCE(ln.status, 'accepted') != 'rejected'
                             AND COALESCE(ln.audience_type, 'reader') IN ('reader', 'public')
                             AND COALESCE(ln.first_known_chapter, 0) <= ?
                           ORDER BY CASE ln.name_role
                               WHEN 'reader' THEN 0 WHEN 'canonical' THEN 1
                               WHEN 'historical' THEN 2 ELSE 3 END,
                               ln.confidence DESC, ln.id
                           LIMIT 1
                       ),
                       (
                           SELECT lp.summary
                           FROM landmark_perspectives lp
                           WHERE lp.landmark_id = lm.id
                             AND COALESCE(lp.reader_visibility, 'partially_known') != 'hidden'
                             AND COALESCE(lp.chapter, 0) <= ?
                           ORDER BY CASE lp.perspective_type WHEN 'reader' THEN 0 WHEN 'neutral' THEN 1 ELSE 2 END,
                               lp.confidence DESC, lp.id DESC
                           LIMIT 1
                       )
                FROM events ev
                LEFT JOIN event_participants ep ON ev.id = ep.event_id
                LEFT JOIN entities e ON ep.entity_id = e.id
                LEFT JOIN event_landmarks lm ON ev.landmark_id = lm.id
                WHERE ev.id IN ({placeholders})
                GROUP BY ev.id, ev.chapter, ev.summary, ev.event_order,
                         ev.inherited_confidence, ev.source_session, lm.id
                ORDER BY COALESCE(ev.inherited_confidence, 1.0) DESC,
                         ev.chapter DESC, ev.event_order DESC
                LIMIT ?
            """, (current_chapter, current_chapter, *event_ids, limit))
            for (
                chapter, summary, participants_raw, confidence, source_session, occurrence_role, identity_key,
                landmark_type, event_state, reliability, historical_start, duration, display_name,
                perspective_summary,
            ) in cursor.fetchall():
                participants = [p.strip() for p in (participants_raw or "").split(",") if p.strip()]
                rows.append((
                    chapter, summary, participants, confidence, source_session, occurrence_role, identity_key,
                    landmark_type, event_state, reliability, historical_start, duration, display_name,
                    perspective_summary,
                ))

        if not rows:
            return "No prior event history matched this chapter's text."

        return "\n".join(
            f"- ch {chapter}: {display_name or summary}"
            + f" ({self._context_origin_label(confidence, source_session)})"
            + (f" [link={occurrence_role}]" if occurrence_role != "occurrence" else "")
            + (f" [landmark:{identity_key}]" if identity_key else "")
            + (f" [{landmark_type}; state={event_state}; reliability={reliability}]" if identity_key else "")
            + (f" [historical={historical_start}]" if historical_start else "")
            + (f" [duration={duration}]" if duration else "")
            + (f" [participants: {', '.join(participants[:5])}]" if participants else "")
            + (f" {perspective_summary[:180]}" if perspective_summary else "")
            for (
                chapter, summary, participants, confidence, source_session, occurrence_role, identity_key,
                landmark_type, event_state, reliability, historical_start, duration, display_name,
                perspective_summary,
            ) in rows
        )

    def get_relationship_context_text(self, chapter_text_lower: str, limit: int = MEMORY_CARD_LIMIT) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            entity_ids = self._ranked_entity_candidates(conn, chapter_text_lower, limit)

            if not entity_ids:
                return "No relationship context for current chapter entities."

            placeholders = ",".join("?" for _ in entity_ids)
            cursor.execute(f"""
                SELECT es.canonical_name, et.canonical_name,
                       COALESCE(r.current_trust_score, rh.trust_score),
                       rh.evidence, rh.chapter, ev.summary,
                       COALESCE(rh.inherited_confidence, 1.0),
                       rh.source_session
                FROM relationship_history rh
                JOIN relationships r ON rh.rel_key = r.rel_key
                JOIN entities es ON r.source_id = es.id
                JOIN entities et ON r.target_id = et.id
                LEFT JOIN events ev ON rh.event_id = ev.id
                WHERE r.source_id IN ({placeholders}) OR r.target_id IN ({placeholders})
                ORDER BY COALESCE(rh.inherited_confidence, 1.0) DESC,
                         rh.chapter DESC, rh.interaction_order DESC
                LIMIT ?
            """, (*entity_ids, *entity_ids, MEMORY_CARD_RELATIONSHIP_LIMIT * max(1, len(entity_ids))))
            rows = cursor.fetchall()

        if not rows:
            return "No relationship history for current chapter entities."

        return "\n".join(
            f"- {source} / {target}: trust {trust}, ch {chapter}, {self._context_origin_label(inherited_confidence, source_session)}, event: {event_summary or 'unlinked'}, evidence: {evidence}"
            for source, target, trust, evidence, chapter, event_summary, inherited_confidence, source_session in rows
            if evidence
        )

    def get_social_relationship_context_text(self, chapter_text_lower: str, limit: int = MEMORY_CARD_LIMIT) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            entity_ids = self._ranked_entity_candidates(conn, chapter_text_lower, limit)

            if not entity_ids:
                return "No social web context for current chapter entities."

            placeholders = ",".join("?" for _ in entity_ids)
            cursor.execute(f"""
                SELECT es.canonical_name, et.canonical_name,
                       se.edge_layer, se.edge_subtype, se.promotion_state,
                       se.support_count, se.shared_event_count,
                       se.chapter_overlap_count, se.familiarity_signal,
                       se.trust_signal, se.hostility_signal,
                       se.cooperation_signal, se.confidence,
                       se.evidence_summary, se.last_seen_chapter,
                       COALESCE(se.inherited_confidence, 1.0),
                       se.source_session
                FROM relationship_social_edges se
                JOIN entities es ON se.source_id = es.id
                JOIN entities et ON se.target_id = et.id
                WHERE se.source_id IN ({placeholders}) OR se.target_id IN ({placeholders})
                ORDER BY COALESCE(se.inherited_confidence, 1.0) DESC,
                         CASE se.promotion_state
                             WHEN 'confirmed' THEN 0
                             WHEN 'stable' THEN 1
                             WHEN 'inferred' THEN 2
                             ELSE 3
                         END,
                         se.support_count DESC,
                         se.last_seen_chapter DESC
                LIMIT ?
            """, (*entity_ids, *entity_ids, max(limit, MEMORY_CARD_RELATIONSHIP_LIMIT * max(1, len(entity_ids)))))
            rows = cursor.fetchall()

            cursor.execute("""
                SELECT rc.community_key, rc.member_count, rc.density,
                       rc.cohesion_score, rc.bridge_count,
                       GROUP_CONCAT(e.canonical_name, ', ')
                FROM relationship_communities rc
                JOIN relationship_community_members rcm ON rc.community_key = rcm.community_key
                JOIN entities e ON rcm.entity_id = e.id
                WHERE rc.community_key IN (
                    SELECT community_key
                    FROM relationship_community_members
                    WHERE entity_id IN ({})
                )
                GROUP BY rc.community_key, rc.member_count, rc.density,
                         rc.cohesion_score, rc.bridge_count
                ORDER BY rc.cohesion_score DESC, rc.member_count DESC
                LIMIT ?
            """.format(placeholders), (*entity_ids, max(3, limit // 2)))
            community_rows = cursor.fetchall()

        lines = []
        for (
            source, target, layer, subtype, promotion_state, support_count,
            shared_event_count, chapter_overlap_count, familiarity_signal,
            trust_signal, hostility_signal, cooperation_signal, confidence,
            evidence_summary, chapter, inherited_confidence, source_session,
        ) in rows:
            lines.append(
                f"- {source} / {target}: {promotion_state} {layer}/{subtype}, "
                f"support {support_count}, shared_events {shared_event_count}, chapters {chapter_overlap_count}, "
                f"signals familiarity {float(familiarity_signal or 0):.2f}, trust {float(trust_signal or 0):.2f}, "
                f"hostility {float(hostility_signal or 0):.2f}, cooperation {float(cooperation_signal or 0):.2f}, "
                f"confidence {float(confidence or 0):.2f}, ch {chapter}, "
                f"{self._context_origin_label(inherited_confidence, source_session)}, evidence: {evidence_summary or 'structural co-presence'}"
            )

        if community_rows:
            lines.append("COMMUNITIES:")
            for community_key, member_count, density, cohesion_score, bridge_count, members_raw in community_rows:
                members = [member.strip() for member in (members_raw or "").split(",") if member.strip()]
                lines.append(
                    f"- {community_key}: members {member_count}, density {float(density or 0):.2f}, "
                    f"cohesion {float(cohesion_score or 0):.2f}, bridges {bridge_count}; "
                    f"{', '.join(members[:8])}"
                )

        if not lines:
            return "No social web context for current chapter entities."
        return "\n".join(lines)

    def export_graph_state(self) -> dict:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            export = {}
            for table in (
                "entities",
                "aliases",
                "mention_occurrences",
                "unresolved_mentions",
                "reference_mentions",
                "name_semantic_relations",
                "kinship_mentions",
                "life_status_evidence",
                "life_status_snapshots",
                "life_status_timeline_segments",
                "entity_legacy_signals",
                "title_links",
                "identity_promotions",
                "entity_type_votes",
                "chapter_boundaries",
                "chapter_visibility_scopes",
                "relationships",
                "relationship_history",
                "relationship_social_edges",
                "relationship_social_evidence",
                "relationship_communities",
                "relationship_community_members",
                "entity_social_metrics",
                "events",
                "event_landmarks",
                "landmark_names",
                "landmark_hierarchy",
                "landmark_event_links",
                "landmark_perspectives",
                "landmark_importance",
                "landmark_locations",
                "landmark_participants",
                "landmark_assertions",
                "landmark_resolution_evidence",
                "event_clusters",
                "event_cluster_members",
                "event_participants",
                "event_consequences",
                "event_causal_edges",
                "merge_candidates",
                "ghost_merge_candidates",
                "merge_audit",
                "conflict_records",
                "performance_metrics",
                "chapter_evidence_revisions",
                "reader_snapshot_revisions",
                "reader_snapshot_current",
                "chapter_processing_checkpoints",
                "chapter_invalidations",
                "resolver_decisions",
                "image_parse_cache",
                "image_evidence_revisions",
                "image_occurrence_provenance",
                "schema_metadata",
            ):
                cursor.execute(f"SELECT * FROM {table}")
                export[table] = [dict(row) for row in cursor.fetchall()]
            conn.row_factory = None
            export["_metadata"] = {
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "cache_version": CACHE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "model_name": GEMINI_MODEL_NAME,
                "normalization_version": NORMALIZATION_VERSION,
                "bookbuddy_version": BOOKBUDDY_VERSION,
                "snapshot_contract_version": SNAPSHOT_CONTRACT_VERSION,
                "replay_version": REPLAY_VERSION,
                "resolver_manifest": RESOLVER_VERSIONS,
                "image_evidence_schema_version": IMAGE_EVIDENCE_SCHEMA_VERSION,
                "exported_at": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "export_format": "bookbuddy_graph_export_v2",
            }
            return export

    def register_merge_candidate(
        self,
        id_1: int,
        id_2: int,
        score: float = 0.0,
        evidence: dict | str | None = None,
        chapter_idx: int | None = None,
        state: str = "candidate",
    ) -> bool:
        entity_a_id = min(id_1, id_2)
        entity_b_id = max(id_1, id_2)
        
        if entity_a_id == entity_b_id: return False
        
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT entity_type, canonical_name FROM entities WHERE id = ?", (entity_a_id,))
            entity_a = cursor.fetchone()
            cursor.execute("SELECT entity_type, canonical_name FROM entities WHERE id = ?", (entity_b_id,))
            entity_b = cursor.fetchone()
            if not entity_a or not entity_b:
                return False
            hard_rejection = self._merge_hard_rejection(cursor, entity_a_id, entity_b_id)
            if hard_rejection:
                self.record_conflict(
                    "merge_conflict",
                    chapter_idx or 0,
                    {
                        "entity_a_id": entity_a_id,
                        "entity_a_name": entity_a[1],
                        "entity_a_type": entity_a[0],
                        "entity_b_id": entity_b_id,
                        "entity_b_name": entity_b[1],
                        "entity_b_type": entity_b[0],
                        "reason": hard_rejection,
                    },
                    entity_a_id,
                    entity_b_id,
                )
                return False
            
            required_votes = self._merge_vote_threshold(cursor, entity_a_id, entity_b_id)

            cursor.execute("""
                INSERT INTO merge_candidates (
                    entity_a_id, entity_b_id, votes, score, state, evidence,
                    last_seen_chapter
                )
                VALUES (?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(entity_a_id, entity_b_id) DO UPDATE SET
                    votes = votes + 1,
                    score = MAX(merge_candidates.score, excluded.score),
                    state = CASE
                        WHEN merge_candidates.state = 'rejected' THEN merge_candidates.state
                        WHEN excluded.state = 'probable' THEN 'probable'
                        ELSE merge_candidates.state
                    END,
                    evidence = excluded.evidence,
                    last_seen_chapter = COALESCE(excluded.last_seen_chapter, merge_candidates.last_seen_chapter)
            """, (
                entity_a_id,
                entity_b_id,
                score,
                state,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True) if isinstance(evidence, dict) else (evidence or ""),
                chapter_idx,
            ))
            
            cursor.execute("SELECT votes FROM merge_candidates WHERE entity_a_id = ? AND entity_b_id = ?", (entity_a_id, entity_b_id))
            votes = cursor.fetchone()[0]
            
            if votes >= required_votes:
                return True
        return False

    def _merge_vote_threshold(self, cursor, entity_a_id: int, entity_b_id: int) -> int:
        candidate_id = max(entity_a_id, entity_b_id)
        cursor.execute("SELECT COUNT(*) FROM aliases WHERE entity_id = ?", (candidate_id,))
        alias_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM relationships WHERE source_id = ? OR target_id = ?",
            (candidate_id, candidate_id),
        )
        edge_count = cursor.fetchone()[0]
        return min(5, 2 + ((alias_count + edge_count) // 2))

    def _merge_hard_rejection(self, cursor, entity_a_id: int, entity_b_id: int) -> str | None:
        left = self._entity_signature(cursor, entity_a_id)
        right = self._entity_signature(cursor, entity_b_id)
        if not left or not right:
            return "missing entity"
        if left["entity_type"] != right["entity_type"]:
            return "entity type mismatch"
        ontology_rejection = self.ontology_compatibility_reason(left, right)
        if ontology_rejection:
            return ontology_rejection
        semantic_blocker = self._has_name_semantic_blocker(
            cursor,
            left["canonical_key"],
            right["canonical_key"],
            {
                "namesake",
                "eponym_attribution",
                "homonym_collision",
                "possessive_reference",
                "same_surface_distinct_referent",
            },
        )
        if semantic_blocker:
            return f"name semantic relation is not merge evidence: {semantic_blocker}"
        left_book = left.get("boundary_book_id") or left.get("boundary_title_id")
        right_book = right.get("boundary_book_id") or right.get("boundary_title_id")
        if left_book and right_book and left_book != right_book:
            return "different book boundary"
        if left.get("boundary_volume_id") and right.get("boundary_volume_id") and left["boundary_volume_id"] != right["boundary_volume_id"]:
            return "different volume boundary"
        if left.get("session_id") and right.get("session_id") and left["session_id"] != right["session_id"]:
            return "different session boundary"
        if (
            (left.get("inherited_confidence") or LOCAL_GRAPH_CONFIDENCE) < 0.999
            or (right.get("inherited_confidence") or LOCAL_GRAPH_CONFIDENCE) < 0.999
        ):
            left_terms = {left["canonical_key"], *left["aliases"]}
            right_terms = {right["canonical_key"], *right["aliases"]}
            if (
                left_terms.isdisjoint(right_terms)
                and not (left["events"] & right["events"])
                and not (left["social_neighbors"] & right["social_neighbors"])
            ):
                return "inherited candidate without direct local corroboration"
        if left["title_class"] and right["title_class"] and left["title_class"] != right["title_class"]:
            return "incompatible title evidence"
        if left["entity_type"] == "LOCATION":
            return None
        left_suffix = left["tokens"][-1] if left["tokens"] else ""
        right_suffix = right["tokens"][-1] if right["tokens"] else ""
        short_long_name_match = False
        if len(left["tokens"]) == 1 and left["tokens"][0] in set(right["tokens"]):
            short_long_name_match = True
        if len(right["tokens"]) == 1 and right["tokens"][0] in set(left["tokens"]):
            short_long_name_match = True
        if (
            left_suffix
            and right_suffix
            and left_suffix != right_suffix
            and not short_long_name_match
            and not (left["canonical_key"] in right["aliases"] or right["canonical_key"] in left["aliases"])
        ):
            return "different name suffix without alias evidence"
        if (
            left_suffix
            and right_suffix
            and left_suffix == right_suffix
            and len(left["tokens"]) > 1
            and len(right["tokens"]) > 1
            and left["canonical_key"] not in right["aliases"]
            and right["canonical_key"] not in left["aliases"]
        ):
            shared_neighbors = (left["neighbors"] | left["social_neighbors"]) & (right["neighbors"] | right["social_neighbors"])
            shared_events = left["events"] & right["events"]
            if not shared_neighbors and not shared_events:
                return "shared family or group name without independent evidence"
        cursor.execute("""
            SELECT 1
            FROM conflict_records
            WHERE conflict_type IN (
                'relationship_contradiction',
                'entity_type_collision',
                'alias_collision',
                'merge_conflict'
            )
              AND status NOT IN ('resolved', 'rejected')
              AND (
                  (entity_a_id = ? AND entity_b_id = ?)
                  OR (entity_a_id = ? AND entity_b_id = ?)
              )
            LIMIT 1
        """, (entity_a_id, entity_b_id, entity_b_id, entity_a_id))
        if cursor.fetchone():
            return "open contradiction conflict"
        return None

    def finalize_merge_candidates(self, min_votes: int | None = None, max_merges: int | None = None) -> dict:
        finalized = 0
        skipped = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT entity_a_id, entity_b_id, votes, COALESCE(score, 0), COALESCE(state, 'candidate')
                FROM merge_candidates
                WHERE COALESCE(state, 'candidate') IN ('candidate', 'probable')
                ORDER BY votes DESC, entity_a_id, entity_b_id
            """)
            candidates = cursor.fetchall()

        for entity_a_id, entity_b_id, votes, score, state in candidates:
            if max_merges is not None and finalized >= max_merges:
                break
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, entity_type FROM entities WHERE id IN (?, ?) ORDER BY id",
                    (entity_a_id, entity_b_id),
                )
                existing_entities = cursor.fetchall()
                entity_types = {entity_type for _entity_id, entity_type in existing_entities}
                if len(existing_entities) != 2 or len(entity_types) != 1:
                    skipped += 1
                    continue
                rejection = self._merge_hard_rejection(cursor, entity_a_id, entity_b_id)
                if rejection:
                    conn.execute("""
                        UPDATE merge_candidates
                        SET state = 'rejected', evidence = ?
                        WHERE entity_a_id = ? AND entity_b_id = ?
                    """, (rejection, entity_a_id, entity_b_id))
                    skipped += 1
                    continue
                threshold = min_votes if min_votes is not None else self._merge_vote_threshold(cursor, entity_a_id, entity_b_id)
            if votes < threshold or (state != "probable" and score < 0.78):
                skipped += 1
                continue
            merged_survivor = self.merge_entities(
                entity_a_id,
                entity_b_id,
                merge_reason="candidate_finalizer",
                merge_votes=votes,
                merge_score=score,
                merge_evidence={"state": state, "threshold": threshold},
            )
            if merged_survivor:
                finalized += 1
            else:
                skipped += 1

        return {
            "finalized": finalized,
            "skipped": skipped,
            "candidates_checked": len(candidates),
        }

    def _entity_survival_score(self, cursor, entity_id: int) -> tuple[float, int, int]:
        cursor.execute("""
            SELECT canonical_name, confidence, importance_score, visibility_score,
                   mention_count, first_seen_chapter, last_verified_chapter,
                   surface_form_class
            FROM entities
            WHERE id = ?
        """, (entity_id,))
        row = cursor.fetchone()
        if not row:
            return (-1.0, 0, -entity_id)
        (
            canonical_name,
            confidence,
            importance,
            visibility,
            mention_count,
            first_seen,
            last_seen,
            surface_class,
        ) = row
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(support_count), 0), COALESCE(MAX(confidence), 0)
            FROM aliases
            WHERE entity_id = ?
              AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """, (entity_id,))
        alias_count, alias_support, alias_confidence = cursor.fetchone()
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(support_count), 0)
            FROM title_links
            WHERE entity_id = ?
              AND COALESCE(status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
        """, (entity_id,))
        title_count, title_support = cursor.fetchone()
        cursor.execute("""
            SELECT COUNT(*)
            FROM relationships
            WHERE source_id = ? OR target_id = ?
        """, (entity_id, entity_id))
        relationship_degree = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM event_participants WHERE entity_id = ?", (entity_id,))
        event_degree = cursor.fetchone()[0]

        surface_bonus = {
            "compound_name": 0.35,
            "proper_name": 0.25,
            "place_name": 0.20,
            "title": 0.05,
            "role": -0.20,
            "descriptor": -0.30,
            "location_fragment": -0.30,
        }.get(surface_class or "", 0.0)
        canonical_tokens = self.normalize_alias_key(canonical_name).split()
        if len(canonical_tokens) > 1 and _is_title_prefix(canonical_tokens[0]):
            surface_bonus -= 1.0
        name_bonus = min(len(str(canonical_name or "").split()), 4) * 0.05
        score = (
            float(confidence or 0) * 3.0
            + float(importance or 0) * 2.0
            + float(visibility or 0) * 2.0
            + min(int(mention_count or 0), 20) * 0.10
            + int(alias_count or 0) * 0.45
            + int(alias_support or 0) * 0.12
            + float(alias_confidence or 0) * 0.5
            + int(title_count or 0) * 0.25
            + int(title_support or 0) * 0.08
            + int(relationship_degree or 0) * 0.20
            + int(event_degree or 0) * 0.08
            + surface_bonus
            + name_bonus
        )
        earliest = int(first_seen or last_seen or 10**9)
        return (score, -earliest, -entity_id)

    def _preferred_name_survivor(self, cursor, id_1: int, id_2: int) -> int | None:
        cursor.execute("SELECT id, canonical_name FROM entities WHERE id IN (?, ?)", (id_1, id_2))
        rows = cursor.fetchall()
        if len(rows) != 2:
            return None

        def name_parts(name: str) -> tuple[list[str], bool]:
            tokens = self.normalize_alias_key(name).split()
            has_title = bool(len(tokens) > 1 and _is_title_prefix(tokens[0]))
            while len(tokens) > 1 and _is_title_prefix(tokens[0]):
                tokens = tokens[1:]
            return tokens, has_title

        left_id, left_name = rows[0]
        right_id, right_name = rows[1]
        left_tokens, left_title = name_parts(left_name)
        right_tokens, right_title = name_parts(right_name)
        if not left_tokens or not right_tokens:
            return None

        left_suffix = left_tokens[-1]
        right_suffix = right_tokens[-1]
        if left_suffix != right_suffix:
            return None

        if left_title != right_title:
            return right_id if left_title else left_id
        if len(left_tokens) == 1 and len(right_tokens) > 1:
            return right_id
        if len(right_tokens) == 1 and len(left_tokens) > 1:
            return left_id
        return None

    def _choose_merge_survivor(self, cursor, id_1: int, id_2: int) -> tuple[int, int]:
        preferred = self._preferred_name_survivor(cursor, id_1, id_2)
        if preferred in {id_1, id_2}:
            return preferred, id_2 if preferred == id_1 else id_1
        ranked = sorted(
            (id_1, id_2),
            key=lambda entity_id: self._entity_survival_score(cursor, entity_id),
            reverse=True,
        )
        return ranked[0], ranked[1]

    def merge_entities(
        self,
        id_1: int,
        id_2: int,
        preferred_surviving_id: int | None = None,
        merge_reason: str = "direct_merge",
        merge_votes: int = 0,
        merge_score: float = 0.0,
        merge_evidence: dict | str | None = None,
    ):
        if id_1 == id_2:
            return id_1
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            hard_rejection = self._merge_hard_rejection(cursor, id_1, id_2)
            if hard_rejection:
                self.record_conflict(
                    "merge_conflict",
                    0,
                    {
                        "entity_a_id": id_1,
                        "entity_b_id": id_2,
                        "reason": hard_rejection,
                        "merge_reason": merge_reason,
                    },
                    id_1,
                    id_2,
                )
                return None
            if preferred_surviving_id in {id_1, id_2}:
                surviving_id = preferred_surviving_id
                losing_id = id_2 if preferred_surviving_id == id_1 else id_1
            else:
                surviving_id, losing_id = self._choose_merge_survivor(cursor, id_1, id_2)

            if surviving_id == losing_id:
                return surviving_id

            cursor.execute("SELECT canonical_name FROM entities WHERE id = ?", (surviving_id,))
            surviving_name_row = cursor.fetchone()
            cursor.execute("SELECT canonical_name FROM entities WHERE id = ?", (losing_id,))
            losing_name_row = cursor.fetchone()
            surviving_name = surviving_name_row[0] if surviving_name_row else ""
            losing_name = losing_name_row[0] if losing_name_row else ""
            if not surviving_name_row or not losing_name_row:
                return surviving_id if surviving_name_row else None
            conn.execute("""
                INSERT INTO merge_audit (
                    surviving_entity_id, losing_entity_id, surviving_name,
                    losing_name, votes, score, evidence, resolver_version, reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'resolver_v1', ?)
            """, (
                surviving_id,
                losing_id,
                surviving_name,
                losing_name,
                merge_votes,
                merge_score,
                json.dumps(merge_evidence, ensure_ascii=False, sort_keys=True) if isinstance(merge_evidence, dict) else (merge_evidence or ""),
                merge_reason,
            ))
            
            # P0 Fix: Metadata Absorption ensures graph weights and Top-K metrics remain accurate
            cursor.execute("""
                SELECT mention_count, last_verified_chapter, confidence,
                       importance_score, visibility_score
                FROM entities
                WHERE id = ?
            """, (losing_id,))
            losing_meta = cursor.fetchone()
            if losing_meta:
                l_count, l_verified, l_confidence, l_importance, l_visibility = losing_meta
                conn.execute("""
                    UPDATE entities 
                    SET mention_count = mention_count + ?, 
                        last_verified_chapter = MAX(last_verified_chapter, ?),
                        confidence = MAX(confidence, ?),
                        importance_score = MAX(importance_score, ?),
                        visibility_score = MAX(visibility_score, ?)
                    WHERE id = ?
                """, (l_count, l_verified, l_confidence, l_importance, l_visibility, surviving_id))

            losing_alias_key = self.normalize_alias_key(losing_name)
            surviving_alias_key = self.normalize_alias_key(surviving_name)
            if losing_alias_key and losing_alias_key != surviving_alias_key:
                conn.execute("""
                    INSERT INTO aliases (
                        alias_name, alias_key, entity_id, chapter_found, evidence,
                        confidence, support_count, first_seen, last_seen, status,
                        validation_status, validation_reason
                    )
                    SELECT ?, ?, ?, first_seen_chapter, ?, 0.95, 1,
                           first_seen_chapter, last_verified_chapter, 'accepted',
                           'merge_absorbed_canonical', ?
                    FROM entities
                    WHERE id = ?
                    ON CONFLICT(entity_id, alias_key) DO UPDATE SET
                        alias_name = CASE
                            WHEN LENGTH(excluded.alias_name) > LENGTH(aliases.alias_name)
                            THEN excluded.alias_name
                            ELSE aliases.alias_name
                        END,
                        confidence = MAX(aliases.confidence, excluded.confidence),
                        support_count = aliases.support_count + 1,
                        status = CASE
                            WHEN aliases.status = 'rejected' THEN excluded.status
                            ELSE aliases.status
                        END,
                        validation_status = excluded.validation_status,
                        validation_reason = excluded.validation_reason
                """, (
                    losing_name,
                    losing_alias_key,
                    surviving_id,
                    f"Absorbed canonical name during merge: {losing_name}",
                    merge_reason,
                    losing_id,
                ))
            
            conn.execute("""
                DELETE FROM aliases
                WHERE entity_id = ?
                  AND alias_key IN (
                      SELECT alias_key FROM aliases WHERE entity_id = ?
                  )
            """, (losing_id, surviving_id))
            conn.execute("UPDATE aliases SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("""
                DELETE FROM title_links
                WHERE entity_id = ?
                  AND title_key IN (
                      SELECT title_key FROM title_links WHERE entity_id = ?
                  )
            """, (losing_id, surviving_id))
            conn.execute("UPDATE title_links SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("""
                INSERT INTO entity_type_votes (
                    entity_id, entity_type, support_count, confidence, first_seen, last_seen
                )
                SELECT ?, entity_type, support_count, confidence, first_seen, last_seen
                FROM entity_type_votes
                WHERE entity_id = ?
                ON CONFLICT(entity_id, entity_type) DO UPDATE SET
                    support_count = entity_type_votes.support_count + excluded.support_count,
                    confidence = MAX(entity_type_votes.confidence, excluded.confidence),
                    first_seen = MIN(entity_type_votes.first_seen, excluded.first_seen),
                    last_seen = MAX(entity_type_votes.last_seen, excluded.last_seen)
            """, (surviving_id, losing_id))
            conn.execute("DELETE FROM entity_type_votes WHERE entity_id = ?", (losing_id,))
            conn.execute(
                "UPDATE mention_occurrences SET linked_entity_id = ? WHERE linked_entity_id = ?",
                (surviving_id, losing_id),
            )
            conn.execute("UPDATE mention_occurrences SET narrator_entity_id = ? WHERE narrator_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE unresolved_mentions SET speaker_entity_id = ? WHERE speaker_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE unresolved_mentions SET narrator_entity_id = ? WHERE narrator_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE kinship_mentions SET speaker_entity_id = ? WHERE speaker_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE kinship_mentions SET narrator_entity_id = ? WHERE narrator_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE kinship_mentions SET resolved_entity_id = ? WHERE resolved_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE life_status_evidence SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE life_status_evidence SET belief_owner_entity_id = ? WHERE belief_owner_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE life_status_evidence SET source_pov_id = ? WHERE source_pov_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE life_status_evidence SET source_speaker_id = ? WHERE source_speaker_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE life_status_evidence SET narrator_entity_id = ? WHERE narrator_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_legacy_signals SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_legacy_signals SET source_pov_id = ? WHERE source_pov_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_legacy_signals SET source_speaker_id = ? WHERE source_speaker_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_legacy_signals SET narrator_entity_id = ? WHERE narrator_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_state_history SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_state_history SET source_entity_id = ? WHERE source_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_state_history SET speaker_entity_id = ? WHERE speaker_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE entity_state_history SET narrator_entity_id = ? WHERE narrator_entity_id = ?", (surviving_id, losing_id))
            conn.execute("DELETE FROM life_status_snapshots WHERE entity_id IN (?, ?)", (surviving_id, losing_id))
            conn.execute("DELETE FROM life_status_timeline_segments WHERE entity_id IN (?, ?)", (surviving_id, losing_id))
            conn.execute(
                "UPDATE identity_promotions SET resolved_entity_id = ? WHERE resolved_entity_id = ?",
                (surviving_id, losing_id),
            )
            conn.execute(
                "UPDATE identity_promotions SET placeholder_entity_id = NULL WHERE placeholder_entity_id = ?",
                (losing_id,),
            )
            conn.execute("UPDATE chapter_pov SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute(
                "UPDATE conflict_records SET entity_a_id = ? WHERE entity_a_id = ?",
                (surviving_id, losing_id),
            )
            conn.execute(
                "UPDATE conflict_records SET entity_b_id = ? WHERE entity_b_id = ?",
                (surviving_id, losing_id),
            )
            conn.execute("""
                INSERT OR IGNORE INTO event_participants (event_id, entity_id, role, confidence)
                SELECT event_id, ?, role, confidence
                FROM event_participants
                WHERE entity_id = ?
            """, (surviving_id, losing_id))
            conn.execute("DELETE FROM event_participants WHERE entity_id = ?", (losing_id,))
            conn.execute("UPDATE event_consequences SET target_entity_id = ? WHERE target_entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE relationships SET source_pov_id = ? WHERE source_pov_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE relationships SET source_speaker_id = ? WHERE source_speaker_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE relationship_history SET source_pov_id = ? WHERE source_pov_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE relationship_history SET source_speaker_id = ? WHERE source_speaker_id = ?", (surviving_id, losing_id))
            
            cursor.execute("SELECT rel_key, source_id, target_id FROM relationships WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            obsolete_edges = cursor.fetchall()
            
            for old_key, src, tgt in obsolete_edges:
                new_src = surviving_id if src == losing_id else src
                new_tgt = surviving_id if tgt == losing_id else tgt
                if new_src == new_tgt: continue 
                
                new_key = f"{new_src}::{new_tgt}"
                conn.execute("""
                    INSERT OR IGNORE INTO relationships (
                        rel_key, source_id, target_id, relation_type,
                        source_pov_id, source_speaker_id, scene_scope
                    )
                    SELECT ?, ?, ?, relation_type, source_pov_id, source_speaker_id, scene_scope
                    FROM relationships
                    WHERE rel_key = ?
                """, (new_key, new_src, new_tgt, old_key))
                
                cursor.execute("""
                    SELECT chapter, interaction_order, interaction_type, trust_score,
                           hostility_score, respect_score, fear_score, reason,
                           evidence, evidence_source_type, source_pov_id,
                           source_speaker_id, scene_scope, confidence,
                           boundary_title_id, boundary_book_id, boundary_volume_id, session_id,
                           source_session, inherited_confidence, event_id,
                           consequence_id
                    FROM relationship_history
                    WHERE rel_key = ?
                """, (old_key,))
                obsolete_history = cursor.fetchall()
                
                for (
                    ch, order, interaction_type, trust, hostility, respect, fear,
                    reason, evidence, evidence_source_type, source_pov_id,
                    source_speaker_id, scene_scope, confidence,
                    boundary_title_id, boundary_book_id, boundary_volume_id, session_id,
                    source_session, inherited_confidence, event_id,
                    consequence_id
                ) in obsolete_history:
                    conn.execute("""
                        INSERT INTO relationship_history (
                            rel_key, chapter, interaction_order, interaction_type,
                            trust_score, hostility_score, respect_score, fear_score,
                            reason, evidence, evidence_source_type, source_pov_id,
                            source_speaker_id, scene_scope, confidence,
                            boundary_title_id, boundary_book_id, boundary_volume_id, session_id,
                            source_session, inherited_confidence, event_id,
                            consequence_id
                        )
                        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM relationship_history
                            WHERE rel_key = ?
                              AND chapter = ?
                              AND COALESCE(interaction_order, -1) = COALESCE(?, -1)
                              AND COALESCE(event_id, -1) = COALESCE(?, -1)
                              AND COALESCE(evidence, '') = COALESCE(?, '')
                        )
                    """, (
                        new_key,
                        ch,
                        order,
                        interaction_type,
                        trust,
                        hostility,
                        respect,
                        fear,
                        reason,
                        evidence,
                        evidence_source_type,
                        source_pov_id,
                        source_speaker_id,
                        scene_scope,
                        confidence,
                        boundary_title_id,
                        boundary_book_id,
                        boundary_volume_id,
                        session_id,
                        source_session,
                        inherited_confidence,
                        event_id,
                        consequence_id,
                        new_key,
                        ch,
                        order,
                        event_id,
                        evidence,
                    ))
                    conn.execute(
                        "UPDATE event_consequences SET rel_key = ? WHERE rel_key = ?",
                        (new_key, old_key),
                    )
                self._recalculate_relationship_snapshot(conn, new_key)
                
            conn.execute("DELETE FROM relationships WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            cursor.execute("""
                SELECT source_id, target_id, chapter, edge_layer, edge_subtype,
                       directional, event_id, evidence_scope, evidence_summary,
                       shared_scene_count, shared_event_count, chapter_overlap_count,
                       dialogue_overlap_count, familiarity_signal, trust_signal,
                       hostility_signal, cooperation_signal, confidence,
                       evidence_source_type, actuality_status, source_pov_id,
                       source_speaker_id, scene_scope, boundary_title_id,
                       boundary_book_id, boundary_volume_id, session_id,
                       source_session, inherited_confidence, evidence_key
                FROM relationship_social_evidence
                WHERE source_id = ? OR target_id = ?
            """, (losing_id, losing_id))
            social_evidence_rows = cursor.fetchall()
            conn.execute("DELETE FROM relationship_social_evidence WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            conn.execute("DELETE FROM relationship_social_edges WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            for (
                source_id, target_id, chapter, edge_layer, edge_subtype,
                directional, event_id, evidence_scope, evidence_summary,
                shared_scene_count, shared_event_count, chapter_overlap_count,
                dialogue_overlap_count, familiarity_signal, trust_signal,
                hostility_signal, cooperation_signal, confidence,
                evidence_source_type, actuality_status, source_pov_id,
                source_speaker_id, scene_scope, boundary_title_id,
                boundary_book_id, boundary_volume_id, session_id,
                source_session, inherited_confidence, evidence_key
            ) in social_evidence_rows:
                new_source_id = surviving_id if source_id == losing_id else source_id
                new_target_id = surviving_id if target_id == losing_id else target_id
                if new_source_id == new_target_id:
                    continue
                self._record_social_edge_evidence_conn(
                    conn,
                    new_source_id,
                    new_target_id,
                    chapter,
                    edge_layer=edge_layer or "cooccurrence",
                    edge_subtype=edge_subtype or "general",
                    directional=bool(directional),
                    event_id=event_id,
                    evidence_scope=evidence_scope,
                    evidence_summary=evidence_summary,
                    shared_scene_count=shared_scene_count or 0,
                    shared_event_count=shared_event_count or 0,
                    chapter_overlap_count=chapter_overlap_count or 0,
                    dialogue_overlap_count=dialogue_overlap_count or 0,
                    familiarity_signal=familiarity_signal or 0.0,
                    trust_signal=trust_signal or 0.0,
                    hostility_signal=hostility_signal or 0.0,
                    cooperation_signal=cooperation_signal or 0.0,
                    confidence=confidence or 0.25,
                    evidence_source_type=evidence_source_type or "observed_fact",
                    actuality_status=actuality_status or "actual",
                    source_pov_id=surviving_id if source_pov_id == losing_id else source_pov_id,
                    source_speaker_id=surviving_id if source_speaker_id == losing_id else source_speaker_id,
                    scene_scope=scene_scope,
                    boundary_title_id=boundary_title_id,
                    boundary_book_id=boundary_book_id,
                    boundary_volume_id=boundary_volume_id,
                    session_id=session_id,
                    source_session=source_session,
                    inherited_confidence=inherited_confidence if inherited_confidence is not None else LOCAL_GRAPH_CONFIDENCE,
                    evidence_key=evidence_key,
                )
            cursor.execute("""
                SELECT entity_a_id, entity_b_id, votes
                FROM merge_candidates
                WHERE entity_a_id = ? OR entity_b_id = ?
            """, (losing_id, losing_id))
            for entity_a_id, entity_b_id, votes in cursor.fetchall():
                other_id = entity_b_id if entity_a_id == losing_id else entity_a_id
                if other_id == surviving_id:
                    continue
                new_a, new_b = sorted((surviving_id, other_id))
                conn.execute("""
                    INSERT INTO merge_candidates (entity_a_id, entity_b_id, votes)
                    VALUES (?, ?, ?)
                    ON CONFLICT(entity_a_id, entity_b_id) DO UPDATE SET
                        votes = MAX(merge_candidates.votes, excluded.votes)
                """, (new_a, new_b, votes))
            conn.execute("DELETE FROM merge_candidates WHERE entity_a_id = ? OR entity_b_id = ?", (losing_id, losing_id))
            conn.execute("""
                INSERT INTO ghost_merge_candidates (target_id, votes)
                SELECT ?, votes
                FROM ghost_merge_candidates
                WHERE target_id = ?
                ON CONFLICT(target_id) DO UPDATE SET
                    votes = MAX(ghost_merge_candidates.votes, excluded.votes)
            """, (surviving_id, losing_id))
            conn.execute("DELETE FROM ghost_merge_candidates WHERE target_id = ?", (losing_id,))
            self._mark_entity_search_dirty(conn, surviving_id)
            cursor.execute("SELECT DISTINCT event_id FROM event_participants WHERE entity_id = ?", (surviving_id,))
            for (event_id,) in cursor.fetchall():
                self._sync_event_search_terms(conn, event_id)
            conn.execute("DELETE FROM entities WHERE id = ?", (losing_id,))
            try:
                from life_status_resolver import LifeStatusResolver
                LifeStatusResolver(self).resolve_entity(surviving_id)
            except Exception:
                pass
            self.refresh_social_graph_metrics()
            return surviving_id

    def register_ghost_merge(self, true_entity_id: int, required_votes: int = 2) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ghost_merge_candidates (target_id, votes)
                VALUES (?, 1)
                ON CONFLICT(target_id) DO UPDATE SET votes = votes + 1
            """, (true_entity_id,))
            
            cursor.execute("SELECT votes FROM ghost_merge_candidates WHERE target_id = ?", (true_entity_id,))
            votes = cursor.fetchone()[0]
            
            if votes >= required_votes:
                return True
        return False

    def merge_ghost_nodes(self, true_entity_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM entities WHERE canonical_name = ?", ("[UNNAMED_POV]",))
            row = cursor.fetchone()
            if row:
                self.merge_entities(true_entity_id, row[0])
                conn.execute("DELETE FROM ghost_merge_candidates")
