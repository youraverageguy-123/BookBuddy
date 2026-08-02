def _source_quote(text: str, surface_form: str, radius: int = 140) -> str:
    if not text or not surface_form:
        return ""
    lowered = text.lower()
    idx = lowered.find(surface_form.lower())
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(surface_form) + radius)
    return " ".join(text[start:end].split())


def _sentence_offset(text: str, surface_form: str) -> int | None:
    if not text or not surface_form:
        return None
    idx = text.lower().find(surface_form.lower())
    if idx < 0:
        return None
    return text[:idx].count(".") + text[:idx].count("!") + text[:idx].count("?")


def _mention_source_type(source_quote: str) -> str:
    lowered = str(source_quote or "").lower()
    if any(marker in lowered for marker in ("footnote", "appendix", "glossary", "index")):
        return "paratext"
    if any(marker in lowered for marker in ("remembered", "recalled", "years ago", "long ago")):
        return "recalled"
    if any(marker in lowered for marker in ("dreamed", "dreamt", "imagined", "vision")):
        return "imagined"
    if any(marker in lowered for marker in ("told", "reported", "according to", "claimed")):
        return "reported"
    if '"' in source_quote or "'" in source_quote:
        return "dialogue"
    return "narration"


def index_ai_mentions(db, ai_data: dict, chapter_idx: int, chapter_text: str):
    narrator_id = db.get_pov_for_chapter(chapter_idx)
    section_type = ai_data.get("_section_type") or "CHAPTER"
    for entity in ai_data.get("entities_present", []):
        surface = entity.get("name", "")
        if not surface:
            continue
        classification = db.classify_mention_surface(surface, entity.get("entity_type", ""))
        quote = _source_quote(chapter_text, surface)
        db.add_mention_occurrence(
            surface_form=surface,
            chapter_idx=chapter_idx,
            sentence_offset=_sentence_offset(chapter_text, surface),
            entity_type_guess=entity.get("entity_type", ""),
            confidence=0.65,
            source_quote=quote,
            narrator_entity_id=narrator_id,
            scene_scope=f"chapter:{chapter_idx}",
            mention_source_type=_mention_source_type(quote),
            source_section_type=section_type,
        )
        if classification["mention_class"] == "kinship":
            db.record_kinship_mention(
                surface,
                chapter_idx,
                narrator_entity_id=narrator_id,
                confidence=0.65,
                evidence=_source_quote(chapter_text, surface),
            )

    for alias in ai_data.get("new_aliases_discovered", []):
        surface = alias.get("new_alias", "")
        if not surface:
            continue
        quote = alias.get("context_proof", "") or _source_quote(chapter_text, surface)
        db.add_mention_occurrence(
            surface_form=surface,
            chapter_idx=chapter_idx,
            sentence_offset=_sentence_offset(chapter_text, surface),
            entity_type_guess="INDIVIDUAL",
            confidence=0.55,
            source_quote=quote,
            narrator_entity_id=narrator_id,
            scene_scope=f"chapter:{chapter_idx}",
            mention_source_type=_mention_source_type(quote),
            source_section_type=section_type,
        )

    for alias in ai_data.get("new_group_aliases_discovered", []):
        surface = alias.get("new_alias", "")
        if not surface:
            continue
        quote = alias.get("context_proof", "") or _source_quote(chapter_text, surface)
        db.add_mention_occurrence(
            surface_form=surface,
            chapter_idx=chapter_idx,
            sentence_offset=_sentence_offset(chapter_text, surface),
            entity_type_guess="GROUP",
            confidence=0.55,
            source_quote=quote,
            narrator_entity_id=narrator_id,
            scene_scope=f"chapter:{chapter_idx}",
            mention_source_type=_mention_source_type(quote),
            source_section_type=section_type,
        )
