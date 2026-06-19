import os
import json
import re
import time
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal
from db_manager import BookDatabase
from datetime import datetime
from alias_validator import CONFLICT, NEEDS_REVIEW, REJECTED, TRUE_ALIAS, TITLE_LINK, validate_alias
from conflict_resolver import resolve_trivial_conflicts
from event_deduper import add_event_with_cluster
from identity_promoter import promote_named_pov
from mention_indexer import index_ai_mentions
from prompt_context_builder import build_prompt_context
from title_linker import maybe_add_title_link
from config import (
    ALIAS_BASE_CONFIDENCE,
    ALIAS_COMMON_NOUN_PENALTY,
    ALIAS_LOWERCASE_PENALTY,
    ALIAS_TITLE_ONLY_PENALTY,
    API_PACING_SECONDS,
    BOOKBUDDY_VERSION,
    CACHE_VERSION,
    GEMINI_MODEL_NAME,
    GRAPH_SCHEMA_VERSION,
    MAX_EXTRACTION_RETRIES,
    NORMALIZATION_VERSION,
    PREVIOUS_CONTEXT_CHAPTERS,
    PROMPT_VERSION,
    RELATIONSHIP_BASE_CONFIDENCE,
    SAFETY_RETRY_SECONDS,
)

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

class ChapterAnalysis(BaseModel):
    pov_character_found: str = Field(
        description="The POV character's name, or '[UNNAMED_POV]' if first-person but unnamed. Use '' if none."
    )
    new_aliases_discovered: list[AliasDict]
    new_group_aliases_discovered: list[GroupAliasDict]
    entities_present: list[EntityDict]
    relationships: list[RelationshipDict]
    major_events: list[str]


# ─── Python Bouncer Layer ────────────────────────────────────────────────────

_RELATIONAL_PREFIXES = (
    "my ", "our ", "his ", "her ", "their ", "a ", "an ", "some ",
)

_GENERIC_ROLES = {
    "guard", "boy", "girl", "man", "woman", "friend", "voice",
    "soldier", "crew", "crowd", "people", "child", "servant", "thug", "bouncer",
    "father", "mother", "prince", "princess", "lord", "lady", "sir", "captain"
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


# ─── Gemini Response Parser ──────────────────────────────────────────────────

def parse_gemini_response(response) -> dict:
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
            f"Gemini blocked this chapter. "
            f"block_reason={getattr(block_reason, 'value', block_reason)}, "
            f"usage_metadata={getattr(response, 'usage_metadata', None)}"
        )

    raise RuntimeError(
        f"Gemini returned HTTP 200 but no parseable JSON. "
        f"finish_reason={finish_reason}, safety_ratings={safety_ratings}, "
        f"prompt_feedback={prompt_feedback}"
    )


# ─── Universal Ingestion Pipeline ────────────────────────────────────────────

