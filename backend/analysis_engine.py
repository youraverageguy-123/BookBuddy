import os
import json
import re
import time
import logging
from copy import deepcopy
from pydantic import BaseModel, Field
from typing import Literal
from db_manager import BookDatabase
from datetime import datetime
from alias_validator import CONFLICT, NEEDS_REVIEW, REJECTED, TRUE_ALIAS, TITLE_LINK, validate_alias
from conflict_resolver import resolve_trivial_conflicts
from entity_reconciler import reconcile_entities
from event_deduper import add_event_with_cluster
from landmark_resolver import LandmarkResolver
from identity_promoter import promote_named_pov
from location_reconciler import reconcile_locations
from mention_indexer import index_ai_mentions
from prompt_context_builder import build_prompt_context
from snapshot_manager import EvidenceStore, SnapshotStore
from title_linker import maybe_add_title_link
from image_pipeline import parse_chapter_images
from image_pipeline.fallback import AIVisionFallback
from ai import GenerationRequest
from image_pipeline.replay_adapter import ingest_image_evidence
from config import (
    ALIAS_BASE_CONFIDENCE,
    ALIAS_COMMON_NOUN_PENALTY,
    ALIAS_LOWERCASE_PENALTY,
    ALIAS_TITLE_ONLY_PENALTY,
    BOOKBUDDY_VERSION,
    CACHE_VERSION,
    AI_CHAPTER_MODEL_NAME,
    GRAPH_SCHEMA_VERSION,
    NORMALIZATION_VERSION,
    PREVIOUS_CONTEXT_CHAPTERS,
    PROMPT_VERSION,
    RELATIONSHIP_BASE_CONFIDENCE,
    IMAGE_EVIDENCE_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

# ─── Pydantic Schema ─────────────────────────────────────────────────────────

class EntityDict(BaseModel):
    name: str
    entity_type: Literal["INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"] = Field(
        description=(
            "INDIVIDUAL: a named person. "
            "GROUP: a faction, caste, organisation, or named collective. "
            "LOCATION: a named place — planet, city, building, region. "
            "CONCEPT_OR_LORE: mythology, religion, historical event, abstract idea."
        )
    )
    entity_category: str = Field(default="UNKNOWN")
    species_or_kind: str = Field(default="unknown")
    sentience: str = Field(default="unknown")
    story_role: str = Field(default="unknown")
    functional_role: str = Field(default="")
    active_status: str = Field(default="uncertain")
    identity_status: str = Field(default="unknown")
    entity_persistence: str = Field(default="persistent")
    can_speak: str = Field(default="unknown")
    can_move: str = Field(default="unknown")
    can_think: str = Field(default="unknown")
    can_remember: str = Field(default="unknown")
    can_make_decisions: str = Field(default="unknown")
    can_form_relationships: str = Field(default="unknown")
    literal_status: str = Field(default="literal")
    interpretation_status: str = Field(default="actual")
    ontology_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    ontology_evidence: str = Field(default="")


class EntitySemanticRelationDict(BaseModel):
    source: str
    target: str = ""
    relation_type: str
    source_evidence: str = ""
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)


class LanguageObservationDict(BaseModel):
    surface_text: str
    language: str = "unknown"
    writing_system: str = "unknown"
    translation_status: str = "unknown"
    decoder_source: str = ""
    source_evidence: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

class LifeStatusEvidenceDict(BaseModel):
    subject: str
    entity_type: Literal["INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"] = "INDIVIDUAL"
    actual_status: Literal["alive", "dead", "missing", "unknown"] = "unknown"
    belief_status: Literal["alive", "dead", "missing", "unknown"] = "unknown"
    appearance_status: Literal["possible_alive", "observed_alive", "confirmed_alive", "appears_dead", "unknown"] = "unknown"
    belief_owner_type: Literal["reader", "narrator", "character", "group", "unknown"] = "unknown"
    belief_owner: str = ""
    reader_visible: bool = True
    participation_type: Literal[
        "active_scene",
        "flashback",
        "memory",
        "vision",
        "letter",
        "recording",
        "historical_reference",
        "dream",
        "hallucination",
    ] = "active_scene"
    observation_type: Literal["direct", "reported", "assumed", "rumor", "historical", "vision", "dream", "flashback"] = "direct"
    status_reason: Literal["battle", "execution", "disease", "accident", "suicide", "reported", "rumor", "fake", "supernatural", "unknown"] = "unknown"
    missing_subtype: Literal["lost", "captured", "escaped", "disappeared", "unknown_location", "missing", ""] = ""
    identity_continuity_mode: Literal[
        "same_identity",
        "copy",
        "reconstructed",
        "revived",
        "reincarnated",
        "alternate_self",
        "unknown",
    ] = "unknown"
    supersedes_subject_status: str = ""
    evidence: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    story_time_text: str = ""
    event_reference: str = ""


class LegacySignalDict(BaseModel):
    subject: str
    entity_type: Literal["INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"] = "INDIVIDUAL"
    signal_type: Literal[
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
    ] = "legacy"
    evidence: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    historical_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    emotional_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    political_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    familial_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    memory_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    event_reference: str = ""

class AliasDict(BaseModel):
    canonical_name: str
    new_alias: str
    context_proof: str

class GroupAliasDict(BaseModel):
    canonical_group_name: str
    new_alias: str
    context_proof: str

class RelationshipDict(BaseModel):
    source: str
    target: str
    trust_score: int = Field(ge=-10, le=10)
    relationship_evidence: str = Field(
        description="A direct quote or literal observed interaction from the current chapter only. Do not explain causes."
    )
    event_reference: str = ""


class EventNameDict(BaseModel):
    name: str
    name_role: Literal["canonical", "public", "private", "factional", "historical", "reader", "propaganda", "retrospective"] = "public"
    name_source_type: Literal["canonical", "factional", "sarcastic", "pejorative", "commemorative", "historical", "rumor_based", "unknown"] = "unknown"
    audience_type: Literal["reader", "narrator", "character", "speaker", "faction", "public"] = "reader"
    framing_polarity: Literal["neutral", "positive", "negative", "contested"] = "neutral"
    literal_status: Literal["literal", "metaphorical", "ironic", "sarcastic", "propagandistic", "commemorative"] = "literal"
    source_entity: str = ""
    faction: str = ""
    first_known_chapter: int | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str = ""


class EventParticipantDict(BaseModel):
    name: str
    entity_type: Literal["INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"] = "INDIVIDUAL"
    role: Literal[
        "participant", "attacker", "defender", "victim", "witness", "commander",
        "organizer", "speaker", "observer", "beneficiary", "pov", "subject",
    ] = "participant"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str = ""


class EventPerspectiveDict(BaseModel):
    summary: str
    perspective_type: Literal["neutral", "reader", "speaker", "faction", "historian", "narrator"] = "neutral"
    reader_visibility: Literal["hidden", "partially_known", "fully_known"] = "partially_known"
    reliability: Literal["direct", "reported", "historical", "rumor", "legend", "myth", "unknown"] = "unknown"
    source_entity: str = ""
    faction: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str = ""


class EventRecord(BaseModel):
    summary: str
    event_type: str = "plot"
    landmark_type: Literal[
        "event", "landmark", "arc", "campaign", "operation", "battle", "incident",
        "war", "civil_war", "revolt", "uprising", "revolution", "conquest", "massacre",
        "reform", "policy_shift", "period", "era", "reign", "collapse", "occupation",
        "siege", "treaty", "ceremony", "recurring_ritual", "commemoration",
    ] = "event"
    lifecycle: Literal["candidate", "landmark", "historically_referenced", "legacy_landmark"] = "candidate"
    event_state: Literal["planned", "ongoing", "completed", "remembered", "historical", "unknown"] = "unknown"
    event_reliability: Literal["direct", "reported", "historical", "rumor", "legend", "myth", "unknown"] = "unknown"
    reader_visibility: Literal["hidden", "partially_known", "fully_known"] = "fully_known"
    event_scope: Literal["personal", "local", "regional", "planetary", "global", "cosmic", "unknown"] = "unknown"
    geographic_scope: str = "unknown"
    landmark_identity_key: str = ""
    landmark_reference: str = ""
    landmark_name: str = ""
    name_status: Literal["unnamed", "named", "retrospectively_named", "unknown"] = "unknown"
    landmark_link_type: Literal["occurrence", "subevent", "trigger", "aftermath", "commemoration", "historical_reference", "recurrence_instance"] = "occurrence"
    parent_landmark_reference: str = ""
    causal_event_reference: str = ""
    causal_relation_type: Literal["causes", "precedes", "triggers", "aftermath_of"] = "precedes"
    recurrence_template_reference: str = ""
    historical_start_text: str = ""
    historical_end_text: str = ""
    historical_start_sort: float | None = None
    historical_end_sort: float | None = None
    duration_text: str = ""
    reader_known_since_chapter: int | None = None
    story_discovery_time_text: str = ""
    story_discovery_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    boundary_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    identity_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    outcome: Literal["victory", "defeat", "stalemate", "collapse", "succession", "revolution", "unknown"] = "unknown"
    historical_memory: Literal["celebrated", "mourned", "forgotten", "rewritten", "mythologized", "controversial", "unknown"] = "unknown"
    event_functions: list[str] = Field(default_factory=list)
    landmark_names: list[EventNameDict] = Field(default_factory=list)
    participants: list[EventParticipantDict] = Field(default_factory=list)
    perspectives: list[EventPerspectiveDict] = Field(default_factory=list)
    importance: dict[str, float] = Field(default_factory=dict)
    primary_location: str = ""
    secondary_locations: list[str] = Field(default_factory=list)
    identity_evidence: str = ""
    name_evidence: str = ""

class ChapterAnalysis(BaseModel):
    pov_character_found: str = Field(
        description="The POV character's name, or '[UNNAMED_POV]' if first-person but unnamed. Use '' if none."
    )
    new_aliases_discovered: list[AliasDict]
    new_group_aliases_discovered: list[GroupAliasDict]
    entities_present: list[EntityDict]
    relationships: list[RelationshipDict]
    major_events: list[EventRecord]
    entity_semantic_relations: list[EntitySemanticRelationDict] = Field(default_factory=list)
    language_observations: list[LanguageObservationDict] = Field(default_factory=list)
    life_status_events: list[LifeStatusEvidenceDict] = Field(default_factory=list)
    legacy_signals: list[LegacySignalDict] = Field(default_factory=list)


# ─── Python Bouncer Layer ────────────────────────────────────────────────────

_RELATIONAL_PREFIXES = (
    "my ", "our ", "his ", "her ", "their ", "a ", "an ", "some ",
)

_GENERIC_ROLES = {
    "guard", "boy", "girl", "man", "woman", "friend", "voice",
    "soldier", "crew", "crowd", "people", "child", "servant", "thug", "bouncer",
    "father", "mother", "prince", "princess", "lord", "lady", "sir", "captain"
}

