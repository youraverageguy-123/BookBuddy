import json
import os
import sqlite3
import sys


def _norm(value: str) -> str:
    return " ".join(str(value).lower().strip().split())


def _f1(predicted: set, expected: set) -> dict:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "predicted": len(predicted),
        "expected": len(expected),
        "true_positive": true_positive,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _load_chapter_cache(db_dir: str) -> list[dict]:
    chapters = []
    idx = 0
    while True:
        path = os.path.join(db_dir, f"chapter_{idx}.json")
        if not os.path.exists(path):
            break
        with open(path, "r", encoding="utf-8") as f:
            chapters.append(json.load(f))
        idx += 1
    return chapters


def _load_graph_predictions(db_dir: str) -> dict | None:
    graph_path = os.path.join(db_dir, "graph.db")
    if not os.path.exists(graph_path):
        return None

    conn = sqlite3.connect(graph_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tables = {row[0] for row in cursor.fetchall()}

        predictions = {
            "aliases": set(),
            "entities": set(),
            "relationships": set(),
            "events": set(),
            "spoiler_events": set(),
            "title_links": set(),
            "identity_promotions": set(),
            "mentions": set(),
            "event_clusters": set(),
            "alias_conflicts": set(),
        }

        if {"entities", "aliases"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, a.alias_name
                FROM aliases a
                JOIN entities e ON a.entity_id = e.id
                WHERE COALESCE(a.status, 'candidate') IN ('accepted', 'probable')
            """)
            predictions["aliases"] = {
                (_norm(canonical_name), _norm(alias_name))
                for canonical_name, alias_name in cursor.fetchall()
                if alias_name
            }

        if "entities" in tables:
            cursor.execute("SELECT canonical_name, entity_type FROM entities")
            predictions["entities"] = {
                (_norm(name), _norm(entity_type))
                for name, entity_type in cursor.fetchall()
            }

        if {"relationships", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT es.canonical_name, et.canonical_name
                FROM relationships r
                JOIN entities es ON r.source_id = es.id
                JOIN entities et ON r.target_id = et.id
                WHERE r.current_trust_score IS NOT NULL
                   OR EXISTS (
                       SELECT 1
                       FROM relationship_history rh
                       WHERE rh.rel_key = r.rel_key
                   )
            """)
            predictions["relationships"] = {
                tuple(sorted((_norm(source), _norm(target))))
                for source, target in cursor.fetchall()
            }

        if "events" in tables:
            cursor.execute("SELECT chapter, summary FROM events")
            predictions["events"] = {
                (int(chapter), _norm(summary))
                for chapter, summary in cursor.fetchall()
            }
            predictions["spoiler_events"] = {event for _chapter, event in predictions["events"]}

        if {"title_links", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, t.title_text
                FROM title_links t
                JOIN entities e ON t.entity_id = e.id
                WHERE COALESCE(t.status, 'candidate') IN ('accepted', 'probable', 'candidate')
            """)
            predictions["title_links"] = {
                (_norm(canonical_name), _norm(title_text))
                for canonical_name, title_text in cursor.fetchall()
                if title_text
            }

        if {"identity_promotions", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT COALESCE(ep.canonical_name, '[UNNAMED_POV]'), er.canonical_name
                FROM identity_promotions p
                LEFT JOIN entities ep ON p.placeholder_entity_id = ep.id
                JOIN entities er ON p.resolved_entity_id = er.id
                WHERE COALESCE(p.status, 'candidate') IN ('accepted', 'probable')
            """)
            predictions["identity_promotions"] = {
                (_norm(placeholder), _norm(resolved))
                for placeholder, resolved in cursor.fetchall()
            }

        if "mention_occurrences" in tables:
            cursor.execute("SELECT chapter, surface_form, entity_type_guess FROM mention_occurrences")
            predictions["mentions"] = {
                (int(chapter), _norm(surface_form), _norm(entity_type_guess))
                for chapter, surface_form, entity_type_guess in cursor.fetchall()
            }

        if {"event_clusters", "event_cluster_members", "events"}.issubset(tables):
            cursor.execute("""
                SELECT ec.cluster_key, ev.chapter, ev.summary
                FROM event_cluster_members ecm
                JOIN event_clusters ec ON ecm.cluster_id = ec.id
                JOIN events ev ON ecm.event_id = ev.id
            """)
            predictions["event_clusters"] = {
                (_norm(cluster_key), int(chapter), _norm(summary))
                for cluster_key, chapter, summary in cursor.fetchall()
            }

        if "conflict_records" in tables:
            cursor.execute("""
                SELECT chapter, payload
                FROM conflict_records
                WHERE conflict_type = 'alias_collision'
            """)
            for chapter, payload in cursor.fetchall():
                try:
                    decoded = json.loads(payload) if payload else {}
                except json.JSONDecodeError:
                    decoded = {}
                predictions["alias_conflicts"].add((int(chapter or 0), _norm(decoded.get("alias", ""))))

        return predictions
    finally:
        conn.close()


def evaluate(db_dir: str, truth_path: str) -> dict:
    chapters = _load_chapter_cache(db_dir)
    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    predicted_aliases = set()
    predicted_entities = set()
    predicted_relationships = set()
    predicted_events = set()

    for chapter_idx, data in enumerate(chapters):
        for alias in data.get("new_aliases_discovered", []):
            predicted_aliases.add((_norm(alias.get("canonical_name", "")), _norm(alias.get("new_alias", ""))))
        for entity in data.get("entities_present", []):
            predicted_entities.add((_norm(entity.get("name", "")), _norm(entity.get("entity_type", ""))))
        for rel in data.get("relationships", []):
            pair = tuple(sorted((_norm(rel.get("source", "")), _norm(rel.get("target", "")))))
            predicted_relationships.add(pair)
        for event in data.get("major_events", []):
            predicted_events.add((chapter_idx, _norm(event)))

    expected_aliases = {
        (_norm(item.get("canonical_name", "")), _norm(item.get("alias", item.get("new_alias", ""))))
        for item in truth.get("aliases", [])
    }
    expected_entities = {
        (_norm(item.get("name", "")), _norm(item.get("entity_type", "")))
        for item in truth.get("entities", [])
    }
    expected_relationships = {
        tuple(sorted((_norm(item.get("source", "")), _norm(item.get("target", "")))))
        for item in truth.get("relationships", [])
    }
    expected_events = {
        (int(item.get("chapter", 0)), _norm(item.get("event", "")))
        for item in truth.get("major_events", [])
    }
    expected_title_links = {
        (_norm(item.get("canonical_name", "")), _norm(item.get("title", item.get("title_text", ""))))
        for item in truth.get("title_links", [])
    }
    expected_identity_promotions = {
        (_norm(item.get("placeholder", "[UNNAMED_POV]")), _norm(item.get("resolved", item.get("canonical_name", ""))))
        for item in truth.get("identity_promotions", truth.get("narrator_promotions", []))
    }
    expected_mentions = {
        (int(item.get("chapter", 0)), _norm(item.get("surface_form", "")), _norm(item.get("entity_type_guess", "")))
        for item in truth.get("mention_occurrences", truth.get("mentions", []))
    }
    expected_event_clusters = {
        (_norm(item.get("cluster_key", "")), int(item.get("chapter", 0)), _norm(item.get("event", item.get("summary", ""))))
        for item in truth.get("event_clusters", [])
    }

    spoiler_leakage_count = sum(
        1 for leak in truth.get("spoiler_leaks", [])
        if _norm(leak.get("text", "")) in {event for _chapter, event in predicted_events}
    )

    result = {
        "alias": _f1(predicted_aliases, expected_aliases),
        "entity": _f1(predicted_entities, expected_entities),
        "relationship_pair": _f1(predicted_relationships, expected_relationships),
        "major_event": _f1(predicted_events, expected_events),
        "spoiler_leakage_count": spoiler_leakage_count,
        "chapters_evaluated": len(chapters),
    }
    graph_predictions = _load_graph_predictions(db_dir)
    if graph_predictions:
        result["graph_alias"] = _f1(graph_predictions["aliases"], expected_aliases)
        result["graph_entity"] = _f1(graph_predictions["entities"], expected_entities)
        result["graph_relationship_pair"] = _f1(graph_predictions["relationships"], expected_relationships)
        result["graph_event"] = _f1(graph_predictions["events"], expected_events)
        result["graph_title_link"] = _f1(graph_predictions["title_links"], expected_title_links)
        result["graph_identity_promotion"] = _f1(graph_predictions["identity_promotions"], expected_identity_promotions)
        result["graph_mention_provenance"] = _f1(graph_predictions["mentions"], expected_mentions)
        result["graph_event_cluster"] = _f1(graph_predictions["event_clusters"], expected_event_clusters)
        result["graph_alias_conflict_count"] = len(graph_predictions["alias_conflicts"])
        result["graph_spoiler_leakage_count"] = sum(
            1 for leak in truth.get("spoiler_leaks", [])
            if _norm(leak.get("text", "")) in graph_predictions["spoiler_events"]
        )

    return result


def main():
    if len(sys.argv) != 3:
        print("Usage: python evaluation_runner.py <db_dir> <truth.json>")
        sys.exit(1)

    result = evaluate(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