def build_cache_metadata(processed_at: float | None = None) -> dict:
    return {
        "cache_version": CACHE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_name": GEMINI_MODEL_NAME,
        "normalization_version": NORMALIZATION_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "bookbuddy_version": BOOKBUDDY_VERSION,
        "processed_at": processed_at or time.time(),
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


def ingest_ai_payload(ai_data: dict, chapter_index: int, db: BookDatabase, chapter_text: str = ""):
    index_ai_mentions(db, ai_data, chapter_index, chapter_text)

    char_alias_to_id,  char_id_to_canon  = db.get_resolution_matrices("INDIVIDUAL")
    group_alias_to_id, group_id_to_canon = db.get_resolution_matrices("GROUP")
    loc_alias_to_id,   loc_id_to_canon   = db.get_resolution_matrices("LOCATION")

    pov_found = ai_data.get("pov_character_found")
    current_pov_id = None
    norm_pov = lookup_key(db, pov_found) if pov_found else "unnamed_pov"
    prev_pov_id = db.get_pov_for_chapter(chapter_index - 1)

    if norm_pov == "unnamed_pov" and prev_pov_id:
        current_pov_id = prev_pov_id
        db.set_pov_for_chapter(chapter_index, current_pov_id)
    else:
        if norm_pov == "unnamed_pov":
            if "unnamed_pov" not in char_alias_to_id:
                new_id = db.add_entity("[UNNAMED_POV]", "INDIVIDUAL", chapter_index)
                char_alias_to_id["unnamed_pov"] = new_id
                char_id_to_canon[new_id] = "[UNNAMED_POV]"
            current_pov_id = char_alias_to_id["unnamed_pov"]
        else:
            current_pov_id = char_alias_to_id.get(norm_pov)
            if not current_pov_id:
                current_pov_id = db.add_entity(normalize_string(pov_found), "INDIVIDUAL", chapter_index)
                char_alias_to_id[norm_pov] = current_pov_id
                char_id_to_canon[current_pov_id] = normalize_string(pov_found)

        db.set_pov_for_chapter(chapter_index, current_pov_id)

        if pov_found and pov_found != "[UNNAMED_POV]":
            if promote_named_pov(db, current_pov_id, chapter_index, f"POV resolved as {pov_found}"):
                char_alias_to_id, char_id_to_canon = db.get_resolution_matrices("INDIVIDUAL")

    pov_canon_name = char_id_to_canon.get(current_pov_id, "[UNNAMED_POV]")

    filtered_entities = []
    for entity in ai_data.get("entities_present", []):
        raw_name = entity.get("name", "")
        e_type   = entity.get("entity_type", "")

        if e_type == "CONCEPT_OR_LORE" or not is_structurally_valid(raw_name):
            continue

        if raw_name == "[UNNAMED_POV]":
            raw_name = pov_canon_name

        is_grp = (e_type == "GROUP")
        is_loc = (e_type == "LOCATION")

        norm_name  = normalize_string(raw_name, is_grp)
        lower_name = db.normalize_alias_key(norm_name)

        if lower_name in loc_alias_to_id:
            e_type, is_grp, is_loc = "LOCATION", False, True
        elif lower_name in group_alias_to_id:
            e_type, is_grp, is_loc = "GROUP", True, False
        elif lower_name in char_alias_to_id:
            e_type, is_grp, is_loc = "INDIVIDUAL", False, False

        target_map = group_alias_to_id if is_grp else (loc_alias_to_id if is_loc else char_alias_to_id)
        target_reverse = group_id_to_canon if is_grp else (loc_id_to_canon if is_loc else char_id_to_canon)

        entity_id = target_map.get(lower_name)
        if not entity_id:
            entity_id = db.add_entity(norm_name, e_type, chapter_index)
            target_map[lower_name] = entity_id
            target_reverse[entity_id] = norm_name
        else:
            db.update_entity_verification(entity_id, chapter_index)

        ent_dict = {"name": target_reverse[entity_id], "entity_type": e_type}
        if ent_dict not in filtered_entities:
            filtered_entities.append(ent_dict)

    ai_data["entities_present"] = filtered_entities

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
        if alias_status != "rejected" and validation.status == TRUE_ALIAS:
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

    event_records = []
    previous_event_id = None
    for event_order, event_summary in enumerate(ai_data.get("major_events", []), start=1):
        event_id = add_event_with_cluster(
            db,
            chapter_index,
            event_summary,
            event_order,
            source_payload={"major_event": event_summary},
        )
        if not event_id:
            continue
        if previous_event_id:
            db.add_event_causal_edge(previous_event_id, event_id, relation_type="precedes", confidence=0.55)
        previous_event_id = event_id
        event_records.append((event_id, event_summary))

        normalized_event = db.normalize_alias_key(event_summary)
        for alias_map in (char_alias_to_id, group_alias_to_id, loc_alias_to_id):
            for alias_key, entity_id in alias_map.items():
                if alias_key and re.search(rf"\b{re.escape(alias_key)}\b", normalized_event):
                    db.add_event_participant(event_id, entity_id)

    def _match_event_id(src_name: str, tgt_name: str, evidence: str) -> int | None:
        if not event_records:
            return None
        src_key = db.normalize_alias_key(src_name)
        tgt_key = db.normalize_alias_key(tgt_name)
        evidence_key = db.normalize_alias_key(evidence)
        fallback = None
        for event_id, event_summary in event_records:
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
        return event_records[0][0] if len(event_records) == 1 else None

    for rel in ai_data.get("relationships", []):
        src = rel["source"]
        tgt = rel["target"]

        if src == "[UNNAMED_POV]": src = pov_canon_name
        if tgt == "[UNNAMED_POV]": tgt = pov_canon_name

        if not is_structurally_valid(src) or not is_structurally_valid(tgt):
            continue

        def _resolve(name: str) -> int | None:
            ind = char_alias_to_id.get(lookup_key(db, name))
            if ind: return ind
            grp = group_alias_to_id.get(lookup_key(db, name, is_group=True))
            if grp: return grp
            loc = loc_alias_to_id.get(lookup_key(db, name))
            return loc

        src_id = _resolve(src)
        tgt_id = _resolve(tgt)

        if not src_id or not tgt_id or src_id == tgt_id: continue

        def _canon(eid: int) -> str | None:
            return (char_id_to_canon.get(eid) or group_id_to_canon.get(eid) or loc_id_to_canon.get(eid))

        rel["source"] = _canon(src_id)
        rel["target"] = _canon(tgt_id)
        evidence = rel.get("relationship_evidence") or rel.get("observed_interaction") or rel.get("reason", "")
        event_id = _match_event_id(rel["source"], rel["target"], evidence)
        if event_id:
            db.add_event_participant(event_id, src_id)
            db.add_event_participant(event_id, tgt_id)
        db.add_relationship_event(
            src_id,
            tgt_id,
            chapter_index,
            rel["trust_score"],
            evidence,
            confidence=RELATIONSHIP_BASE_CONFIDENCE,
            event_id=event_id,
            consequence_description=evidence,
        )
    resolve_trivial_conflicts(db)
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
        f.write(f"model_name: {GEMINI_MODEL_NAME}\n")
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
            "model_name": GEMINI_MODEL_NAME,
            "status": status,
            "duration_seconds": round(duration_seconds, 3),
            "retries": retries,
            "safety_triggers": safety_triggers,
            "active_key_id": active_key_id,
        }, ensure_ascii=False) + "\n")
