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


def index_ai_mentions(db, ai_data: dict, chapter_idx: int, chapter_text: str):
    for entity in ai_data.get("entities_present", []):
        surface = entity.get("name", "")
        if not surface:
            continue
        db.add_mention_occurrence(
            surface_form=surface,
            chapter_idx=chapter_idx,
            sentence_offset=_sentence_offset(chapter_text, surface),
            entity_type_guess=entity.get("entity_type", ""),
            confidence=0.65,
            source_quote=_source_quote(chapter_text, surface),
        )

    for alias in ai_data.get("new_aliases_discovered", []):
        surface = alias.get("new_alias", "")
        if not surface:
            continue
        db.add_mention_occurrence(
            surface_form=surface,
            chapter_idx=chapter_idx,
            sentence_offset=_sentence_offset(chapter_text, surface),
            entity_type_guess="INDIVIDUAL",
            confidence=0.55,
            source_quote=alias.get("context_proof", "") or _source_quote(chapter_text, surface),
        )

    for alias in ai_data.get("new_group_aliases_discovered", []):
        surface = alias.get("new_alias", "")
        if not surface:
            continue
        db.add_mention_occurrence(
            surface_form=surface,
            chapter_idx=chapter_idx,
            sentence_offset=_sentence_offset(chapter_text, surface),
            entity_type_guess="GROUP",
            confidence=0.55,
            source_quote=alias.get("context_proof", "") or _source_quote(chapter_text, surface),
        )
