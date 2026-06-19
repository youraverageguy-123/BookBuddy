TEMPORARY_POV_NAME = "[UNNAMED_POV]"


def promote_named_pov(db, true_entity_id: int, chapter_idx: int, evidence: str = "") -> bool:
    if not true_entity_id:
        return False

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM entities WHERE canonical_name = ?", (TEMPORARY_POV_NAME,))
        row = cursor.fetchone()
        if not row or row[0] == true_entity_id:
            return False
        placeholder_id = row[0]

    db.record_identity_promotion(
        placeholder_entity_id=placeholder_id,
        resolved_entity_id=true_entity_id,
        chapter_idx=chapter_idx,
        evidence=evidence or "Named POV established by chapter extraction.",
        confidence=0.85,
        status="accepted",
    )
    db.merge_entities(true_entity_id, placeholder_id, preferred_surviving_id=true_entity_id)
    return True