# ─── Chapter Processor ───────────────────────────────────────────────────────

def process_single_chapter(
    key_manager,
    chapter_index: int,
    book,
    db_dir: str,
    db: BookDatabase | None = None,
    previous_events_cache: dict[int, list[str]] | None = None,
) -> dict:
    chapter_file   = os.path.join(db_dir, f"chapter_{chapter_index}.json")
    target_chapter = book.chapters[chapter_index]

    if os.path.exists(chapter_file):
        with open(chapter_file, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        if previous_events_cache is not None:
            previous_events_cache[chapter_index] = cached_data.get("major_events", [])
        return cached_data

    if target_chapter.section_type == "FRONT_BACK_MATTER":
        print(f"⏩ Bypassing LLM for system text: {target_chapter.title}")
        ai_data = {
            "pov_character_found": "",
            "new_aliases_discovered": [],
            "new_group_aliases_discovered": [],
            "entities_present": [],
            "relationships": [],
            "major_events": [f"System skipped: {target_chapter.title}"],
            "_metadata": build_cache_metadata(),
        }
        write_json_cache_once(chapter_file, ai_data)
        if previous_events_cache is not None:
            previous_events_cache[chapter_index] = ai_data.get("major_events", [])
        return ai_data

    print(f"🧠 Processing Chapter {chapter_index} ({target_chapter.title})...")

    db = db or BookDatabase(db_dir)
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
   Extract every named individual, group, and location that appears.
   - INDIVIDUAL: a named person.
   - GROUP: a named faction, caste, organisation, or collective (e.g. Gold, Sons of Ares). Note: Factions within factions are distinct GROUP entities, not aliases.
   - LOCATION: a named place — planet, city, building, mine, region.
   - CONCEPT_OR_LORE: mythology, religion, historical event, abstract idea — extract these too.

3. ALIASES
   If a character is referred to by a true alternate name or stable epithet not yet
   in KNOWN INDIVIDUALS, record it in new_aliases_discovered with a direct quote
   as context_proof.
   Do not turn relational phrases, possessive descriptions, or bare roles into
   aliases. Title-like phrases may be emitted only when the current chapter
   directly links the title to the named entity.
   If a group has a new alternate name, record it in new_group_aliases_discovered.

4. RELATIONSHIPS
   For each meaningful interaction, record source, target, a trust_score (-10 to +10),
   and relationship_evidence.
   relationship_evidence must be a direct quote or literal observed interaction from THIS CHAPTER ONLY.
   Do not infer motives, blame, historical causes, or explanations from prior chapters.

5. MAJOR EVENTS
   List the key plot events of this chapter as concise bullet strings.

CHAPTER TEXT:
{target_chapter.content}"""

    ai_data = None
    max_retries = MAX_EXTRACTION_RETRIES  # Extensive retry threshold to outlast server outages
    start_time = time.time()
    safety_triggers = 0
    last_key_id = ""
    base_log_metadata = {
        "book": book.title,
        "session": session_name,
        "chapter": chapter_index,
        "chapter_index": chapter_index,
        "chapter_title": target_chapter.title,
        "model": GEMINI_MODEL_NAME,
        "model_name": GEMINI_MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
    }
    log_prompt(log_dir, chapter_index, prompt, {**base_log_metadata, "result_status": "prompt_written"})
    
    for attempt in range(max_retries):
        client, current_key_id = key_manager.get_available_client()
        last_key_id = current_key_id
        try:
            time.sleep(API_PACING_SECONDS) # Pacing buffer
            response = client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ChapterAnalysis,
                    temperature=0.0,
                    safety_settings=[
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,       threshold=types.HarmBlockThreshold.OFF),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.OFF),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.OFF),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,        threshold=types.HarmBlockThreshold.OFF),
                    ],
                ),
            )
            ai_data = parse_gemini_response(response)
            log_response(
                log_dir,
                chapter_index,
                ai_data,
                {**base_log_metadata, "key_id": current_key_id, "result_status": "response_received"},
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
                print(f"\n⚠️ Safety block triggered (Attempt {attempt+1}/{max_retries}).")
                key_manager.regenerate_client(current_key_id)
                time.sleep(SAFETY_RETRY_SECONDS)
            else:
                print(f"\n⚠️ Parser Error: {e}")
                time.sleep(2)
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

            print("\n" + "=" * 80)
            print("FULL EXCEPTION INFO")
            print("=" * 80)

            print("TYPE:")
            print(type(e))

            print("\nREPR:")
            print(repr(e))

            print("\nSTRING:")
            print(str(e))

            print("=" * 80 + "\n")

            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                key_manager.report_exhaustion(current_key_id)
            elif "503" in error_msg or "500" in error_msg or "unavailable" in error_msg:
                # Exponential Backoff for Google Server Crashes (caps at 60s)
                sleep_time = min(2 ** attempt, 60)
                print(f"\n🌩️ Server overloaded (503/500). Exponential backoff: sleeping for {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                sleep_time = min(2 ** attempt, 60)
                print(f"\n⚠️ Unknown API Error: {e}. Retrying in {sleep_time}s...")
                time.sleep(sleep_time)

    if not ai_data:
        log_analysis_result(
            log_dir,
            book.title,
            session_name,
            chapter_index,
            target_chapter.title,
            "failure",
            time.time() - start_time,
            max_retries,
            safety_triggers,
            last_key_id,
        )
        raise RuntimeError("❌ Extraction failed: All API keys exhausted or max retries exceeded.")

    ai_data["_metadata"] = build_cache_metadata()

    ingest_ai_payload(ai_data, chapter_index, db, target_chapter.content)

    write_json_cache_once(chapter_file, ai_data)
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
