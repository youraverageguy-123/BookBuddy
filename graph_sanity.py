import json
import sqlite3
import sys


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,))
    return cursor.fetchone() is not None


def run_graph_sanity(graph_path: str) -> dict:
    conn = sqlite3.connect(graph_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        issues = []

        cursor.execute("""
            SELECT lower(canonical_name), COUNT(*), GROUP_CONCAT(id)
            FROM entities
            GROUP BY lower(canonical_name)
            HAVING COUNT(*) > 1
        """)
        for name, count, ids in cursor.fetchall():
            issues.append({"type": "duplicate_canonical", "name": name, "count": count, "entity_ids": ids})

        cursor.execute("""
            SELECT a.id, a.alias_name, a.entity_id
            FROM aliases a
            LEFT JOIN entities e ON a.entity_id = e.id
            WHERE e.id IS NULL
        """)
        for alias_id, alias_name, entity_id in cursor.fetchall():
            issues.append({"type": "orphan_alias", "alias_id": alias_id, "alias": alias_name, "entity_id": entity_id})

        cursor.execute("""
            SELECT a.id, e.canonical_name, a.alias_name
            FROM aliases a
            JOIN entities e ON a.entity_id = e.id
            WHERE lower(e.canonical_name) = lower(a.alias_name)
        """)
        for alias_id, canonical_name, alias_name in cursor.fetchall():
            issues.append({"type": "self_alias", "alias_id": alias_id, "canonical_name": canonical_name, "alias": alias_name})

        if _table_exists(cursor, "identity_promotions"):
            cursor.execute("SELECT id FROM entities WHERE canonical_name = '[UNNAMED_POV]'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM identity_promotions WHERE COALESCE(status, 'candidate') = 'accepted'")
                if cursor.fetchone()[0] == 0:
                    issues.append({"type": "unpromoted_narrator", "entity": "[UNNAMED_POV]"})

        cursor.execute("""
            SELECT ep.event_id, ep.entity_id
            FROM event_participants ep
            LEFT JOIN events ev ON ep.event_id = ev.id
            LEFT JOIN entities e ON ep.entity_id = e.id
            WHERE ev.id IS NULL OR e.id IS NULL
        """)
        for event_id, entity_id in cursor.fetchall():
            issues.append({"type": "orphan_event_participant", "event_id": event_id, "entity_id": entity_id})

        if _table_exists(cursor, "title_links"):
            cursor.execute("""
                SELECT title_key, COUNT(DISTINCT entity_id), GROUP_CONCAT(entity_id)
                FROM title_links
                WHERE COALESCE(status, 'candidate') != 'rejected'
                GROUP BY title_key
                HAVING COUNT(DISTINCT entity_id) > 1
            """)
            for title_key, count, ids in cursor.fetchall():
                issues.append({"type": "conflicting_title_link", "title_key": title_key, "count": count, "entity_ids": ids})

        return {"issue_count": len(issues), "issues": issues}
    finally:
        conn.close()


def main():
    if len(sys.argv) != 2:
        print("Usage: python graph_sanity.py <graph.db>")
        sys.exit(1)
    print(json.dumps(run_graph_sanity(sys.argv[1]), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
