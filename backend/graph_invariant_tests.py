import sys

from graph_sanity import run_graph_sanity


BLOCKING_ISSUES = {
    "duplicate_canonical",
    "conflicting_title_link",
    "orphan_alias",
    "self_alias",
    "orphan_event_participant",
    "orphan_image_occurrence_provenance",
    "multiple_active_image_occurrence_revisions",
    "image_evidence_payload_hash_mismatch",
    "invalid_active_image_evidence_schema",
    "serialized_image_raw_bytes",
    "authoritative_image_evidence_not_normalized",
    "invalid_image_cache_identity",
    "orphan_terminology_alias",
    "orphan_terminology_evidence",
}


def assert_graph_invariants(graph_path: str) -> dict:
    result = run_graph_sanity(graph_path)
    blocking = [issue for issue in result["issues"] if issue["type"] in BLOCKING_ISSUES]
    if blocking:
        details = "\n".join(f"- {issue}" for issue in blocking)
        raise AssertionError(f"Graph invariant failure:\n{details}")
    return result


def main():
    if len(sys.argv) != 2:
        print("Usage: python graph_invariant_tests.py <graph.db>")
        sys.exit(1)
    result = assert_graph_invariants(sys.argv[1])
    print(f"Graph invariants passed with {result['issue_count']} non-blocking issue(s).")


if __name__ == "__main__":
    main()
