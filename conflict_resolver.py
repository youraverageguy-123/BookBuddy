import json


AUTO_RESOLVABLE_TYPES = {"alias_self", "alias_rejected"}


def rank_open_conflicts(db) -> list[dict]:
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, conflict_type, entity_a_id, entity_b_id, chapter, payload, created_at
            FROM conflict_records
            WHERE COALESCE(status, 'open') = 'open'
            ORDER BY
                CASE conflict_type
                    WHEN 'alias_collision' THEN 1
                    WHEN 'merge_conflict' THEN 2
                    WHEN 'relationship_contradiction' THEN 3
                    ELSE 9
                END,
                chapter,
                id
        """)
        rows = []
        for conflict_id, conflict_type, a_id, b_id, chapter, payload, created_at in cursor.fetchall():
            try:
                decoded = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                decoded = {"raw_payload": payload}
            rows.append({
                "id": conflict_id,
                "conflict_type": conflict_type,
                "entity_a_id": a_id,
                "entity_b_id": b_id,
                "chapter": chapter,
                "payload": decoded,
                "created_at": created_at,
            })
        return rows


def resolve_trivial_conflicts(db) -> int:
    resolved = 0
    for conflict in rank_open_conflicts(db):
        if conflict["conflict_type"] in AUTO_RESOLVABLE_TYPES:
            db.resolve_conflict(conflict["id"], "resolved", "Auto-resolved trivial conflict.")
            resolved += 1
    return resolved