ACTIVE_NARRATIVE_TYPES = {"INDIVIDUAL", "GROUP", "LOCATION"}
REFERENCE_ENTITY_TYPES = {"CONCEPT_OR_LORE", "REFERENCE", "WORK_OF_ART"}


def classify_text_source(text: str, section_type: str = "CHAPTER") -> dict:
    key = re.sub(r"\s+", " ", str(text or "").lower())
    section_type = section_type or "CHAPTER"
    evidence_source_type = "observed_fact"
    actuality_status = "actual"
    confidence_delta = 0.0

    if section_type in {"FRONT_BACK_MATTER", "LORE_SUPPLEMENT"}:
        evidence_source_type = "paratext"
        actuality_status = "contextual_reference"
        confidence_delta -= 0.25
    elif any(marker in key for marker in (" dreamed ", " dreamt ", " nightmare", "vision of", "hallucinat")):
        evidence_source_type = "dreamed"
        actuality_status = "imagined"
        confidence_delta -= 0.35
    elif any(marker in key for marker in (" imagined ", " pictured ", " pretended ", "fantasized")):
        evidence_source_type = "imagined"
        actuality_status = "imagined"
        confidence_delta -= 0.35
    elif any(marker in key for marker in (" remembered ", " recalled ", " thought back", "years ago", "long ago", "once ")):
        evidence_source_type = "recalled"
        actuality_status = "recalled"
        confidence_delta -= 0.15
    elif any(marker in key for marker in (" told ", " said that", "reported ", "according to", "rumor", "rumour", "claimed ")):
        evidence_source_type = "reported"
        actuality_status = "reported"
        confidence_delta -= 0.2
    elif any(marker in key for marker in (" said", " asked", " called", " shouted", " whispered")):
        evidence_source_type = "spoken_claim"
        actuality_status = "reported"
        confidence_delta -= 0.1
    elif any(marker in key for marker in (" thought", " believed", " seemed", " felt", " suspected")):
        evidence_source_type = "narrator_belief"
        actuality_status = "perceived"
        confidence_delta -= 0.1

    story_time_text = ""
    story_time_confidence = 0.0
    for pattern in (
        r"\b(?:years?|months?|weeks?|days?)\s+(?:ago|earlier|before)\b",
        r"\b(?:later|afterward|afterwards|then|now)\b",
        r"\b(?:as a child|in childhood|that night|the next morning|the previous night)\b",
    ):
        match = re.search(pattern, key)
        if match:
            story_time_text = match.group(0)
            story_time_confidence = 0.45
            break

    return {
        "evidence_source_type": evidence_source_type,
        "actuality_status": actuality_status,
        "confidence_delta": confidence_delta,
        "story_time_text": story_time_text,
        "story_time_confidence": story_time_confidence,
    }


def is_structurally_valid(name: str) -> bool:
    if not name or not name.strip():
        return False

    name_stripped = name.strip()
    name_lower    = name_stripped.lower()

    if "[unnamed" in name_lower and name_lower != "[unnamed_pov]":
        return False

    if "'s " in name_lower or name_lower.endswith("'s") or "’s " in name_lower or name_lower.endswith("’s"):
        if name_lower.startswith(_RELATIONAL_PREFIXES):
            return False

    if name_lower.startswith(_RELATIONAL_PREFIXES):
        return False

    if name_lower.startswith("the "):
        rest = name_stripped[4:]
        if not rest or not rest[0].isupper():
            return False

    if name_lower in _GENERIC_ROLES:
        return False

    return True

def is_valid_alias(new_alias: str) -> bool:
    alias_stripped = new_alias.strip()
    if not alias_stripped:
        return False
        
    if len(alias_stripped.split()) > 3:
        return False
        
    return True


def alias_confidence(alias: str) -> float:
    alias_stripped = alias.strip()
    alias_lower = alias_stripped.lower()
    confidence = ALIAS_BASE_CONFIDENCE

    if alias_lower.startswith("the "):
        return confidence

    if alias_stripped.islower():
        confidence -= ALIAS_LOWERCASE_PENALTY

    if alias_lower in _GENERIC_ROLES:
        confidence -= ALIAS_COMMON_NOUN_PENALTY

    title_words = {"lord", "lady", "sir", "captain", "prince", "princess", "king", "queen"}
    if alias_lower in title_words:
        confidence -= ALIAS_TITLE_ONLY_PENALTY

    return max(0.05, min(1.0, confidence))

def normalize_string(name: str, is_group: bool = False) -> str:
    name = name.strip()
    if is_group:
        name = re.sub(r'(?i)\s+(caste|clan|family|tribe|house|faction|empire)$', '', name).strip()
    return name


def lookup_key(db: BookDatabase, name: str, is_group: bool = False) -> str:
    return db.normalize_alias_key(normalize_string(name, is_group=is_group))


def _ontology_from_entity(entity: dict, entity_type: str, raw_name: str, source_section_type: str) -> dict:
    ontology = {
        "entity_category": entity.get("entity_category") or "UNKNOWN",
        "species_or_kind": entity.get("species_or_kind") or "unknown",
        "sentience": entity.get("sentience") or "unknown",
        "story_role": entity.get("story_role") or entity.get("narrative_role") or "unknown",
        "functional_role": entity.get("functional_role") or "",
        "active_status": entity.get("active_status") or "uncertain",
        "identity_status": entity.get("identity_status") or "unknown",
        "entity_persistence": entity.get("entity_persistence") or "persistent",
        "can_speak": entity.get("can_speak") or "unknown",
        "can_move": entity.get("can_move") or "unknown",
        "can_think": entity.get("can_think") or "unknown",
        "can_remember": entity.get("can_remember") or "unknown",
        "can_make_decisions": entity.get("can_make_decisions") or "unknown",
        "can_form_relationships": entity.get("can_form_relationships") or "unknown",
        "literal_status": entity.get("literal_status") or "literal",
        "interpretation_status": entity.get("interpretation_status") or "actual",
        "ontology_confidence": entity.get("ontology_confidence") or 0.5,
        "ontology_evidence": entity.get("ontology_evidence") or "",
        "raw_surface_form": raw_name,
    }
    if source_section_type in {"FRONT_BACK_MATTER", "LORE_SUPPLEMENT"} and ontology["active_status"] == "uncertain":
        ontology["active_status"] = "referenced_only"
    if entity_type == "INDIVIDUAL" and ontology["entity_category"] == "UNKNOWN":
        ontology["entity_category"] = "CHARACTER"
    elif entity_type == "GROUP" and ontology["entity_category"] == "UNKNOWN":
        ontology["entity_category"] = "GROUP"
    elif entity_type == "LOCATION" and ontology["entity_category"] == "UNKNOWN":
        ontology["entity_category"] = "LOCATION"
    elif entity_type == "CONCEPT_OR_LORE" and ontology["entity_category"] == "UNKNOWN":
        ontology["entity_category"] = "REFERENCE"
    return ontology


def _routing_entity_type(entity_type: str, ontology: dict) -> str:
    category = str(ontology.get("entity_category") or "UNKNOWN").upper()
    if category == "GROUP":
        return "GROUP"
    if category == "LOCATION":
        return "LOCATION"
    if category == "CHARACTER":
        return "INDIVIDUAL"
    if category in {"OBJECT", "CONCEPT", "REFERENCE"}:
        return "CONCEPT_OR_LORE"
    return entity_type if entity_type in {"INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"} else "CONCEPT_OR_LORE"


# ─── Provider-Neutral Response Parser ───────────────────────────────────────

def parse_analysis_response(response) -> dict:
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, dict): return parsed
        if hasattr(parsed, "model_dump"): return parsed.model_dump()
        if hasattr(parsed, "dict"): return parsed.dict()

    response_text = getattr(response, "text", None)
    if response_text:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines and lines[0].startswith("```"): lines.pop(0)
            if lines and lines[-1].startswith("```"): lines.pop(-1)
            cleaned = "\n".join(lines).strip()
        try: return json.loads(cleaned)
        except json.JSONDecodeError: pass

    candidates    = getattr(response, "candidates", None) or []
    finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    safety_ratings= getattr(candidates[0], "safety_ratings", None) if candidates else None
    prompt_feedback = getattr(response, "prompt_feedback", None)
    block_reason    = getattr(prompt_feedback, "block_reason", None) if prompt_feedback else None

    if block_reason:
        raise RuntimeError(
            f"AI provider blocked this chapter. "
            f"block_reason={getattr(block_reason, 'value', block_reason)}, "
            f"usage_metadata={getattr(response, 'usage_metadata', None)}"
        )

    raise RuntimeError(
        f"AI provider returned no parseable JSON. "
        f"finish_reason={finish_reason}, safety_ratings={safety_ratings}, "
        f"prompt_feedback={prompt_feedback}"
    )


# ─── Universal Ingestion Pipeline ────────────────────────────────────────────

def build_cache_metadata(processed_at: float | None = None) -> dict:
    return {
        "cache_version": CACHE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_name": AI_CHAPTER_MODEL_NAME,
        "normalization_version": NORMALIZATION_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "bookbuddy_version": BOOKBUDDY_VERSION,
        "processed_at": processed_at or time.time(),
    }


def cache_metadata_status(payload: dict) -> dict:
    metadata = payload.get("_metadata") or {}
    expected = build_cache_metadata(processed_at=metadata.get("processed_at") or 0)
    mismatches = {
        key: {"expected": expected.get(key), "actual": metadata.get(key)}
        for key in (
            "cache_version",
            "prompt_version",
            "model_name",
            "normalization_version",
            "graph_schema_version",
        )
        if metadata.get(key) != expected.get(key)
    }
    return {
        "status": "stale" if mismatches else "current",
        "mismatches": mismatches,
        "metadata": metadata,
    }


def write_json_cache_once(chapter_file: str, payload: dict):
    if os.path.exists(chapter_file):
        raise FileExistsError(f"Refusing to overwrite immutable cache file: {chapter_file}")

    tmp_file = f"{chapter_file}.{os.getpid()}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_file, chapter_file)
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def normalize_event_record(raw_event) -> dict:
    """Adapt immutable legacy string caches to the structured event contract."""
    if isinstance(raw_event, str):
        return {
            "summary": raw_event,
            "event_type": "plot",
            "landmark_type": "event",
            "lifecycle": "candidate",
            "event_state": "unknown",
            "event_reliability": "unknown",
            "reader_visibility": "fully_known",
            "event_scope": "unknown",
            "geographic_scope": "unknown",
            "landmark_names": [],
            "participants": [],
            "perspectives": [],
            "importance": {},
            "_legacy_event": True,
        }
    if not isinstance(raw_event, dict):
        return {}
    record = dict(raw_event)
    record["summary"] = " ".join(str(record.get("summary") or record.get("event") or "").split())
    record.setdefault("event_type", "plot")
    record.setdefault("landmark_type", "event")
    record.setdefault("lifecycle", "candidate")
    record.setdefault("event_state", "unknown")
    record.setdefault("event_reliability", "unknown")
    record.setdefault("reader_visibility", "fully_known")
    record.setdefault("event_scope", "unknown")
    record.setdefault("geographic_scope", record.get("event_scope") or "unknown")
    record.setdefault("landmark_names", [])
    record.setdefault("participants", [])
    record.setdefault("perspectives", [])
    record.setdefault("importance", {})
    return record


