import json
import os
import re
import shutil
import sqlite3
from datetime import datetime

from config import INHERITED_GRAPH_CONFIDENCE
from db_manager import BookDatabase


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) > 2 and token not in {"the", "and", "book", "volume", "novel"}
    }


def find_series_matches(
    library_dir: str,
    title: str,
    author: str = "",
    limit: int = 5,
    exclude_book_name: str | None = None,
) -> list[dict]:
    title_tokens = _tokens(title)
    author_tokens = _tokens(author)
    matches = []

    if not os.path.exists(library_dir):
        return []

    for book_name in os.listdir(library_dir):
        if exclude_book_name and book_name == exclude_book_name:
            continue

        book_path = os.path.join(library_dir, book_name)
        if not os.path.isdir(book_path):
            continue

        candidate_tokens = _tokens(book_name.replace("_", " "))
        title_overlap = len(title_tokens & candidate_tokens)
        author_overlap = len(author_tokens & candidate_tokens)
        score = title_overlap * 2 + author_overlap

        if score <= 0:
            continue

        sessions = [
            s for s in os.listdir(book_path)
            if os.path.isdir(os.path.join(book_path, s))
        ]
        if not sessions:
            continue

        matches.append({
            "book_name": book_name,
            "sessions": sessions,
            "score": score,
        })

    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]


def latest_session_for_book(library_dir: str, book_name: str) -> str | None:
    book_path = os.path.join(library_dir, book_name)
    if not os.path.isdir(book_path):
        return None

    sessions = [
        s for s in os.listdir(book_path)
        if os.path.isdir(os.path.join(book_path, s))
    ]
    if not sessions:
        return None

    sessions.sort(
        key=lambda session: os.path.getmtime(os.path.join(book_path, session)),
        reverse=True,
    )
    return sessions[0]


def inherit_series_graph(
    library_dir: str,
    parent_book: str,
    parent_session: str,
    target_session_dir: str,
    confirmed_relationship_confidence: float = 0.6,
    target_book: str | None = None,
    target_session: str | None = None,
    inherited_confidence: float = INHERITED_GRAPH_CONFIDENCE,
) -> bool:
    source_graph = os.path.join(library_dir, parent_book, parent_session, "database", "graph.db")
    target_db_dir = os.path.join(target_session_dir, "database")
    target_graph = os.path.join(target_db_dir, "graph.db")

    if not os.path.exists(source_graph):
        return False

    os.makedirs(target_db_dir, exist_ok=True)
    if not os.path.exists(target_graph):
        shutil.copy2(source_graph, target_graph)
        prune_inherited_graph(target_graph, confirmed_relationship_confidence)
        db = BookDatabase(target_db_dir)
        try:
            db.mark_graph_as_inherited(
                parent_book=parent_book,
                parent_session=parent_session,
                target_book=target_book,
                target_session=target_session,
                inherited_confidence=inherited_confidence,
            )
        finally:
            db.close()
    return True


