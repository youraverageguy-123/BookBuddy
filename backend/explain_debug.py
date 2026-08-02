"""Print a single engine-scoped resolver explanation as JSON."""

from __future__ import annotations

import argparse
import json

from db_manager import BookDatabase
from explanation_service import ExplanationService


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect BookBuddy resolver evidence without changing graph state.")
    parser.add_argument("--db-dir", required=True, help="Session database directory containing graph.db")
    parser.add_argument("--kind", required=True, choices=("entity", "landmark", "life_status", "relationship", "snapshot", "evidence_revision"))
    parser.add_argument("--subject", required=True, help="Entity/landmark/relationship key or chapter number")
    parser.add_argument("--chapter", type=int)
    parser.add_argument("--revision", type=int)
    args = parser.parse_args()

    db = BookDatabase(args.db_dir)
    try:
        result = ExplanationService(db).explain(args.kind, args.subject, chapter=args.chapter, revision=args.revision)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
