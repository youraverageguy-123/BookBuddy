from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any, Iterable


SOURCE_TABLES = {
    "chapter_evidence_revisions",
    "image_evidence_revisions",
    "image_occurrence_provenance",
}
RETENTION_TABLES = {
    "reader_snapshot_current",
    "reader_snapshot_revisions",
    "resolver_decisions",
}
OPERATIONAL_TABLES = {
    "chapter_invalidations",
    "chapter_processing_checkpoints",
    "image_parse_cache",
    "performance_metrics",
    "schema_metadata",
}
DERIVED_TABLES = {
    "aliases", "chapter_boundaries", "chapter_pov", "chapter_visibility_scopes",
    "conflict_records", "entities", "entity_legacy_signals", "entity_ontology_evidence",
    "entity_search_terms", "entity_semantic_relations", "entity_social_metrics",
    "entity_state_history", "entity_type_votes", "event_causal_edges", "event_cluster_members",
    "event_clusters", "event_consequences", "event_landmarks", "event_participants",
    "event_search_terms", "events", "ghost_merge_candidates", "identity_promotions",
    "identity_resolution_evidence", "kinship_mentions", "knowledge_object_relations",
    "landmark_assertions", "landmark_event_links", "landmark_hierarchy", "landmark_importance",
    "landmark_locations", "landmark_names", "landmark_participants", "landmark_perspectives",
    "landmark_resolution_evidence", "language_observations", "life_status_evidence",
    "life_status_snapshots", "life_status_timeline_segments", "mention_occurrences", "merge_audit",
    "merge_candidates", "name_semantic_relations", "reference_mentions", "relationship_communities",
    "relationship_community_members", "relationship_history", "relationship_social_edges",
    "relationship_social_evidence", "relationships", "terminology_aliases", "terminology_attributes",
    "terminology_evidence", "terminology_functions", "terminology_objects", "terminology_occurrences",
    "title_links", "unresolved_mentions",
}
TABLE_CLASSIFICATION = {
    **{name: "source" for name in SOURCE_TABLES},
    **{name: "retention" for name in RETENTION_TABLES},
    **{name: "operational" for name in OPERATIONAL_TABLES},
    **{name: "derived" for name in DERIVED_TABLES},
}
VOLATILE_COLUMNS = {"created_at", "updated_at", "resolved_at"}


def _connect(path: str | Path, *, readonly: bool = True) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    if readonly:
        conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def inspect_database(path: str | Path) -> dict[str, Any]:
    with closing(_connect(path)) as conn:
        integrity = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
        foreign_keys = [dict(row) for row in conn.execute("PRAGMA foreign_key_check")]
        schema: dict[str, Any] = {}
        unknown = []
        for table in _tables(conn):
            if table not in TABLE_CLASSIFICATION:
                unknown.append(table)
            columns = [dict(row) for row in conn.execute(f'PRAGMA table_xinfo("{table}")')]
            indexes = []
            for index in conn.execute(f'PRAGMA index_list("{table}")'):
                entry = dict(index)
                entry["columns"] = [row[2] for row in conn.execute(f'PRAGMA index_info("{index[1]}")')]
                indexes.append(entry)
            schema[table] = {
                "classification": TABLE_CLASSIFICATION.get(table, "unknown"),
                "row_count": conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0],
                "columns": columns,
                "foreign_keys": [dict(row) for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')],
                "indexes": indexes,
            }
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "schema": schema,
            "unknown_tables": unknown,
            "passed": integrity == ["ok"] and not foreign_keys and not unknown,
        }


def canonical_database(
    path: str | Path,
    *,
    categories: Iterable[str] = ("derived", "retention"),
    volatile_columns: set[str] | None = None,
) -> dict[str, Any]:
    categories = set(categories)
    volatile = VOLATILE_COLUMNS if volatile_columns is None else volatile_columns
    with closing(_connect(path)) as conn:
        found = set(_tables(conn))
        unknown = sorted(found - set(TABLE_CLASSIFICATION))
        if unknown:
            raise ValueError(f"Unclassified database tables: {unknown}")
        result: dict[str, Any] = {}
        for table in sorted(found):
            if TABLE_CLASSIFICATION[table] not in categories:
                continue
            info = list(conn.execute(f'PRAGMA table_info("{table}")'))
            columns = [str(row[1]) for row in info if str(row[1]) not in volatile]
            pk_columns = [str(row[1]) for row in sorted(info, key=lambda item: int(item[5])) if int(row[5])]
            order = pk_columns or columns
            select = ", ".join(f'"{column}"' for column in columns)
            order_by = ", ".join(f'"{column}"' for column in order)
            rows = [
                [_canonical_value(row[column]) for column in columns]
                for row in conn.execute(f'SELECT {select} FROM "{table}" ORDER BY {order_by}')
            ]
            result[table] = {"columns": columns, "rows": rows}
        return result


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, str) and value[:1] in {"{", "["}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def compare_databases(
    expected: str | Path,
    actual: str | Path,
    *,
    categories: Iterable[str] = ("derived", "retention"),
) -> dict[str, Any]:
    left = canonical_database(expected, categories=categories)
    right = canonical_database(actual, categories=categories)
    mismatches = []
    for table in sorted(set(left) | set(right)):
        if left.get(table) != right.get(table):
            left_rows = left.get(table, {}).get("rows", [])
            right_rows = right.get(table, {}).get("rows", [])
            first_difference = None
            for index in range(max(len(left_rows), len(right_rows))):
                lrow = left_rows[index] if index < len(left_rows) else None
                rrow = right_rows[index] if index < len(right_rows) else None
                if lrow != rrow:
                    first_difference = {"index": index, "expected": lrow, "actual": rrow}
                    break
            mismatches.append({
                "table": table,
                "expected_rows": len(left_rows),
                "actual_rows": len(right_rows),
                "first_difference": first_difference,
            })
    return {"matched": not mismatches, "mismatches": mismatches, "tables_compared": len(set(left) | set(right))}


def export_evidence_bundle(graph_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    with closing(_connect(graph_path)) as conn:
        payload = {
            "schema_version": "bookbuddy_evidence_bundle_v1",
            "tables": {},
        }
        for table in sorted(SOURCE_TABLES):
            columns = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]
            rows = [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            payload["tables"][table] = {"columns": columns, "rows": rows}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    target = Path(output_path)
    target.write_bytes(raw)
    return {"path": str(target.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "rows": sum(len(v["rows"]) for v in payload["tables"].values())}


def import_evidence_bundle(bundle_path: str | Path, db_dir: str | Path) -> dict[str, Any]:
    from db_manager import BookDatabase

    payload = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "bookbuddy_evidence_bundle_v1":
        raise ValueError("Unsupported evidence bundle schema")
    database = BookDatabase(str(db_dir))
    conn = database._get_connection()
    imported = 0
    try:
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for table in sorted(SOURCE_TABLES):
            entry = payload.get("tables", {}).get(table)
            if not entry:
                continue
            columns = entry["columns"]
            placeholders = ", ".join("?" for _ in columns)
            names = ", ".join(f'"{name}"' for name in columns)
            rows = [[row.get(name) for name in columns] for row in entry["rows"]]
            if rows:
                conn.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', rows)
                imported += len(rows)
        conn.commit()
    finally:
        database.close()
    return {"rows": imported, "db_dir": str(Path(db_dir).resolve())}


def explain_query_plan(path: str | Path, query: str, parameters: tuple = ()) -> list[dict[str, Any]]:
    with closing(_connect(path)) as conn:
        return [dict(row) for row in conn.execute("EXPLAIN QUERY PLAN " + query, parameters)]
