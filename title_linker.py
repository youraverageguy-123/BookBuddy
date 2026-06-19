from alias_validator import TITLE_LINK


def maybe_add_title_link(db, entity_id: int, title: str, chapter_idx: int, evidence: str, validation_result):
    if validation_result.status != TITLE_LINK:
        return None
    return db.add_title_link(
        entity_id=entity_id,
        title_text=title,
        chapter_idx=chapter_idx,
        evidence=evidence,
        confidence=max(0.1, 0.55 + validation_result.confidence_delta),
        status="candidate",
    )
