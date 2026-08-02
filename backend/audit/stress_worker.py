"""Isolated worker for the intentionally expensive synthetic replay audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from audit.database import inspect_database
from db_manager import BookDatabase
from graph_invariant_tests import assert_graph_invariants
from snapshot_manager import EvidenceStore, ReplayCoordinator


def run(work_dir: Path, output: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    db = BookDatabase(str(work_dir))
    try:
        for chapter in range(2_000):
            suffix = hashlib.sha256(f"scale:{chapter}".encode()).hexdigest()[:10]
            names = [f"Stressperson {suffix}{letter}" for letter in "abcde"]
            EvidenceStore.record(db, chapter, {
                "pov_character_found": names[0],
                "new_aliases_discovered": [
                    {"canonical_name": name, "new_alias": f"Echo {suffix}{index}{variant}", "context_proof": f"{name} was called Echo {suffix}{index}{variant}."}
                    for index, name in enumerate(names) for variant in "xy"
                ],
                "new_group_aliases_discovered": [],
                "entities_present": [{"name": name, "entity_type": "INDIVIDUAL", "active_status": "active_participant"} for name in names],
                "relationships": [
                    {"source": names[left], "target": names[right], "trust_score": 0, "relationship_evidence": f"{names[left]} met {names[right]}.", "event_reference": ""}
                    for left in range(5) for right in range(left + 1, 5)
                ],
                "major_events": [], "entity_semantic_relations": [], "language_observations": [],
                "life_status_events": [], "legacy_signals": [], "_metadata": {"audit_scale": "synthetic_v1"},
            }, trigger_reason="stress_audit")
    finally:
        db.close()
    started = time.perf_counter()
    replay = ReplayCoordinator(str(work_dir)).run(mode="full", reason="stress_audit")
    elapsed = time.perf_counter() - started
    graph = work_dir / "graph.db"
    with sqlite3.connect(graph) as conn:
        counts = {
            table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in ("chapter_evidence_revisions", "entities", "aliases", "relationships", "relationship_history")
        }
    integrity = inspect_database(graph)
    sanity = assert_graph_invariants(str(graph))
    verify = ReplayCoordinator(str(work_dir)).run(mode="verify", reason="stress_verify")
    output.write_text(json.dumps({
        "counts": counts, "replay_seconds": elapsed,
        "replay": {"promoted": replay.get("promoted"), "chapters": replay.get("chapters")},
        "verify": {"verified": verify.get("verified"), "chapters": verify.get("chapters")},
        "integrity": integrity["passed"], "sanity_issues": sanity["issue_count"],
    }, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    parser.add_argument("output")
    args = parser.parse_args()
    run(Path(args.work_dir), Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