def prune_inherited_graph(graph_path: str, confirmed_relationship_confidence: float = 0.6):
    conn = sqlite3.connect(graph_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tables = {row[0] for row in cursor.fetchall()}

        if "aliases" in tables:
            cursor.execute("""
                DELETE FROM aliases
                WHERE COALESCE(status, 'candidate') NOT IN ('accepted', 'probable', 'review')
            """)
        if "title_links" in tables:
            cursor.execute("""
                DELETE FROM title_links
                WHERE COALESCE(status, 'candidate') IN ('rejected', 'expired')
            """)
        if "merge_candidates" in tables:
            cursor.execute("DELETE FROM merge_candidates")
        if "ghost_merge_candidates" in tables:
            cursor.execute("DELETE FROM ghost_merge_candidates")
        if "conflict_records" in tables:
            cursor.execute("DELETE FROM conflict_records WHERE COALESCE(status, 'open') = 'rejected'")
        if "relationship_history" in tables:
            cursor.execute(
                "DELETE FROM relationship_history WHERE COALESCE(confidence, 0.0) < ?",
                (confirmed_relationship_confidence,),
            )
        if "event_consequences" in tables and "relationship_history" in tables:
            cursor.execute("""
                DELETE FROM event_consequences
                WHERE rel_key IS NOT NULL
                  AND id NOT IN (
                      SELECT DISTINCT consequence_id
                      FROM relationship_history
                      WHERE consequence_id IS NOT NULL
                  )
            """)
        if "relationships" in tables and "relationship_history" in tables:
            cursor.execute("""
                DELETE FROM relationships
                WHERE rel_key NOT IN (SELECT DISTINCT rel_key FROM relationship_history)
            """)
        if "relationship_social_evidence" in tables:
            cursor.execute(
                "DELETE FROM relationship_social_evidence WHERE COALESCE(confidence, 0.0) < ?",
                (max(0.2, confirmed_relationship_confidence * 0.5),),
            )
        if "relationship_social_edges" in tables and "relationship_social_evidence" in tables:
            cursor.execute("""
                DELETE FROM relationship_social_edges
                WHERE edge_key NOT IN (
                    SELECT DISTINCT edge_key
                    FROM relationship_social_evidence
                )
            """)
        if "relationship_community_members" in tables and "relationship_communities" in tables:
            cursor.execute("DELETE FROM relationship_community_members")
            cursor.execute("DELETE FROM relationship_communities")
        if "entity_social_metrics" in tables:
            cursor.execute("DELETE FROM entity_social_metrics")
        if "events" in tables:
            cursor.execute("DELETE FROM events WHERE summary LIKE 'System skipped:%'")
        if "event_participants" in tables and "events" in tables:
            cursor.execute("""
                DELETE FROM event_participants
                WHERE event_id NOT IN (SELECT id FROM events)
            """)
        if "event_causal_edges" in tables and "events" in tables:
            cursor.execute("""
                DELETE FROM event_causal_edges
                WHERE parent_event_id NOT IN (SELECT id FROM events)
                   OR child_event_id NOT IN (SELECT id FROM events)
            """)
        if "event_cluster_members" in tables and "events" in tables:
            cursor.execute("""
                DELETE FROM event_cluster_members
                WHERE event_id NOT IN (SELECT id FROM events)
            """)
        if "event_clusters" in tables and "event_cluster_members" in tables:
            cursor.execute("""
                DELETE FROM event_clusters
                WHERE id NOT IN (SELECT DISTINCT cluster_id FROM event_cluster_members)
            """)
        if "landmark_event_links" in tables and "events" in tables:
            cursor.execute("""
                DELETE FROM landmark_event_links
                WHERE event_id NOT IN (SELECT id FROM events)
                   OR landmark_id NOT IN (SELECT id FROM event_landmarks)
            """)
        if "landmark_hierarchy" in tables:
            cursor.execute("""
                DELETE FROM landmark_hierarchy
                WHERE parent_landmark_id NOT IN (SELECT id FROM event_landmarks)
                   OR child_landmark_id NOT IN (SELECT id FROM event_landmarks)
            """)
        if "landmark_resolution_evidence" in tables:
            cursor.execute("""
                DELETE FROM landmark_resolution_evidence
                WHERE (event_id IS NOT NULL AND event_id NOT IN (SELECT id FROM events))
                   OR (landmark_id IS NOT NULL AND landmark_id NOT IN (SELECT id FROM event_landmarks))
            """)
        if "schema_metadata" in tables:
            cursor.execute("""
                INSERT OR REPLACE INTO schema_metadata (key, value)
                VALUES ('inheritance_policy', 'parent_only_boundary_aware_inherited_confidence')
            """)
            cursor.execute("""
                INSERT OR REPLACE INTO schema_metadata (key, value)
                VALUES ('inherited_graph_confidence', ?)
            """, (str(INHERITED_GRAPH_CONFIDENCE),))
        conn.commit()
    finally:
        conn.close()


def write_continuity_metadata(
    session_dir: str,
    current_book: str,
    parent_book: str | None = None,
    parent_session: str | None = None,
    inherited_graph: bool = False,
    session_type: str | None = None,
):
    resolved_session_type = session_type or ("inherited-series" if parent_book else "standalone")
    metadata = {
        "current_book": current_book,
        "session_type": resolved_session_type,
        "parent_book": parent_book,
        "parent_session": parent_session,
        "inherited_graph": inherited_graph,
        "created_at": datetime.now().isoformat(),
        "spoiler_policy": "parent books only; no future book access",
    }

    os.makedirs(session_dir, exist_ok=True)
    with open(os.path.join(session_dir, "continuity.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