def event_record_summary(raw_event) -> str:
    return normalize_event_record(raw_event).get("summary", "")


def ingest_ai_payload(ai_data: dict, chapter_index: int, db: BookDatabase, chapter_text: str = ""):
    with db.defer_entity_search_sync():
        return _ingest_ai_payload(ai_data, chapter_index, db, chapter_text)


def _ingest_ai_payload(ai_data: dict, chapter_index: int, db: BookDatabase, chapter_text: str = ""):
    ingest_start = time.perf_counter()
    session_id = ai_data.get("_session_id")
    title_id = ai_data.get("_title_id")
    volume_id = ai_data.get("_volume_id") or title_id
    source_section_type = ai_data.get("_section_type") or "CHAPTER"
    # This adapter only records reviewable, source-scoped observations. It does
    # not participate in entity creation, aliases, life status, landmarks, or
    # social edges.
    image_evidence_summary = ingest_image_evidence(ai_data, chapter_index, db)
    # A chapter whose only payload is image evidence has no textual narrator
    # evidence.  It may retain an already-established POV, but it must not
    # synthesize the generic unnamed narrator entity simply because replay is
    # processing that occurrence.
    image_only_payload = bool(ai_data.get("image_evidence")) and not any(
        ai_data.get(key)
        for key in (
            "pov_character_found",
            "entities_present",
            "relationships",
            "major_events",
            "new_aliases_discovered",
            "new_group_aliases_discovered",
            "entity_semantic_relations",
            "language_observations",
            "life_status_events",
            "legacy_signals",
        )
    )
    db.stamp_local_chapter_boundary(
        chapter_index,
        title_id=title_id,
        book_id=title_id,
        volume_id=volume_id,
        session_id=session_id,
    )

    char_alias_to_id,  char_id_to_canon  = db.get_resolution_matrices("INDIVIDUAL")
    group_alias_to_id, group_id_to_canon = db.get_resolution_matrices("GROUP")
    loc_alias_to_id,   loc_id_to_canon   = db.get_resolution_matrices("LOCATION")
    lore_alias_to_id,  lore_id_to_canon  = db.get_resolution_matrices("CONCEPT_OR_LORE")

    def _maps_for_entity_type(entity_type: str):
        if entity_type == "GROUP":
            return group_alias_to_id, group_id_to_canon
        if entity_type == "LOCATION":
            return loc_alias_to_id, loc_id_to_canon
        if entity_type == "CONCEPT_OR_LORE":
            return lore_alias_to_id, lore_id_to_canon
        return char_alias_to_id, char_id_to_canon

    def _resolve_active_entity(
        name: str,
        preferred_type: str | None = None,
        allow_cross_type: bool = False,
    ) -> tuple[int | None, str | None, str | None]:
        candidate_types = [preferred_type] if preferred_type in {"INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"} else []
        if allow_cross_type or not candidate_types:
            candidate_types.extend(entity_type for entity_type in ("INDIVIDUAL", "GROUP", "LOCATION") if entity_type not in candidate_types)
        for entity_type in candidate_types:
            resolution = db.resolve_entity_reference(
                normalize_string(name, entity_type == "GROUP"),
                entity_type,
                chapter_index,
                boundary_title_id=title_id,
                boundary_book_id=title_id,
                boundary_volume_id=volume_id,
                session_id=session_id,
            )
            if resolution.get("state") == "resolved" and resolution.get("entity_id"):
                return resolution["entity_id"], resolution.get("canonical_name"), entity_type
        return None, None, None

    def _resolve_any_entity(name: str, preferred_type: str | None = None) -> tuple[int | None, str | None, str | None]:
        entity_id, canonical, entity_type = _resolve_active_entity(name, preferred_type, allow_cross_type=True)
        if entity_id:
            return entity_id, canonical, entity_type
        resolution = db.resolve_entity_reference(
            normalize_string(name),
            "CONCEPT_OR_LORE",
            chapter_index,
            boundary_title_id=title_id,
            boundary_book_id=title_id,
            boundary_volume_id=volume_id,
            session_id=session_id,
        )
        if resolution.get("state") == "resolved" and resolution.get("entity_id"):
            return resolution["entity_id"], resolution.get("canonical_name"), "CONCEPT_OR_LORE"
        return None, None, None

    pov_found = ai_data.get("pov_character_found")
    current_pov_id = None
    norm_pov = lookup_key(db, pov_found) if pov_found else "unnamed_pov"
    prev_pov_id = db.get_pov_for_chapter(chapter_index - 1)

    if image_only_payload:
        current_pov_id = prev_pov_id
    elif norm_pov == "unnamed_pov" and prev_pov_id:
        current_pov_id = prev_pov_id
        db.set_pov_for_chapter(
            chapter_index,
            current_pov_id,
            narrator_type="carried_forward",
            narrator_confidence=0.45,
            source_evidence="Unnamed POV carried from previous chapter.",
            scene_scope=f"chapter:{chapter_index}",
        )
    else:
        if norm_pov == "unnamed_pov":
            if "unnamed_pov" not in char_alias_to_id:
                new_id = db.add_entity("[UNNAMED_POV]", "INDIVIDUAL", chapter_index)
                char_alias_to_id["unnamed_pov"] = new_id
                char_id_to_canon[new_id] = "[UNNAMED_POV]"
            current_pov_id = char_alias_to_id["unnamed_pov"]
        else:
            current_pov_id, pov_canonical, _pov_type = _resolve_active_entity(pov_found, "INDIVIDUAL")
            if current_pov_id and pov_canonical:
                char_alias_to_id[norm_pov] = current_pov_id
                char_id_to_canon[current_pov_id] = pov_canonical
            if not current_pov_id:
                current_pov_id = db.add_entity(
                    normalize_string(pov_found),
                    "INDIVIDUAL",
                    chapter_index,
                    boundary_title_id=title_id,
                    boundary_book_id=title_id,
                    boundary_volume_id=volume_id,
                    session_id=session_id,
                    source_session=session_id,
                    inherited_confidence=1.0,
                )
                char_alias_to_id[norm_pov] = current_pov_id
                char_id_to_canon[current_pov_id] = normalize_string(pov_found)

        narrator_type = "unnamed_first_person" if norm_pov == "unnamed_pov" else "explicit_pov"
        db.set_pov_for_chapter(
            chapter_index,
            current_pov_id,
            narrator_type=narrator_type,
            narrator_confidence=0.65 if norm_pov == "unnamed_pov" else 0.9,
            source_evidence=str(pov_found or ""),
            scene_scope=f"chapter:{chapter_index}",
        )

        if pov_found and pov_found != "[UNNAMED_POV]":
            if promote_named_pov(db, current_pov_id, chapter_index, f"POV resolved as {pov_found}"):
                char_alias_to_id, char_id_to_canon = db.get_resolution_matrices("INDIVIDUAL")

    pov_canon_name = char_id_to_canon.get(current_pov_id, "[UNNAMED_POV]")
    narrator_scope = "first_person" if norm_pov == "unnamed_pov" else ("pov_limited" if current_pov_id else "unknown")
    db.set_chapter_visibility_scope(
        chapter_index,
        observed_by_entity_id=current_pov_id,
        narrator_entity_id=current_pov_id,
        narrator_scope=narrator_scope,
        scene_scope=f"chapter:{chapter_index}",
        confidence=0.75 if current_pov_id else 0.0,
        source_evidence=str(pov_found or ""),
    )
    index_ai_mentions(db, ai_data, chapter_index, chapter_text)
    event_payloads = [normalize_event_record(raw_event) for raw_event in ai_data.get("major_events", [])]

    participation_roles_by_surface: dict[str, set[str]] = {}
    chapter_entity_ids: list[int] = []

    def _add_participation_role(surface: str, role: str):
        key = db.normalize_alias_key(surface)
        if key and role:
            participation_roles_by_surface.setdefault(key, set()).add(role)

    def _remember_chapter_entity(entity_id: int | None):
        if entity_id and entity_id not in chapter_entity_ids:
            chapter_entity_ids.append(entity_id)

    if pov_found and pov_found != "[UNNAMED_POV]":
        _add_participation_role(pov_found, "pov")
    for rel in ai_data.get("relationships", []):
        _add_participation_role(rel.get("source", ""), "relationship")
        _add_participation_role(rel.get("target", ""), "relationship")
    for event_record in event_payloads:
        event_key = db.normalize_alias_key(event_record.get("summary", ""))
        for entity in ai_data.get("entities_present", []):
            surface = entity.get("name", "")
            surface_key = db.normalize_alias_key(surface)
            if surface_key and re.search(rf"\b{re.escape(surface_key)}\b", event_key):
                _add_participation_role(surface, "event")

    filtered_entities = []
    for entity in ai_data.get("entities_present", []):
        raw_name = entity.get("name", "")
        e_type   = entity.get("entity_type", "")
        ontology = _ontology_from_entity(entity, e_type, raw_name, source_section_type)
        e_type = _routing_entity_type(e_type, ontology)
        ontology = db.normalize_entity_ontology(ontology, e_type, raw_name)

        norm_name = normalize_string(raw_name, e_type == "GROUP")
        classification = db.classify_mention_surface(norm_name, e_type)
        mention_context = chapter_text

        if e_type in REFERENCE_ENTITY_TYPES and ontology.get("entity_category") in {"REFERENCE", "CONCEPT"}:
            db.record_reference_mention(
                norm_name,
                chapter_index,
                entity_type_guess=e_type,
                context_text=mention_context,
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
                source_section_type=source_section_type,
            )
            db.record_unresolved_mention(
                norm_name,
                e_type,
                chapter_index,
                confidence=0.0,
                ambiguous=False,
                reason="contextual_reference_not_active_narrative_entity",
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
            continue

        if raw_name == "[UNNAMED_POV]":
            raw_name = pov_canon_name

        is_grp = (e_type == "GROUP")
        is_loc = (e_type == "LOCATION")

        norm_name  = normalize_string(raw_name, is_grp)
        lower_name = db.normalize_alias_key(norm_name)
        classification = db.classify_mention_surface(norm_name, e_type)
        resolution = {"state": "unresolved", "candidates": [], "score": 0.0, "margin": 0.0}
        quarantine_reference_class = (
            classification["mention_class"] in {"kinship", "title"}
            or (
                classification["mention_class"] == "reference"
                and ontology.get("entity_category") not in {"OBJECT", "CHARACTER", "GROUP", "LOCATION"}
            )
        )
        if quarantine_reference_class:
            db.record_reference_mention(
                norm_name,
                chapter_index,
                entity_type_guess=e_type,
                context_text=mention_context,
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
                source_section_type=source_section_type,
            )
            db.record_unresolved_mention(
                norm_name,
                e_type,
                chapter_index,
                confidence=0.0,
                ambiguous=True,
                reason=f"{classification['mention_class']}_requires_contextual_resolution",
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
            if classification["mention_class"] == "kinship":
                db.record_kinship_mention(
                    norm_name,
                    chapter_index,
                    narrator_entity_id=current_pov_id,
                    evidence=chapter_text[:300],
                )
            continue

        if not is_structurally_valid(raw_name) and classification["mention_class"] != "group":
            continue

        should_promote, participation = db.should_promote_mention_to_active_entity(
            norm_name,
            e_type,
            chapter_index,
            context_text=mention_context,
            evidence_roles=sorted(participation_roles_by_surface.get(lower_name, set())),
            ontology=ontology,
        )
        if not should_promote:
            db.record_reference_mention(
                norm_name,
                chapter_index,
                entity_type_guess=e_type,
                context_text=mention_context,
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
                source_section_type=source_section_type,
            )
            db.record_unresolved_mention(
                norm_name,
                e_type,
                chapter_index,
                confidence=max(0.0, participation.get("net_score", 0.0)),
                ambiguous=False,
                reason="insufficient_narrative_participation",
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
            continue

        scoped_entity_id, scoped_canonical, scoped_type = _resolve_active_entity(norm_name, e_type)
        if scoped_entity_id:
            entity_id = scoped_entity_id
            e_type = scoped_type or e_type
            is_grp = e_type == "GROUP"
            is_loc = e_type == "LOCATION"
            target_map, target_reverse = _maps_for_entity_type(e_type)
            target_map[lower_name] = entity_id
            target_reverse[entity_id] = scoped_canonical or norm_name
            db.update_entity_verification(entity_id, chapter_index)
        elif is_loc and lower_name in loc_alias_to_id:
            e_type, is_grp, is_loc = "LOCATION", False, True
            target_map = loc_alias_to_id
            target_reverse = loc_id_to_canon
            entity_id = target_map[lower_name]
            db.update_entity_verification(entity_id, chapter_index)
        elif is_grp and lower_name in group_alias_to_id:
            e_type, is_grp, is_loc = "GROUP", True, False
            target_map = group_alias_to_id
            target_reverse = group_id_to_canon
            entity_id = target_map[lower_name]
            db.update_entity_verification(entity_id, chapter_index)
        elif e_type == "INDIVIDUAL" and lower_name in char_alias_to_id:
            e_type, is_grp, is_loc = "INDIVIDUAL", False, False
            target_map = char_alias_to_id
            target_reverse = char_id_to_canon
            entity_id = target_map[lower_name]
            db.update_entity_verification(entity_id, chapter_index)
        elif e_type == "CONCEPT_OR_LORE" and lower_name in lore_alias_to_id:
            target_map = lore_alias_to_id
            target_reverse = lore_id_to_canon
            entity_id = target_map[lower_name]
            db.update_entity_verification(entity_id, chapter_index)
        else:
            target_map, target_reverse = _maps_for_entity_type(e_type)
            resolution = db.resolve_entity_reference(
                norm_name,
                e_type,
                chapter_index,
                boundary_title_id=title_id,
                boundary_book_id=title_id,
                boundary_volume_id=volume_id,
                session_id=session_id,
            )
            entity_id = resolution.get("entity_id") if resolution.get("state") == "resolved" else None
        if not entity_id:
            entity_id, resolution_state = db.resolve_or_create_entity(
                norm_name,
                e_type,
                chapter_index,
                boundary_title_id=title_id,
                boundary_book_id=title_id,
                boundary_volume_id=volume_id,
                session_id=session_id,
                source_session=session_id,
                inherited_confidence=1.0,
                ontology=ontology,
            )
            if not entity_id:
                db.record_conflict(
                    "ambiguous_unresolved_mention",
                    chapter_index,
                    {
                        "mention": norm_name,
                        "entity_type": e_type,
                        "resolution_state": resolution_state,
                        "candidates": resolution.get("candidates", [])[:5],
                        "score": resolution.get("score", 0.0),
                        "margin": resolution.get("margin", 0.0),
                    },
                )
                continue
            target_map[lower_name] = entity_id
            target_reverse[entity_id] = norm_name
        if entity_id:
            db.update_entity_ontology(
                entity_id,
                ontology,
                chapter_idx=chapter_index,
                confidence=ontology.get("ontology_confidence", 0.5),
                source_text=ontology.get("ontology_evidence") or chapter_text[:500],
                ontology_source="LLM",
                reason="chapter entity extraction",
            )
        if entity_id not in target_reverse:
            db.update_entity_verification(entity_id, chapter_index)
            target_map[lower_name] = entity_id
            if resolution.get("canonical_name"):
                target_reverse[entity_id] = resolution["canonical_name"]
            else:
                target_reverse[entity_id] = norm_name

        if e_type in {"INDIVIDUAL", "GROUP"}:
            for derived_alias in db.discover_aliases_from_canonical(entity_id, chapter_index):
                target_map[db.normalize_alias_key(derived_alias)] = entity_id

        _remember_chapter_entity(entity_id)
        ent_dict = {"name": target_reverse[entity_id], "entity_type": e_type}
        if ent_dict not in filtered_entities:
            filtered_entities.append(ent_dict)

    ai_data["entities_present"] = filtered_entities

    for semantic_relation in ai_data.get("entity_semantic_relations", []):
        source_name = semantic_relation.get("source", "")
        target_name = semantic_relation.get("target", "")
        relation_type = semantic_relation.get("relation_type", "")
        if not source_name or not relation_type:
            continue
        source_id, _source_canon, _source_type = _resolve_any_entity(source_name)
        target_id, _target_canon, _target_type = _resolve_any_entity(target_name) if target_name else (None, None, None)
        db.record_entity_semantic_relation(
            source_id,
            target_id,
            relation_type=relation_type,
            source_surface=source_name,
            target_surface=target_name,
            chapter_idx=chapter_index,
            confidence=semantic_relation.get("confidence", 0.55),
            source_text=semantic_relation.get("source_evidence", ""),
            ontology_source="LLM",
        )

    for language_observation in ai_data.get("language_observations", []):
        db.record_language_observation(
            language_observation.get("surface_text", ""),
            chapter_idx=chapter_index,
            language=language_observation.get("language", "unknown"),
            writing_system=language_observation.get("writing_system", "unknown"),
            translation_status=language_observation.get("translation_status", "unknown"),
            decoder_source=language_observation.get("decoder_source", ""),
            confidence=language_observation.get("confidence", 0.5),
            source_section_type=source_section_type,
            source_quote=language_observation.get("source_evidence", ""),
        )

    for alias_obj in ai_data.get("new_aliases_discovered", []):
        canon_raw = alias_obj.get("canonical_name", "")
        new_nick_raw = alias_obj.get("new_alias", "")

        if not is_structurally_valid(canon_raw) or not new_nick_raw.strip() or not is_valid_alias(new_nick_raw):
            continue  

        canon_lower = lookup_key(db, canon_raw)
        target_id   = char_alias_to_id.get(canon_lower)
        if not target_id: continue

        new_nick   = normalize_string(new_nick_raw)
        nick_lower = db.normalize_alias_key(new_nick)
        evidence = alias_obj.get("context_proof", "Rebuild Sync")

        validation = validate_alias(db, target_id, canon_raw, new_nick, chapter_index, evidence)
        if validation.status == TITLE_LINK:
            maybe_add_title_link(db, target_id, new_nick, chapter_index, evidence, validation)
            continue
        if validation.status == CONFLICT:
            db.record_conflict(
                "alias_collision",
                chapter_index,
                {
                    "alias": new_nick,
                    "canonical_name": canon_raw,
                    "target_entity_id": target_id,
                    "evidence": evidence,
                    "reason": validation.reason,
                },
                target_id,
            )
            continue
        if validation.status == REJECTED:
            db.record_conflict(
                "alias_rejected",
                chapter_index,
                {
                    "alias": new_nick,
                    "canonical_name": canon_raw,
                    "target_entity_id": target_id,
                    "evidence": evidence,
                    "reason": validation.reason,
                },
                target_id,
            )
            continue

        existing_id = char_alias_to_id.get(nick_lower)
        if existing_id and existing_id != target_id:
            db.record_conflict(
                "alias_collision",
                chapter_index,
                {
                    "alias": new_nick,
                    "canonical_name": canon_raw,
                    "existing_entity_id": existing_id,
                    "target_entity_id": target_id,
                    "evidence": alias_obj.get("context_proof", ""),
                },
                target_id,
                existing_id,
            )
            continue

        alias_status = db.add_alias(
            target_id,
            new_nick,
            chapter_index,
            evidence,
            max(0.05, alias_confidence(new_nick) + validation.confidence_delta),
            validation_status=validation.status,
            validation_reason=validation.reason,
            initial_status="review" if validation.status == NEEDS_REVIEW else "candidate",
        )
        if alias_status != "rejected":
            char_alias_to_id[nick_lower] = target_id

    for g_alias in ai_data.get("new_group_aliases_discovered", []):
        canon_raw = g_alias.get("canonical_group_name", "")
        new_nick_raw = g_alias.get("new_alias", "")

        if not is_structurally_valid(canon_raw) or not new_nick_raw.strip() or not is_valid_alias(new_nick_raw):
            continue

        canon_lower = lookup_key(db, canon_raw, is_group=True)
        target_id   = group_alias_to_id.get(canon_lower)
        if not target_id: continue

        new_nick   = normalize_string(new_nick_raw, is_group=True)
        nick_lower = db.normalize_alias_key(new_nick)
        evidence = g_alias.get("context_proof", "Rebuild Sync")

        validation = validate_alias(db, target_id, canon_raw, new_nick, chapter_index, evidence)
        if validation.status == TITLE_LINK:
            maybe_add_title_link(db, target_id, new_nick, chapter_index, evidence, validation)
            continue
        if validation.status == CONFLICT:
            db.record_conflict(
                "alias_collision",
                chapter_index,
                {
                    "alias": new_nick,
                    "canonical_group_name": canon_raw,
                    "target_entity_id": target_id,
                    "evidence": evidence,
                    "reason": validation.reason,
                },
                target_id,
            )
            continue
        if validation.status == REJECTED:
            db.record_conflict(
                "alias_rejected",
                chapter_index,
                {
                    "alias": new_nick,
                    "canonical_group_name": canon_raw,
                    "target_entity_id": target_id,
                    "evidence": evidence,
                    "reason": validation.reason,
                },
                target_id,
            )
            continue

        existing_id = group_alias_to_id.get(nick_lower)
        if existing_id and existing_id != target_id:
            db.record_conflict(
                "alias_collision",
                chapter_index,
                {
                    "alias": new_nick,
                    "canonical_group_name": canon_raw,
                    "existing_entity_id": existing_id,
                    "target_entity_id": target_id,
                    "evidence": g_alias.get("context_proof", ""),
                },
                target_id,
                existing_id,
            )
            continue

        alias_status = db.add_alias(
            target_id,
            new_nick,
            chapter_index,
            evidence,
            max(0.05, alias_confidence(new_nick) + validation.confidence_delta),
            validation_status=validation.status,
            validation_reason=validation.reason,
            initial_status="review" if validation.status == NEEDS_REVIEW else "candidate",
        )
        if alias_status != "rejected" and validation.status == TRUE_ALIAS:
            group_alias_to_id[nick_lower] = target_id

    landmark_resolver = LandmarkResolver(db)
    event_records = []
    previous_event_id = None
    for event_order, event_record in enumerate(event_payloads, start=1):
        event_summary = event_record.get("summary", "")
        if not event_summary:
            continue
        event_id = add_event_with_cluster(
            db,
            chapter_index,
            event_summary,
            event_order,
            event_type=event_record.get("event_type", "plot"),
            source_payload={"major_event": event_record},
            observed_by_entity_id=current_pov_id,
            narrator_entity_id=current_pov_id,
            narrator_scope=narrator_scope,
            scene_scope=f"chapter:{chapter_index}",
            evidence_source_type=(event_source := classify_text_source(event_summary, source_section_type))["evidence_source_type"],
            actuality_status=event_source["actuality_status"],
            narrative_order=event_order,
            story_time_text=event_source["story_time_text"],
            story_time_confidence=event_source["story_time_confidence"],
            source_section_type=source_section_type,
            confidence=max(0.1, RELATIONSHIP_BASE_CONFIDENCE + event_source["confidence_delta"]),
            boundary_title_id=title_id,
            boundary_book_id=title_id,
            boundary_volume_id=volume_id,
            session_id=session_id,
            source_session=session_id,
            inherited_confidence=1.0,
        )
        if not event_id:
            continue
        if previous_event_id:
            db.add_event_causal_edge(previous_event_id, event_id, relation_type="precedes", confidence=0.55)
        if event_record.get("causal_event_reference"):
            causal_parent_id = db.find_latest_event_for_landmark_reference(event_record["causal_event_reference"])
            if causal_parent_id and causal_parent_id != event_id:
                db.add_event_causal_edge(
                    causal_parent_id,
                    event_id,
                    relation_type=event_record.get("causal_relation_type", "causes"),
                    confidence=event_record.get("identity_confidence", 0.5),
                )
        previous_event_id = event_id
        landmark_id, _resolution = landmark_resolver.resolve_or_create(
            event_record,
            event_id,
            chapter_index,
            source_session=session_id,
        )
        landmark_is_direct = landmark_id and event_record.get("landmark_link_type", "occurrence") not in {
            "commemoration", "historical_reference", "recurrence_instance",
        }
        if landmark_id and event_record.get("parent_landmark_reference"):
            parent_ids = db.find_landmarks_by_reference(event_record["parent_landmark_reference"])
            if len(parent_ids) == 1:
                db.add_landmark_hierarchy(
                    parent_ids[0],
                    landmark_id,
                    relation_type="contains",
                    confidence=event_record.get("identity_confidence", 0.5),
                    evidence=event_record.get("identity_evidence") or event_summary,
                )
        event_records.append({
            "event_id": event_id,
            "summary": event_summary,
            "landmark_id": landmark_id,
            "record": event_record,
        })

        normalized_event = db.normalize_alias_key(event_summary)
        seen_participants = set()
        for participant in event_record.get("participants", []):
            if not isinstance(participant, dict):
                continue
            participant_name = participant.get("name", "")
            entity_id, _canonical, _entity_type = _resolve_active_entity(
                participant_name,
                participant.get("entity_type") or "INDIVIDUAL",
                allow_cross_type=True,
            )
            if not entity_id:
                continue
            role = participant.get("role") or "participant"
            seen_participants.add(entity_id)
            db.add_event_participant(
                event_id,
                entity_id,
                role=role,
                confidence=participant.get("confidence", 0.5),
                observed_by_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
            if landmark_is_direct:
                db.add_landmark_participant(
                    landmark_id,
                    entity_id,
                    role=role,
                    source_event_id=event_id,
                    confidence=participant.get("confidence", 0.5),
                    evidence=participant.get("evidence", ""),
                )
        for entity in filtered_entities:
            entity_name = entity.get("name", "")
            alias_key = db.normalize_alias_key(entity_name)
            if not alias_key or len(alias_key) <= 2 or not re.search(rf"\b{re.escape(alias_key)}\b", normalized_event):
                continue
            entity_id, _canonical, _entity_type = _resolve_active_entity(entity_name, entity.get("entity_type"))
            if entity_id:
                db.add_event_participant(
                    event_id,
                    entity_id,
                    observed_by_entity_id=current_pov_id,
                    scene_scope=f"chapter:{chapter_index}",
                )
                if landmark_is_direct and entity_id not in seen_participants:
                    db.add_landmark_participant(
                        landmark_id,
                        entity_id,
                        source_event_id=event_id,
                        confidence=0.5,
                        evidence=event_summary,
                    )
        if landmark_is_direct:
            for location_name, location_role in (
                [(event_record.get("primary_location", ""), "primary")]
                + [(name, "secondary") for name in event_record.get("secondary_locations", [])]
            ):
                location_id, _canonical, _entity_type = _resolve_active_entity(
                    location_name,
                    "LOCATION",
                    allow_cross_type=True,
                )
                if location_id:
                    db.add_landmark_location(
                        landmark_id,
                        location_id,
                        location_role=location_role,
                        confidence=event_record.get("identity_confidence", 0.5),
                        evidence=event_summary,
                    )

    def _match_event_id(src_name: str, tgt_name: str, evidence: str, event_reference: str = "") -> int | None:
        if not event_records:
            return None
        if event_reference:
            reference_ids = db.find_landmarks_by_reference(event_reference)
            if len(reference_ids) == 1:
                for event_record in event_records:
                    if event_record.get("landmark_id") == reference_ids[0]:
                        return event_record["event_id"]
        src_key = db.normalize_alias_key(src_name)
        tgt_key = db.normalize_alias_key(tgt_name)
        evidence_key = db.normalize_alias_key(evidence)
        fallback = None
        for event_record in event_records:
            event_id = event_record["event_id"]
            event_summary = event_record["summary"]
            event_key = db.normalize_alias_key(event_summary)
            src_hit = src_key and re.search(rf"\b{re.escape(src_key)}\b", event_key)
            tgt_hit = tgt_key and re.search(rf"\b{re.escape(tgt_key)}\b", event_key)
            if src_hit and tgt_hit:
                return event_id
            if src_hit or tgt_hit:
                fallback = fallback or event_id
            if evidence_key and (evidence_key in event_key or event_key in evidence_key):
                fallback = fallback or event_id
        if fallback:
            return fallback
        return event_records[0]["event_id"] if len(event_records) == 1 else None

    def _resolve_or_create_status_subject(name: str, preferred_type: str = "INDIVIDUAL") -> tuple[int | None, str | None, str | None]:
        if not name or not is_structurally_valid(name):
            return None, None, None
        preferred_type = preferred_type if preferred_type in {"INDIVIDUAL", "GROUP", "LOCATION", "CONCEPT_OR_LORE"} else "INDIVIDUAL"
        normalized = normalize_string(name, preferred_type == "GROUP")
        entity_id, canonical, entity_type = _resolve_any_entity(normalized, preferred_type)
        if entity_id:
            return entity_id, canonical, entity_type
        entity_id, resolution_state = db.resolve_or_create_entity(
            normalized,
            preferred_type,
            chapter_index,
            boundary_title_id=title_id,
            boundary_book_id=title_id,
            boundary_volume_id=volume_id,
            session_id=session_id,
            source_session=session_id,
            inherited_confidence=1.0,
            ontology=db.default_entity_ontology(preferred_type, normalized),
        )
        if not entity_id:
            db.record_conflict(
                "life_status_subject_unresolved",
                chapter_index,
                {"subject": name, "entity_type": preferred_type, "resolution_state": resolution_state},
                severity=4,
            )
            return None, None, None
        target_map, target_reverse = _maps_for_entity_type(preferred_type)
        target_map[db.normalize_alias_key(normalized)] = entity_id
        target_reverse[entity_id] = normalized
        return entity_id, normalized, preferred_type

    def _resolve_belief_owner(owner_name: str, owner_type: str) -> int | None:
        if not owner_name or owner_type not in {"character", "group", "narrator"}:
            return current_pov_id if owner_type == "narrator" else None
        preferred = "GROUP" if owner_type == "group" else "INDIVIDUAL"
        owner_id, _owner_canon, _owner_type = _resolve_any_entity(owner_name, preferred)
        return owner_id

    def _latest_superseded_status_id(entity_id: int, status_hint: str) -> int | None:
        hint = db.normalize_alias_key(status_hint)
        if not hint:
            return None
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id
                FROM life_status_evidence
                WHERE entity_id = ?
                  AND (
                    actual_status = ?
                    OR belief_status = ?
                    OR appearance_status = ?
                    OR status_reason = ?
                  )
                ORDER BY COALESCE(chapter, 0) DESC, id DESC
                LIMIT 1
            """, (entity_id, hint, hint, hint, hint))
            row = cursor.fetchone()
            return row[0] if row else None

    def _identity_audit_links(entity_id: int, identity_mode: str) -> tuple[int | None, int | None]:
        if identity_mode in {"unknown", "same_identity", "revived"}:
            return None, None
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id
                FROM identity_resolution_evidence
                WHERE source_entity_id = ? OR target_entity_id = ?
                ORDER BY COALESCE(chapter, 0) DESC, id DESC
                LIMIT 1
            """, (entity_id, entity_id))
            identity_row = cursor.fetchone()
            cursor.execute("""
                SELECT id
                FROM aliases
                WHERE entity_id = ?
                  AND (
                    lower(COALESCE(evidence, '')) LIKE '%conceal%'
                    OR lower(COALESCE(evidence, '')) LIKE '%fake%'
                    OR lower(COALESCE(validation_reason, '')) LIKE '%conceal%'
                  )
                ORDER BY COALESCE(last_seen, chapter_found, 0) DESC, id DESC
                LIMIT 1
            """, (entity_id,))
            alias_row = cursor.fetchone()
            return (identity_row[0] if identity_row else None, alias_row[0] if alias_row else None)

    for status_order, status_event in enumerate(ai_data.get("life_status_events", []), start=1):
        subject = status_event.get("subject", "")
        entity_id, canonical, entity_type = _resolve_or_create_status_subject(
            subject,
            status_event.get("entity_type") or "INDIVIDUAL",
        )
        if not entity_id:
            continue
        evidence = status_event.get("evidence", "")
        event_id = _match_event_id(canonical or subject, "", evidence, status_event.get("event_reference", ""))
        source_info = classify_text_source(evidence, source_section_type)
        belief_owner_type = status_event.get("belief_owner_type") or "unknown"
        belief_owner_id = _resolve_belief_owner(status_event.get("belief_owner", ""), belief_owner_type)
        supersedes_id = _latest_superseded_status_id(entity_id, status_event.get("supersedes_subject_status", ""))
        identity_mode = status_event.get("identity_continuity_mode", "unknown")
        identity_evidence_id, concealment_alias_id = _identity_audit_links(entity_id, identity_mode)
        db.record_life_status_evidence(
            entity_id,
            subject_surface=subject,
            chapter_idx=chapter_index,
            linked_event_id=event_id,
            supersedes_evidence_id=supersedes_id,
            actual_status=status_event.get("actual_status", "unknown"),
            belief_status=status_event.get("belief_status", "unknown"),
            appearance_status=status_event.get("appearance_status", "unknown"),
            belief_owner_type=belief_owner_type,
            belief_owner_entity_id=belief_owner_id,
            reader_visible=bool(status_event.get("reader_visible", True)),
            participation_type=status_event.get("participation_type", "active_scene"),
            observation_type=status_event.get("observation_type") or source_info["evidence_source_type"],
            status_reason=status_event.get("status_reason", "unknown"),
            missing_subtype=status_event.get("missing_subtype") or None,
            identity_continuity_mode=identity_mode,
            identity_evidence_id=identity_evidence_id,
            concealment_alias_id=concealment_alias_id,
            confidence=status_event.get("confidence", 0.5),
            story_time_text=status_event.get("story_time_text") or source_info["story_time_text"],
            story_time_confidence=source_info["story_time_confidence"],
            narrative_order=status_order,
            timeline_position=float(chapter_index) + (status_order / 1000.0),
            evidence_text=evidence,
            evidence_source_type=source_info["evidence_source_type"],
            actuality_status=source_info["actuality_status"],
            source_pov_id=current_pov_id,
            source_speaker_id=belief_owner_id or current_pov_id,
            narrator_entity_id=current_pov_id,
            scene_scope=f"chapter:{chapter_index}",
            source_section_type=source_section_type,
            boundary_title_id=title_id,
            boundary_book_id=title_id,
            boundary_volume_id=volume_id,
            session_id=session_id,
            source_session=session_id,
            inherited_confidence=1.0,
        )
        _remember_chapter_entity(entity_id)
        if event_id:
            db.add_event_participant(
                event_id,
                entity_id,
                observed_by_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )

    for legacy_signal in ai_data.get("legacy_signals", []):
        subject = legacy_signal.get("subject", "")
        preferred_type = legacy_signal.get("entity_type") or "INDIVIDUAL"
        entity_id, canonical, _entity_type = _resolve_any_entity(subject, preferred_type)
        if not entity_id:
            db.record_reference_mention(
                normalize_string(subject, preferred_type == "GROUP"),
                chapter_index,
                entity_type_guess=preferred_type,
                context_text=legacy_signal.get("evidence", ""),
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
                source_section_type=source_section_type,
            )
            db.record_unresolved_mention(
                normalize_string(subject, preferred_type == "GROUP"),
                preferred_type,
                chapter_index,
                confidence=legacy_signal.get("confidence", 0.5),
                ambiguous=True,
                reason="legacy_signal_requires_existing_entity",
                narrator_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
            continue
        evidence = legacy_signal.get("evidence", "")
        event_id = _match_event_id(canonical or subject, "", evidence, legacy_signal.get("event_reference", ""))
        db.record_legacy_signal(
            entity_id,
            subject_surface=subject,
            signal_type=legacy_signal.get("signal_type", "legacy"),
            chapter_idx=chapter_index,
            evidence_text=evidence,
            confidence=legacy_signal.get("confidence", 0.5),
            historical_importance=legacy_signal.get("historical_importance", 0.0),
            emotional_importance=legacy_signal.get("emotional_importance", 0.0),
            political_importance=legacy_signal.get("political_importance", 0.0),
            familial_importance=legacy_signal.get("familial_importance", 0.0),
            memory_strength=legacy_signal.get("memory_strength", 0.0),
            linked_event_id=event_id,
            source_pov_id=current_pov_id,
            source_speaker_id=current_pov_id,
            narrator_entity_id=current_pov_id,
            scene_scope=f"chapter:{chapter_index}",
            source_section_type=source_section_type,
            boundary_title_id=title_id,
            boundary_book_id=title_id,
            boundary_volume_id=volume_id,
            session_id=session_id,
            source_session=session_id,
            inherited_confidence=1.0,
        )
        _remember_chapter_entity(entity_id)

    for rel in ai_data.get("relationships", []):
        src = rel["source"]
        tgt = rel["target"]

        if src == "[UNNAMED_POV]": src = pov_canon_name
        if tgt == "[UNNAMED_POV]": tgt = pov_canon_name

        if not is_structurally_valid(src) or not is_structurally_valid(tgt):
            continue

        src_id, src_canon, src_type = _resolve_active_entity(src, allow_cross_type=True)
        tgt_id, tgt_canon, tgt_type = _resolve_active_entity(tgt, allow_cross_type=True)

        if not src_id or not tgt_id or src_id == tgt_id: continue
        _remember_chapter_entity(src_id)
        _remember_chapter_entity(tgt_id)

        def _canon(eid: int) -> str | None:
            return (char_id_to_canon.get(eid) or group_id_to_canon.get(eid) or loc_id_to_canon.get(eid))

        rel["source"] = src_canon or _canon(src_id)
        rel["target"] = tgt_canon or _canon(tgt_id)
        evidence = rel.get("relationship_evidence") or rel.get("observed_interaction") or rel.get("reason", "")
        event_id = _match_event_id(rel["source"], rel["target"], evidence, rel.get("event_reference", ""))
        if event_id:
            db.add_event_participant(
                event_id,
                src_id,
                observed_by_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
            db.add_event_participant(
                event_id,
                tgt_id,
                observed_by_entity_id=current_pov_id,
                scene_scope=f"chapter:{chapter_index}",
            )
        evidence_source = classify_text_source(evidence, source_section_type)
        evidence_source_type = evidence_source["evidence_source_type"]
        db.add_relationship_event(
            src_id,
            tgt_id,
            chapter_index,
            rel["trust_score"],
            evidence,
            confidence=max(0.1, RELATIONSHIP_BASE_CONFIDENCE + evidence_source["confidence_delta"]),
            event_id=event_id,
            consequence_description=rel.get("reason") or rel.get("relationship_summary") or None,
            reason=rel.get("reason") or rel.get("relationship_summary"),
            source_pov_id=current_pov_id,
            source_speaker_id=current_pov_id,
            scene_scope=f"chapter:{chapter_index}",
            evidence_source_type=evidence_source_type,
            boundary_title_id=title_id,
            boundary_book_id=title_id,
            boundary_volume_id=volume_id,
            session_id=session_id,
            source_session=session_id,
            inherited_confidence=1.0,
        )
    db.record_chapter_social_context(
        chapter_entity_ids,
        chapter_index,
        source_pov_id=current_pov_id,
        scene_scope=f"chapter:{chapter_index}",
        evidence_source_type="observed_fact" if source_section_type == "CHAPTER" else "paratext",
        actuality_status="actual" if source_section_type == "CHAPTER" else "contextual_reference",
        boundary_title_id=title_id,
        boundary_book_id=title_id,
        boundary_volume_id=volume_id,
        session_id=session_id,
        source_session=session_id,
        inherited_confidence=1.0,
    )
    social_event_edges = 0
    for event_record in event_records:
        social_event_edges += db.record_event_social_context(event_record["event_id"])
    social_metrics = db.refresh_social_graph_metrics(chapter_index)
    resolve_trivial_conflicts(db)
    entity_merge_stats = reconcile_entities(db, auto_merge=True)
    location_merge_stats = reconcile_locations(db, auto_merge=True)
    finalized_merge_stats = db.finalize_merge_candidates()
    social_metrics = db.refresh_social_graph_metrics(chapter_index)
    merge_stats = {
        "entities": entity_merge_stats,
        "locations": location_merge_stats,
        "finalized_candidates": finalized_merge_stats,
        "social_graph": social_metrics,
        "actual_merges": (
            entity_merge_stats.get("actual_merges", 0)
            + location_merge_stats.get("actual_merges", 0)
            + finalized_merge_stats.get("finalized", 0)
        ),
    }
    ai_data["_merge_stats"] = merge_stats
    from life_status_resolver import LifeStatusResolver
    LifeStatusResolver(db).resolve_all()
    db.record_performance_metric(chapter_index, "chapter_processing_time", time.perf_counter() - ingest_start, "seconds")
    db.record_performance_metric(chapter_index, "entity_count", len(filtered_entities), "count")
    db.record_performance_metric(chapter_index, "event_count", len(ai_data.get("major_events", [])), "count")
    db.record_performance_metric(chapter_index, "relationship_count", len(ai_data.get("relationships", [])), "count")
    db.record_performance_metric(chapter_index, "life_status_event_count", len(ai_data.get("life_status_events", [])), "count")
    db.record_performance_metric(chapter_index, "legacy_signal_count", len(ai_data.get("legacy_signals", [])), "count")
    db.record_performance_metric(chapter_index, "social_event_edge_count", social_event_edges, "count")
    db.record_performance_metric(chapter_index, "social_edge_count", social_metrics.get("social_edges", 0), "count")
    db.record_performance_metric(chapter_index, "community_count", social_metrics.get("communities", 0), "count")
    db.record_performance_metric(chapter_index, "merge_count", merge_stats["actual_merges"], "count")
    db.record_performance_metric(
        chapter_index,
        "image_evidence_count",
        image_evidence_summary.get("images", 0),
        "count",
    )
    terminology_observations = ai_data.get("terminology_observations") or []
    if terminology_observations or chapter_text:
        from dictionary_subsystem.terminology import TerminologyDiscovery
        discovery = TerminologyDiscovery(db)
        terminology_summary = discovery.process_observations(chapter_index, terminology_observations) if terminology_observations else discovery.process(chapter_index, chapter_text)
        db.record_performance_metric(chapter_index, "terminology_candidate_count", terminology_summary["candidates"], "count")
        db.record_performance_metric(chapter_index, "terminology_confirmation_count", terminology_summary["confirmed"], "count")
    return merge_stats
# ─── logging ───────────────────────────────────────────────────────
def get_session_log_dir(db_dir: str) -> str:
    session_dir = os.path.dirname(db_dir)
    log_dir = os.path.join(session_dir, "logs")
    for child in ("prompts", "responses", "failures", "debug"):
        os.makedirs(os.path.join(log_dir, child), exist_ok=True)
    return log_dir


def log_prompt(log_dir: str, chapter_index: int, prompt: str, metadata: dict | None = None) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    prompt_path = os.path.join(log_dir, "prompts", f"chapter_{chapter_index}_{timestamp}.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        if metadata:
            f.write(json.dumps(metadata, indent=2, ensure_ascii=False))
            f.write("\n\n")
        f.write(prompt)
    return prompt_path


def log_response(log_dir: str, chapter_index: int, payload: dict, metadata: dict | None = None) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    response_path = os.path.join(log_dir, "responses", f"chapter_{chapter_index}_{timestamp}.json")
    with open(response_path, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata or {}, "response": payload}, f, indent=2, ensure_ascii=False)
    return response_path


def log_failure(
    log_dir: str,
    book_title: str,
    session_name: str,
    chapter_index: int,
    chapter_title: str,
    attempt: int,
    active_key_id: str,
    prompt: str,
    error: str,
    response_info: str = "",
):
    prompt_token_estimate = len(prompt.split())
    failure_log = os.path.join(log_dir, "failures", "failures.log")
    with open(failure_log, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 100 + "\n")
        f.write(f"timestamp: {datetime.now().isoformat()}\n")
        f.write(f"book: {book_title}\n")
        f.write(f"session: {session_name}\n")
        f.write(f"chapter: {chapter_index}\n")
        f.write(f"chapter_index: {chapter_index}\n")
        f.write(f"chapter_title: {chapter_title}\n")
        f.write(f"attempt: {attempt}\n")
        f.write(f"prompt_version: {PROMPT_VERSION}\n")
        f.write(f"model_name: {AI_CHAPTER_MODEL_NAME}\n")
        f.write(f"prompt_token_estimate: {prompt_token_estimate}\n")
        f.write(f"active_key_id: {active_key_id}\n")
        f.write(f"error: {error}\n")
        if response_info:
            f.write(f"response: {response_info}\n")


def log_analysis_result(
    log_dir: str,
    book_title: str,
    session_name: str,
    chapter_index: int,
    chapter_title: str,
    status: str,
    duration_seconds: float,
    retries: int,
    safety_triggers: int,
    active_key_id: str = "",
):
    analysis_log = os.path.join(log_dir, "analysis.log")
    with open(analysis_log, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "book": book_title,
            "session": session_name,
            "chapter": chapter_index,
            "chapter_index": chapter_index,
            "chapter_title": chapter_title,
            "prompt_version": PROMPT_VERSION,
            "model_name": AI_CHAPTER_MODEL_NAME,
            "status": status,
            "duration_seconds": round(duration_seconds, 3),
            "retries": retries,
            "safety_triggers": safety_triggers,
            "active_key_id": active_key_id,
        }, ensure_ascii=False) + "\n")
# ─── Chapter Processor ───────────────────────────────────────────────────────

def process_single_chapter(
    ai_manager,
    chapter_index: int,
    book,
    db_dir: str,
    db: BookDatabase | None = None,
    previous_events_cache: dict[int, list[dict | str]] | None = None,
    ingest: bool = True,
    force_reextract: bool = False,
    trigger_reason: str = "new_chapter",
    allow_ai_vision_fallback: bool = False,
    ai_vision_consent_callback=None,
) -> dict:
    chapter_file   = os.path.join(db_dir, f"chapter_{chapter_index}.json")
    target_chapter = book.chapters[chapter_index]
    db = db or BookDatabase(db_dir)

    def _with_image_evidence(payload: dict) -> tuple[dict, bool]:
        """Clone payload evidence; original JSON chapter caches are immutable."""
        # A list alone is not a completion marker: early/legacy caches can
        # contain an empty list before the image-evidence schema existed.
        # Reparse only when descriptors are available, then append a new
        # evidence revision without touching the legacy JSON cache.
        if (
            payload.get("image_evidence_schema_version") == IMAGE_EVIDENCE_SCHEMA_VERSION
            and isinstance(payload.get("image_evidence"), list)
        ):
            return payload, False
        descriptors = list(getattr(target_chapter, "image_descriptors", []) or [])
        enriched = deepcopy(payload)
        # Keep Vision credentials and quota independent from chapter text
        # extraction. Its request is deferred until local image parsing is
        # low confidence and the caller has authorized API usage.
        vision_fallback_requested = allow_ai_vision_fallback or ai_vision_consent_callback is not None
        fallback_callable = (
            AIVisionFallback(ai_manager)
            if vision_fallback_requested and ai_manager is not None and ai_manager.is_available("vision")
            else None
        )
        enriched["image_evidence"] = (
            parse_chapter_images(
                descriptors,
                db=db,
                fallback_callable=fallback_callable,
                allow_ai_vision_fallback=vision_fallback_requested,
                vision_consent_callback=ai_vision_consent_callback,
            )
            if descriptors else []
        )
        enriched["image_evidence_schema_version"] = IMAGE_EVIDENCE_SCHEMA_VERSION
        chapter_diagnostics = list(getattr(target_chapter, "image_diagnostics", []) or [])
        if chapter_diagnostics:
            enriched["image_ingestion_diagnostics"] = chapter_diagnostics
        return enriched, True

    if os.path.exists(chapter_file) and not force_reextract:
        with open(chapter_file, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        evidence_payload, enriched = _with_image_evidence(cached_data)
        evidence = EvidenceStore.record(
            db,
            chapter_index,
            evidence_payload,
            trigger_reason="image_evidence_enrichment" if enriched else "legacy_import",
            source_metadata={
                "cache_file": os.path.basename(chapter_file),
                "import_mode": "image_evidence_enrichment" if enriched else "process_cache",
                "text_model_called": False,
            },
            preserve_existing_active=not enriched,
        )
        cache_status = cache_metadata_status(cached_data)
        cached_data["_cache_status"] = cache_status
        cached_data["_evidence_revision"] = evidence["revision"]
        if cache_status["status"] == "stale":
            logger.warning("Stale immutable cache detected", extra={"chapter": chapter_index, "mismatches": cache_status["mismatches"]})
        if previous_events_cache is not None:
            previous_events_cache[chapter_index] = cached_data.get("major_events", [])
        return evidence_payload

    if target_chapter.section_type == "FRONT_BACK_MATTER":
        logger.info("Bypassing AI for system text", extra={"chapter": chapter_index})
        ai_data = {
            "pov_character_found": "",
            "new_aliases_discovered": [],
            "new_group_aliases_discovered": [],
            "entities_present": [],
            "relationships": [],
            "major_events": [f"System skipped: {target_chapter.title}"],
            "life_status_events": [],
            "legacy_signals": [],
            "_section_type": target_chapter.section_type,
            "_source_material_type": "paratext",
            "_chapter_title": target_chapter.title,
            "_metadata": build_cache_metadata(),
        }
        ai_data, _ = _with_image_evidence(ai_data)
        evidence = EvidenceStore.record(
            db,
            chapter_index,
            ai_data,
            trigger_reason=trigger_reason,
            source_metadata={"section_type": target_chapter.section_type, "chapter_title": target_chapter.title},
        )
        if not os.path.exists(chapter_file):
            write_json_cache_once(chapter_file, ai_data)
        if ingest:
            SnapshotStore.capture(db, chapter_index, evidence, trigger_reason=trigger_reason)
        ai_data["_evidence_revision"] = evidence["revision"]
        if previous_events_cache is not None:
            previous_events_cache[chapter_index] = ai_data.get("major_events", [])
        return ai_data

    logger.info("Processing chapter", extra={"chapter": chapter_index})

    if ingest:
        db.apply_confidence_decay(chapter_index)

    log_dir = get_session_log_dir(db_dir)
    session_name = os.path.basename(os.path.dirname(db_dir))
    prompt_context = build_prompt_context(
        db,
        target_chapter.content,
        previous_events_cache,
        chapter_index,
        PREVIOUS_CONTEXT_CHAPTERS,
    )

    # Completely re-engineered Positive Constraint Academic Prompt
    prompt = f"""You are an automated NLP data-extraction algorithm processing the published text "{book.title}". Your objective is pure structural data mining. You must process the provided text strictly as a sequence of abstract data points. You must output exclusively in valid JSON format. Your extraction must reflect only the literal words and events provided in the current text block. Catalog all events, including character deaths or conflicts, precisely as written.

STRUCTURED MEMORY CARDS:
{prompt_context["memory_cards"]}

RELATIONSHIP CONTEXT:
{prompt_context["relationship_context"]}

SOCIAL WEB CONTEXT:
{prompt_context["social_web_context"]}

LIFE / DEATH STATUS CONTEXT:
{prompt_context["life_status_context"]}

PRIOR EVENT CONTEXT FROM GRAPH:
{prompt_context["prior_event_context"]}

RECENT EVENT CACHE:
{prompt_context["previous_cache_context"]}

KNOWN INDIVIDUALS:
{prompt_context["known_chars"]}

KNOWN GROUPS:
{prompt_context["known_groups"]}

KNOWN LOCATIONS:
{prompt_context["known_locs"]}

EXTRACTION TASK:

1. POV CHARACTER
   Name the point-of-view character, or use "[UNNAMED_POV]" if first-person but unnamed.

2. ENTITIES PRESENT
   Extract every named individual, group, location, object, concept, symbolic figure, reference-only entity, animal, AI, non-human sentient being, and agentive place that appears.
   Keep entity_type as a routing field only:
   - INDIVIDUAL: one active narrative actor, human or non-human.
   - GROUP: faction, organisation, species collective, or named collective.
   - LOCATION: named place.
   - CONCEPT_OR_LORE: concepts, lore, references, symbolic entities, and non-social named objects.
   Always fill layered ontology fields:
   - entity_category: CHARACTER, GROUP, LOCATION, OBJECT, CONCEPT, REFERENCE, or UNKNOWN.
   - species_or_kind: human, animal, alien, ai, spirit, construct, plant, object, unknown, or another evidence-backed kind.
   - sentience: true, false, or unknown. Do not infer species or sentience early.
   - active_status: active_participant, referenced_only, historical_only, symbolic_only, or uncertain.
   - identity_status: confirmed, probable, possible, conflicted, or unknown.
   - entity_persistence: persistent, temporary, scene_only, flashback_only, dream_only, or hallucination_only.
   - story_role is narrative importance; functional_role is job/office/species role. Keep them separate.
   - can_speak, can_move, can_think, can_remember, can_make_decisions, can_form_relationships: true, false, or unknown.
   - literal_status and interpretation_status must separate literal, symbolic, imagined, metaphorical, historical_reference, dream, hallucination, reported, recalled, and uncertain layers.
   Preserve multiple interpretations in interpretation_status with comma-separated values when needed.
   Do not emit bare kinship words, occupational roles, religious titles, or sentence-initial common nouns as INDIVIDUAL entities.
   Keep father, mother, sister, brother, teacher, captain, doctor, and priest style surfaces in relationship_evidence or event text unless the chapter gives a stable full name or explicit title-to-name link.
   Do not emit a person as present only because a ship, law, treaty, theory, doctrine, title, place, memorial, institution, or artifact is named after them or contains their name.
   Same spelling is not identity: a person, place, ship, law, title, and object may share a surface name and must remain separate unless current-chapter evidence directly proves identity.

   Treat "named after X", "X's law", "X's treaty", "X's ship", "X's memorial", renamed objects, and same-name different-referent language as reference/name-relation evidence unless X speaks, acts, is present, has a relationship, or participates in an event in the current narrative.
   Named animals, AI, spirits, constructs, aliens, sentient objects, and living places may be active characters only when current text gives speech, thought, agency, event participation, or relationship evidence.
   Named non-sentient objects may be important without becoming social entities.

3. ALIASES
   If a character is referred to by a true alternate name or stable epithet not yet
   in KNOWN INDIVIDUALS, record it in new_aliases_discovered with a direct quote
   as context_proof.
   Do not turn relational phrases, possessive descriptions, or bare roles into
   aliases. Title-like phrases may be emitted only when the current chapter
   directly links the title to the named entity.
   Do not turn namesakes, eponyms, renamed objects, homonyms, or shared surface names into aliases without direct identity evidence.
   If a group has a new alternate name, record it in new_group_aliases_discovered.

4. RELATIONSHIPS
   For each meaningful interaction, record source, target, a trust_score (-10 to +10),
   and relationship_evidence.
   relationship_evidence must be a direct quote or literal observed interaction from THIS CHAPTER ONLY.
   Relationships are directional: source is the observer, speaker, or actor whose attitude is represented; target is the object of that attitude.
   Do not infer motives, blame, historical causes, or explanations from prior chapters.
   Do not convert shared faction membership, shared scene presence, or temporary mission cooperation into friendship.
   Keep family, mentorship, command, romance, rivalry, fear, respect, obligation, public behavior, private behavior, and hidden/rumored belief distinct in the evidence wording.
   Include meaningful non-POV interactions between side characters when the current chapter gives literal evidence.

5. MAJOR EVENTS
   Return structured event objects, never bare strings for new analysis. summary is a concise literal account of the current chapter's event.
   Keep event identity separate from names: use landmark_reference only to copy an exact [landmark:lm_*] reference from PRIOR EVENT CONTEXT or a directly established prior label. Never invent an identity key and never merge merely because a phrase repeats.
   Use landmark_name only when the text actually gives a name. Put alternate, factional, commemorative, propagandistic, retrospective, metaphorical, or sarcastic labels in landmark_names with provenance; do not make them the canonical identity.
   Fill landmark_type, lifecycle, event_state, event_reliability, reader_visibility, event_scope/geographic_scope, narrative versus historical timing, outcome, historical_memory, and importance only when supported by the current text. Unknown is preferred to inference.
   Use participants with role (attacker, defender, victim, witness, commander, organizer, speaker, observer, beneficiary, or participant) and direct evidence. Use primary_location and secondary_locations only for named locations.
   A ceremony, memorial, or annual tradition is a distinct occurrence: use landmark_link_type commemoration or recurrence_instance and recurrence_template_reference when the text supports it. Do not merge occurrences across years.
   Use perspectives for separate neutral, reader, speaker, faction, historian, or narrator summaries. Do not overwrite one perspective with another.
   If an event is remembered, reported, dreamed, imagined, quoted from paratext, or otherwise not directly observed in the current narrative moment, preserve that uncertainty through event_reliability and wording.
   Do not convert footnotes, citations, appendices, glossaries, or metadata into active story events.

6. ENTITY SEMANTIC RELATIONS
   Emit ownership, attachment, gift, inheritance, creation, containment, namesake, memorial, artifact_origin, command, and similar non-social relation evidence in entity_semantic_relations.
   Do not use friendship/trust relationships for non-sentient object attachment.

7. LANGUAGE OBSERVATIONS
   Emit untranslated, alien, cipher, code, invented script, glossary, or decoder evidence in language_observations.
   Store language, writing_system, translation_status, decoder_source, and source_evidence. Do not invent translations.

8. LIFE STATUS EVENTS
   Emit life_status_events only when the current text gives explicit evidence about a named entity's life, death, missing state, presumed death, fake death, revival, survival, or appearance.
   Do not infer life from mention frequency. Mentioning a dead or missing person usually updates legacy_signals, not life_status_events.
   Keep reality, belief, and appearance separate:
   - actual_status: alive, dead, missing, or unknown. Use unknown when the text only reports a belief.
   - belief_status: alive, dead, missing, or unknown. Use this for character/narrator/reader beliefs.
   - appearance_status: possible_alive, observed_alive, confirmed_alive, appears_dead, or unknown.
   - belief_owner_type: reader, narrator, character, group, or unknown. Fill belief_owner when a specific character or group holds the belief.
   - reader_visible: true only if the reader can know this status from the current text without future-book knowledge.
   - participation_type: active_scene, flashback, memory, vision, letter, recording, historical_reference, dream, or hallucination.
   - observation_type: direct, reported, assumed, rumor, historical, vision, dream, or flashback.
   - status_reason: battle, execution, disease, accident, suicide, reported, rumor, fake, supernatural, or unknown.
   - missing_subtype: lost, captured, escaped, disappeared, unknown_location, missing, or empty.
   Use possible_alive -> observed_alive -> confirmed_alive for ambiguous returns.
   A dream, ghost, hallucination, flashback, memory, letter, recording, archive, or historical reference is participation but not proof of literal life.
   A fake death, clone, backup, reincarnation, alternate self, reconstructed body, or uploaded mind must set identity_continuity_mode instead of assuming same identity.
   Store separate rows for multiple independent reports; do not collapse witnesses or rumors into one final truth.

9. LEGACY SIGNALS
   Emit legacy_signals for grief, memorials, revenge motives, lineage, inheritance, political claims, honor, hatred, memory, familial impact, and historical importance.
   Legacy, memory, emotional importance, political importance, historical importance, and familial importance never prove biological life.

SOURCE SCOPE:
   Current section type: {target_chapter.section_type}
   Use section/source context to separate narration, dialogue, reported speech, recalled events, imagined scenes, lore supplements, and paratext.

CHAPTER TEXT:
{target_chapter.content}"""

    ai_data = None
    max_retries = 1  # Retry policy is owned by AIManager; retained for failure logging.
    start_time = time.time()
    safety_triggers = 0
    last_key_id = ""
    base_log_metadata = {
        "book": book.title,
        "session": session_name,
        "chapter": chapter_index,
        "chapter_index": chapter_index,
        "chapter_title": target_chapter.title,
        "model": AI_CHAPTER_MODEL_NAME,
        "model_name": AI_CHAPTER_MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
    }
    log_prompt(log_dir, chapter_index, prompt, {**base_log_metadata, "result_status": "prompt_written"})
    
    for attempt in range(1):
        current_key_id = ""
        try:
            result = ai_manager.generate(GenerationRequest(
                role="chapter_analysis",
                prompt=prompt,
                response_schema=ChapterAnalysis,
                temperature=0.0,
                safety_profile="unrestricted",
                metadata={"book": book.title, "chapter_index": chapter_index},
            ))
            current_key_id = result.credential_id
            last_key_id = current_key_id
            safety_triggers = result.safety_triggers
            ai_data = result.parsed
            if not isinstance(ai_data, dict):
                ai_data = parse_analysis_response(result)
            log_response(
                log_dir,
                chapter_index,
                ai_data,
                {**base_log_metadata, "key_id": current_key_id, "provider": result.provider, "model_name": result.model, "result_status": "response_received"},
            )
            break # Success! Break the retry loop.
            
        except RuntimeError as e:
            log_failure(
                log_dir,
                book.title,
                session_name,
                chapter_index,
                target_chapter.title,
                attempt + 1,
                current_key_id,
                prompt,
                str(e),
            )

            error_msg = str(e).lower()

            if "blocked" in error_msg or "prohibited" in error_msg:
                safety_triggers += 1
                logger.warning("AI safety block", extra={"chapter": chapter_index, "attempt": attempt + 1})
            else:
                logger.warning("AI response parsing failed", extra={"chapter": chapter_index, "error_class": type(e).__name__})
            raise
        except Exception as e:
            log_failure(
                log_dir,
                book.title,
                session_name,
                chapter_index,
                target_chapter.title,
                attempt + 1,
                current_key_id,
                prompt,
                str(e),
            )

            logger.exception("Chapter AI extraction failed", extra={"chapter": chapter_index, "attempt": attempt + 1})

            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                pass
            elif "503" in error_msg or "500" in error_msg or "unavailable" in error_msg:
                # Exponential Backoff for Google Server Crashes (caps at 60s)
                sleep_time = min(2 ** attempt, 60)
                logger.warning("AI provider unavailable", extra={"chapter": chapter_index, "backoff_seconds": sleep_time})
            else:
                sleep_time = min(2 ** attempt, 60)
                logger.warning("Unknown AI provider error", extra={"chapter": chapter_index, "error_class": type(e).__name__, "backoff_seconds": sleep_time})

            raise

    if not ai_data:
        log_analysis_result(
            log_dir,
            book.title,
            session_name,
            chapter_index,
            target_chapter.title,
            "failure",
            time.time() - start_time,
            1,
            safety_triggers,
            last_key_id,
        )
        raise RuntimeError("❌ Extraction failed: All API keys exhausted or max retries exceeded.")

    ai_data["_metadata"] = build_cache_metadata()
    book_name = os.path.basename(os.path.dirname(os.path.dirname(db_dir)))
    session_id = f"{book_name}::{session_name}"
    ai_data["_title_id"] = book_name
    ai_data["_volume_id"] = book_name
    ai_data["_session_id"] = session_id
    ai_data["_section_type"] = target_chapter.section_type
    ai_data["_source_material_type"] = "narrative" if target_chapter.section_type in {"CHAPTER", "STORY_EVENT"} else "contextual"
    ai_data["_chapter_title"] = target_chapter.title
    ai_data["_chapter_boundary_confidence"] = getattr(target_chapter, "chapter_boundary_confidence", None)
    from dictionary_subsystem.terminology import TerminologyDiscovery
    ai_data["terminology_observations"] = [
        *TerminologyDiscovery.discover(target_chapter.content),
        *TerminologyDiscovery.discover_images(ai_data.get("image_evidence") or []),
    ]
    ai_data, _ = _with_image_evidence(ai_data)

    evidence = EvidenceStore.record(
        db,
        chapter_index,
        ai_data,
        trigger_reason=trigger_reason,
        source_metadata={
            "chapter_title": target_chapter.title,
            "section_type": target_chapter.section_type,
            "force_reextract": bool(force_reextract),
            "gemini_vision_fallback_authorized": bool(allow_ai_vision_fallback),
        },
    )

    if ingest:
        ingest_ai_payload(ai_data, chapter_index, db, target_chapter.content)
        SnapshotStore.capture(db, chapter_index, evidence, trigger_reason=trigger_reason)

    if not os.path.exists(chapter_file):
        write_json_cache_once(chapter_file, ai_data)
    ai_data["_evidence_revision"] = evidence["revision"]
    if previous_events_cache is not None:
        previous_events_cache[chapter_index] = ai_data.get("major_events", [])

    log_analysis_result(
        log_dir,
        book.title,
        session_name,
        chapter_index,
        target_chapter.title,
        "success",
        time.time() - start_time,
        attempt,
        safety_triggers,
        last_key_id,
    )

    return ai_data
