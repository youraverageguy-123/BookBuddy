import os
import json
import re
import time
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal
from db_manager import BookDatabase
from config import (
    API_PACING_SECONDS,
    BOOKBUDDY_VERSION,
    CACHE_VERSION,
    GEMINI_MODEL_NAME,
    GRAPH_SCHEMA_VERSION,
    MAX_EXTRACTION_RETRIES,
    NORMALIZATION_VERSION,
    PREVIOUS_CONTEXT_CHAPTERS,
    PROMPT_VERSION,
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
    reason: str

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
    "soldier", "crew", "crowd", "people", "child", "servant", "thug", "bouncer"
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
        
    if " " in alias_stripped and alias_stripped.islower():
        return False
        
    return alias_stripped[0].isupper() or alias_stripped.startswith("[")

def normalize_string(name: str, is_group: bool = False) -> str:
    name = name.strip()
    if is_group:
        name = re.sub(r'(?i)\s+(caste|clan|family|tribe|house|faction|empire)$', '', name).strip()
    return name


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


def ingest_ai_payload(ai_data: dict, chapter_index: int, db: BookDatabase):
    char_alias_to_id,  char_id_to_canon  = db.get_resolution_matrices("INDIVIDUAL")
    group_alias_to_id, group_id_to_canon = db.get_resolution_matrices("GROUP")
    loc_alias_to_id,   loc_id_to_canon   = db.get_resolution_matrices("LOCATION")

    pov_found = ai_data.get("pov_character_found")
    current_pov_id = None
    norm_pov = normalize_string(pov_found).lower() if pov_found else "[unnamed_pov]"
    prev_pov_id = db.get_pov_for_chapter(chapter_index - 1)

    if norm_pov == "[unnamed_pov]" and prev_pov_id:
        current_pov_id = prev_pov_id
        db.set_pov_for_chapter(chapter_index, current_pov_id)
    else:
        if norm_pov == "[unnamed_pov]":
            if "[unnamed_pov]" not in char_alias_to_id:
                new_id = db.add_entity("[UNNAMED_POV]", "INDIVIDUAL", chapter_index)
                char_alias_to_id["[unnamed_pov]"] = new_id
                char_id_to_canon[new_id] = "[UNNAMED_POV]"
            current_pov_id = char_alias_to_id["[unnamed_pov]"]
        else:
            current_pov_id = char_alias_to_id.get(norm_pov)
            if not current_pov_id:
                current_pov_id = db.add_entity(normalize_string(pov_found), "INDIVIDUAL", chapter_index)
                char_alias_to_id[norm_pov] = current_pov_id
                char_id_to_canon[current_pov_id] = normalize_string(pov_found)

        db.set_pov_for_chapter(chapter_index, current_pov_id)

        if pov_found and pov_found != "[UNNAMED_POV]":
            if db.register_ghost_merge(current_pov_id):
                db.merge_ghost_nodes(current_pov_id)
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
        lower_name = norm_name.lower()

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

        if not is_structurally_valid(canon_raw) or not is_structurally_valid(new_nick_raw) or not is_valid_alias(new_nick_raw):
            continue  

        canon_lower = normalize_string(canon_raw).lower()
        target_id   = char_alias_to_id.get(canon_lower)
        if not target_id: continue

        new_nick   = normalize_string(new_nick_raw)
        nick_lower = new_nick.lower()

        existing_id = char_alias_to_id.get(nick_lower)
        if existing_id and existing_id != target_id:
            surviving_id = min(target_id, existing_id)
            losing_id = max(target_id, existing_id)
            if db.register_merge_candidate(surviving_id, losing_id):
                db.merge_entities(surviving_id, losing_id)
                char_alias_to_id = {k: (surviving_id if v == losing_id else v) for k, v in char_alias_to_id.items()}
                target_id = surviving_id
            else:
                continue  

        db.add_alias(target_id, new_nick, chapter_index, alias_obj.get("context_proof", "Rebuild Sync"))
        char_alias_to_id[nick_lower] = target_id

    for g_alias in ai_data.get("new_group_aliases_discovered", []):
        canon_raw = g_alias.get("canonical_group_name", "")
        new_nick_raw = g_alias.get("new_alias", "")

        if not is_structurally_valid(canon_raw) or not is_structurally_valid(new_nick_raw) or not is_valid_alias(new_nick_raw):
            continue

        canon_lower = normalize_string(canon_raw, is_group=True).lower()
        target_id   = group_alias_to_id.get(canon_lower)
        if not target_id: continue

        new_nick   = normalize_string(new_nick_raw, is_group=True)
        nick_lower = new_nick.lower()

        existing_id = group_alias_to_id.get(nick_lower)
        if existing_id and existing_id != target_id:
            surviving_id = min(target_id, existing_id)
            losing_id = max(target_id, existing_id)
            if db.register_merge_candidate(surviving_id, losing_id):
                db.merge_entities(surviving_id, losing_id)
                group_alias_to_id = {k: (surviving_id if v == losing_id else v) for k, v in group_alias_to_id.items()}
                target_id = surviving_id
            else:
                continue

        db.add_alias(target_id, new_nick, chapter_index, g_alias.get("context_proof", "Rebuild Sync"))
        group_alias_to_id[nick_lower] = target_id

    for rel in ai_data.get("relationships", []):
        src = rel["source"]
        tgt = rel["target"]

        if src == "[UNNAMED_POV]": src = pov_canon_name
        if tgt == "[UNNAMED_POV]": tgt = pov_canon_name

        if not is_structurally_valid(src) or not is_structurally_valid(tgt):
            continue

        def _resolve(name: str) -> int | None:
            ind = char_alias_to_id.get(normalize_string(name).lower())
            if ind: return ind
            grp = group_alias_to_id.get(normalize_string(name, is_group=True).lower())
            if grp: return grp
            loc = loc_alias_to_id.get(normalize_string(name).lower())
            return loc

        src_id = _resolve(src)
        tgt_id = _resolve(tgt)

        if not src_id or not tgt_id or src_id == tgt_id: continue

        def _canon(eid: int) -> str | None:
            return (char_id_to_canon.get(eid) or group_id_to_canon.get(eid) or loc_id_to_canon.get(eid))

        rel["source"] = _canon(src_id)
        rel["target"] = _canon(tgt_id)
        db.add_relationship_event(src_id, tgt_id, chapter_index, rel["trust_score"], rel["reason"])


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
            return json.load(f)

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

    story_so_far = []
    for i in range(max(0, chapter_index - PREVIOUS_CONTEXT_CHAPTERS), chapter_index):
        if previous_events_cache is not None and i in previous_events_cache:
            events = previous_events_cache[i]
            if events and "System skipped" not in events[0]:
                story_so_far.append(f"Chapter {i}: " + " | ".join(events))
            continue

        prev_file = os.path.join(db_dir, f"chapter_{i}.json")
        if os.path.exists(prev_file):
            with open(prev_file, "r", encoding="utf-8") as f:
                events = json.load(f).get("major_events", [])
                if previous_events_cache is not None:
                    previous_events_cache[i] = events
                if events and "System skipped" not in events[0]:
                    story_so_far.append(f"Chapter {i}: " + " | ".join(events))

    context_string     = "\n".join(story_so_far) if story_so_far else "No prior context."
    chapter_text_lower = target_chapter.content.lower()

    known_chars  = db.get_known_entities_text("INDIVIDUAL", chapter_text_lower)
    known_groups = db.get_known_entities_text("GROUP",      chapter_text_lower)
    known_locs   = db.get_known_entities_text("LOCATION",   chapter_text_lower)

    # Completely re-engineered Positive Constraint Academic Prompt
    prompt = f"""You are an automated NLP data-extraction algorithm processing the published text "{book.title}". Your objective is pure structural data mining. You must process the provided text strictly as a sequence of abstract data points. You must output exclusively in valid JSON format. Your extraction must reflect only the literal words and events provided in the current text block. Catalog all events, including character deaths or conflicts, precisely as written.

PREVIOUS CONTEXT (last 3 chapters):
{context_string}

KNOWN INDIVIDUALS:
{known_chars}

KNOWN GROUPS:
{known_groups}

KNOWN LOCATIONS:
{known_locs}

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
   If a character is referred to by a new name or title not yet in KNOWN INDIVIDUALS,
   record it in new_aliases_discovered with a direct quote as context_proof.
   If a group has a new alternate name, record it in new_group_aliases_discovered.

4. RELATIONSHIPS
   For each meaningful interaction, record source, target, a trust_score (-10 to +10),
   and a one-sentence reason.

5. MAJOR EVENTS
   List the key plot events of this chapter as concise bullet strings.

CHAPTER TEXT:
{target_chapter.content}"""

    ai_data = None
    max_retries = MAX_EXTRACTION_RETRIES  # Extensive retry threshold to outlast server outages
    
    for attempt in range(max_retries):
        client, current_key_id = key_manager.get_available_client()
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
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,       threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,        threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    ],
                ),
            )
            ai_data = parse_gemini_response(response)
            break # Success! Break the retry loop.
            
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "prohibited" in error_msg:
                print(f"\n⚠️ Safety block triggered (Attempt {attempt+1}/{max_retries}).")
                key_manager.regenerate_client(current_key_id)
                time.sleep(SAFETY_RETRY_SECONDS) # Wait before hitting the fresh client
            else:
                print(f"\n⚠️ Parser Error: {e}")
                time.sleep(2)
        except Exception as e:
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
        raise RuntimeError("❌ Extraction failed: All API keys exhausted or max retries exceeded.")

    ai_data["_metadata"] = build_cache_metadata()

    ingest_ai_payload(ai_data, chapter_index, db)

    write_json_cache_once(chapter_file, ai_data)
    if previous_events_cache is not None:
        previous_events_cache[chapter_index] = ai_data.get("major_events", [])

    return ai_data
