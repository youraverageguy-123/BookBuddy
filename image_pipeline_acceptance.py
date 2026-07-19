"""Non-destructive image-pipeline acceptance runner for user-owned EPUBs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from config import IMAGE_EVIDENCE_SCHEMA_VERSION
from db_manager import BookDatabase
from epub_parser import parse_epub
from graph_invariant_tests import assert_graph_invariants
from image_pipeline import parse_chapter_images
from snapshot_manager import EvidenceStore, ReplayCoordinator


def _payload(image_evidence: list[dict], chapter) -> dict:
    return {
        "pov_character_found": "",
        "new_aliases_discovered": [],
        "new_group_aliases_discovered": [],
        "entities_present": [],
        "relationships": [],
        "major_events": [],
        "entity_semantic_relations": [],
        "language_observations": [],
        "life_status_events": [],
        "legacy_signals": [],
        "image_evidence_schema_version": IMAGE_EVIDENCE_SCHEMA_VERSION,
        "image_evidence": image_evidence,
        "_section_type": getattr(chapter, "section_type", "CHAPTER"),
        "_chapter_title": getattr(chapter, "title", ""),
        "_metadata": {},
    }


def accept_epub(epub_path: str | Path) -> dict:
    source = Path(epub_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    book = parse_epub(str(source))
    with tempfile.TemporaryDirectory(prefix="bookbuddy-image-acceptance-") as db_dir:
        db = BookDatabase(db_dir)
        degraded = 0
        image_count = 0
        cacheable_count = 0
        try:
            for chapter in book.chapters:
                evidence = parse_chapter_images(chapter.image_descriptors, db=db)
                image_count += len(evidence)
                degraded += sum(
                    1 for item in evidence
                    if (item.get("failure_state") or {}).get("state") in {"degraded", "failed"}
                )
                EvidenceStore.record(
                    db,
                    chapter.index,
                    _payload(evidence, chapter),
                    trigger_reason="image_acceptance",
                )
            for chapter in book.chapters:
                repeated = parse_chapter_images(chapter.image_descriptors, db=db)
                cacheable_count += sum(
                    1 for item in repeated
                    if item.get("cache_status") in {"exact_hash_hit", "skipped_decoration"}
                )
        finally:
            db.close()

        coordinator = ReplayCoordinator(db_dir)
        first = coordinator.run(mode="full", reason="image_acceptance")
        verification = coordinator.run(mode="verify", reason="image_acceptance_verify")
        sanity = assert_graph_invariants(str(Path(db_dir) / "graph.db"))
        if not first.get("promoted") or not verification.get("verified"):
            raise AssertionError("Image replay was not deterministic")
        if cacheable_count < image_count - degraded:
            raise AssertionError("Not all reusable image artifacts produced cache hits")
        return {
            "epub": str(source),
            "chapters": len(book.chapters),
            "images": image_count,
            "degraded_images": degraded,
            "cache_reuse_outcomes": cacheable_count,
            "replay_verified": True,
            "graph_sanity_issues": sanity["issue_count"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", nargs="+", help="User-owned EPUB path(s) to validate")
    args = parser.parse_args()
    results = [accept_epub(path) for path in args.epub]
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
