import json
import os
import re
import shutil
import sqlite3
from datetime import datetime


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
        if "schema_metadata" in tables:
            cursor.execute("""
                INSERT OR REPLACE INTO schema_metadata (key, value)
                VALUES ('inheritance_policy', 'probable_aliases_titles_promotions_confirmed_relationships_parent_only')
            """)
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
