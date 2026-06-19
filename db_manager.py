import sqlite3
import os
import re
import json
from collections import OrderedDict
from config import (
    ACTIVE_ENTITY_LIMIT,
    ALIAS_ACCEPTED_CONFIDENCE,
    ALIAS_ACCEPTED_SUPPORT,
    ALIAS_BASE_CONFIDENCE,
    ALIAS_EXPIRED_CONFIDENCE,
    ALIAS_REVIEW_CONFIDENCE,
    ALIAS_SUPPORT_CONFIDENCE_BOOST,
    CONFIDENCE_DECAY_AFTER_CHAPTERS,
    CONFIDENCE_DECAY_FACTOR,
    ENTITY_BASE_CONFIDENCE,
    ENTITY_REVIEW_CONFIDENCE,
    ENTITY_SUPPORT_CONFIDENCE_BOOST,
    ENTITY_TYPE_CHANGE_CONFIDENCE,
    ENTITY_TYPE_CHANGE_SUPPORT,
    EVENT_CONTEXT_LIMIT,
    GRAPH_SCHEMA_VERSION,
    MEMORY_CARD_LIMIT,
    MEMORY_CARD_RELATIONSHIP_LIMIT,
    MEMORY_CARD_RECENT_EVENT_LIMIT,
    RELATIONSHIP_BASE_CONFIDENCE,
    RELATIONSHIP_CONTRADICTION_DELTA,
    REGEX_CACHE_SIZE,
)

class BookDatabase:
    # Top-K Configurable limit to prevent LLM prompt token explosion
    ACTIVE_ENTITY_LIMIT = ACTIVE_ENTITY_LIMIT 

    def __init__(self, db_dir: str):
        self.db_path = os.path.join(db_dir, "graph.db")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._regex_cache = OrderedDict()
        self._initialize_schema()

    def _get_connection(self):
        return self._conn

    def close(self):
        self._conn.close()

    @staticmethod
    def normalize_alias_key(value: str) -> str:
        value = " ".join(str(value or "").lower().strip().split())
        value = re.sub(r"[^\w\s]", "", value)
        return " ".join(value.split())

    def _infer_surface_form_class(self, name: str, entity_type: str) -> str:
        stripped = str(name or "").strip()
        lower = stripped.lower()
        if entity_type == "LOCATION":
            return "place_name" if any(ch.isupper() for ch in stripped) else "location_fragment"
        if lower.startswith("the "):
            return "title" if stripped[4:5].isupper() else "descriptor"
        if lower in {
            "butler", "nurse", "policeman", "doctor", "reporter", "conductor",
            "chambermaid", "lieutenant", "chauffeur", "guard", "servant",
        }:
            return "role"
        if stripped and not any(ch.isupper() for ch in stripped):
            return "descriptor"
        if len(stripped.split()) == 1:
            return "proper_name"
        return "compound_name"

    def _infer_location_subtype(self, name: str) -> str | None:
        lower = str(name or "").lower()
        if not lower:
            return None
        if any(word in lower for word in ("street", "road", "avenue", "lane", "drive")):
            return "road"
        if any(word in lower for word in ("house", "hotel", "club", "building", "room", "apartment")):
            return "building"
        if any(word in lower for word in ("sound", "bay", "river", "valley", "island", "coast")):
            return "region"
        if len(lower.split()) == 1 and lower in {"sound", "valley", "island", "bay", "river"}:
            return "fragment"
        return "place"

    def _initial_importance(self, name: str, entity_type: str) -> tuple[float, float, str, str | None]:
        surface_class = self._infer_surface_form_class(name, entity_type)
        location_subtype = self._infer_location_subtype(name) if entity_type == "LOCATION" else None
        importance = 0.45
        visibility = 0.45
        if surface_class in {"proper_name", "compound_name", "place_name"}:
            importance = 0.6
            visibility = 0.6
        if surface_class in {"role", "descriptor", "location_fragment"} or location_subtype == "fragment":
            importance = 0.2
            visibility = 0.15
        if entity_type == "GROUP":
            importance = max(importance, 0.55)
            visibility = max(visibility, 0.5)
        return importance, visibility, surface_class, location_subtype

    def _initialize_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT UNIQUE,
                    entity_type TEXT,
                    first_seen_chapter INTEGER,
                    last_verified_chapter INTEGER,
                    mention_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.55,
                    type_support_count INTEGER DEFAULT 1,
                    importance_score REAL DEFAULT 0.45,
                    visibility_score REAL DEFAULT 0.45,
                    surface_form_class TEXT DEFAULT 'proper_name',
                    location_subtype TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_name TEXT,
                    alias_key TEXT,
                    entity_id INTEGER,
                    chapter_found INTEGER,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.35,
                    support_count INTEGER DEFAULT 1,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    status TEXT DEFAULT 'candidate',
                    UNIQUE(alias_name, entity_id),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mention_occurrences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    surface_form TEXT NOT NULL,
                    normalized_form TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    sentence_offset INTEGER,
                    paragraph_offset INTEGER,
                    speaker TEXT,
                    entity_type_guess TEXT,
                    confidence REAL DEFAULT 0.5,
                    source_quote TEXT,
                    linked_entity_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(linked_entity_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS title_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    title_text TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    chapter_found INTEGER,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.55,
                    support_count INTEGER DEFAULT 1,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    status TEXT DEFAULT 'candidate',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(entity_id, title_key),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS identity_promotions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    placeholder_entity_id INTEGER,
                    resolved_entity_id INTEGER NOT NULL,
                    chapter INTEGER NOT NULL,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.75,
                    status TEXT DEFAULT 'candidate',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(placeholder_entity_id, resolved_entity_id),
                    FOREIGN KEY(placeholder_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(resolved_entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_type_votes (
                    entity_id INTEGER,
                    entity_type TEXT,
                    support_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.55,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    PRIMARY KEY (entity_id, entity_type),
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)
            
            # P0 Fix: Symmetric naming conventions to prevent future developer confusion
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS merge_candidates (
                    entity_a_id INTEGER,
                    entity_b_id INTEGER,
                    votes INTEGER DEFAULT 1,
                    PRIMARY KEY (entity_a_id, entity_b_id),
                    FOREIGN KEY(entity_a_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_b_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ghost_merge_candidates (
                    target_id INTEGER PRIMARY KEY,
                    votes INTEGER DEFAULT 1,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_pov (
                    chapter INTEGER PRIMARY KEY,
                    entity_id INTEGER,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cursor.execute(
                "INSERT OR REPLACE INTO schema_metadata (key, value) VALUES ('graph_schema_version', ?)",
                (str(GRAPH_SCHEMA_VERSION),)
            )
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    rel_key TEXT PRIMARY KEY,
                    source_id INTEGER,
                    target_id INTEGER,
                    current_trust_score REAL,
                    last_event_id INTEGER,
                    last_updated_chapter INTEGER,
                    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(last_event_id) REFERENCES events(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    event_order INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    normalized_summary TEXT NOT NULL,
                    event_type TEXT DEFAULT 'plot',
                    confidence REAL DEFAULT 0.7,
                    source_payload TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter, normalized_summary)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_key TEXT UNIQUE NOT NULL,
                    representative_summary TEXT NOT NULL,
                    confidence REAL DEFAULT 0.7,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_cluster_members (
                    cluster_id INTEGER,
                    event_id INTEGER,
                    confidence REAL DEFAULT 0.7,
                    PRIMARY KEY(cluster_id, event_id),
                    FOREIGN KEY(cluster_id) REFERENCES event_clusters(id) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_participants (
                    event_id INTEGER,
                    entity_id INTEGER,
                    role TEXT DEFAULT 'participant',
                    confidence REAL DEFAULT 0.7,
                    PRIMARY KEY(event_id, entity_id, role),
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_consequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER,
                    consequence_type TEXT DEFAULT 'relationship_change',
                    target_entity_id INTEGER,
                    rel_key TEXT,
                    description TEXT,
                    trust_delta INTEGER,
                    confidence REAL DEFAULT 0.7,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_causal_edges (
                    parent_event_id INTEGER,
                    child_event_id INTEGER,
                    relation_type TEXT DEFAULT 'causes',
                    confidence REAL DEFAULT 0.5,
                    PRIMARY KEY(parent_event_id, child_event_id, relation_type),
                    FOREIGN KEY(parent_event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY(child_event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rel_key TEXT,
                    chapter INTEGER,
                    interaction_order INTEGER,
                    interaction_type TEXT DEFAULT 'interaction',
                    trust_score INTEGER,
                    reason TEXT,
                    evidence TEXT,
                    confidence REAL DEFAULT 0.7,
                    event_id INTEGER,
                    consequence_id INTEGER,
                    FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL,
                    FOREIGN KEY(consequence_id) REFERENCES event_consequences(id) ON DELETE SET NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conflict_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conflict_type TEXT NOT NULL,
                    entity_a_id INTEGER,
                    entity_b_id INTEGER,
                    chapter INTEGER,
                    payload TEXT,
                    status TEXT DEFAULT 'open',
                    reviewed_at TEXT,
                    resolution TEXT,
                    resolved_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entity_a_id) REFERENCES entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(entity_b_id) REFERENCES entities(id) ON DELETE SET NULL
                )
            """)
            self._migrate_table_columns(conn)
            self._migrate_relationship_history_schema(conn)
            conn.commit()

    def _add_column_if_missing(self, conn, table_name: str, column_name: str, definition: str):
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _migrate_table_columns(self, conn):
        self._add_column_if_missing(conn, "entities", "confidence", "REAL DEFAULT 0.55")
        self._add_column_if_missing(conn, "entities", "type_support_count", "INTEGER DEFAULT 1")
        self._add_column_if_missing(conn, "entities", "importance_score", "REAL DEFAULT 0.45")
        self._add_column_if_missing(conn, "entities", "visibility_score", "REAL DEFAULT 0.45")
        self._add_column_if_missing(conn, "entities", "surface_form_class", "TEXT DEFAULT 'proper_name'")
        self._add_column_if_missing(conn, "entities", "location_subtype", "TEXT")
        self._add_column_if_missing(conn, "aliases", "alias_key", "TEXT")
        self._add_column_if_missing(conn, "aliases", "confidence", "REAL DEFAULT 0.85")
        self._add_column_if_missing(conn, "aliases", "support_count", "INTEGER DEFAULT 4")
        self._add_column_if_missing(conn, "aliases", "first_seen", "INTEGER")
        self._add_column_if_missing(conn, "aliases", "last_seen", "INTEGER")
        self._add_column_if_missing(conn, "aliases", "status", "TEXT DEFAULT 'accepted'")
        self._add_column_if_missing(conn, "aliases", "validation_status", "TEXT")
        self._add_column_if_missing(conn, "aliases", "validation_reason", "TEXT")
        self._add_column_if_missing(conn, "relationships", "current_trust_score", "REAL")
        self._add_column_if_missing(conn, "relationships", "last_event_id", "INTEGER")
        self._add_column_if_missing(conn, "relationships", "last_updated_chapter", "INTEGER")
        self._add_column_if_missing(conn, "relationship_history", "evidence", "TEXT")
        self._add_column_if_missing(conn, "relationship_history", "confidence", "REAL DEFAULT 0.7")
        self._add_column_if_missing(conn, "relationship_history", "event_id", "INTEGER")
        self._add_column_if_missing(conn, "relationship_history", "consequence_id", "INTEGER")
        self._add_column_if_missing(conn, "conflict_records", "reviewed_at", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "resolution", "TEXT")
        self._add_column_if_missing(conn, "conflict_records", "resolved_at", "TEXT")
        conn.execute("UPDATE aliases SET first_seen = COALESCE(first_seen, chapter_found)")
        conn.execute("UPDATE aliases SET last_seen = COALESCE(last_seen, chapter_found)")
        conn.execute("UPDATE aliases SET status = COALESCE(status, 'accepted')")
        conn.execute("UPDATE aliases SET confidence = COALESCE(confidence, 0.85)")
        conn.execute("UPDATE aliases SET support_count = COALESCE(support_count, 4)")
        conn.execute("UPDATE relationship_history SET evidence = COALESCE(evidence, reason)")

        cursor = conn.cursor()
        cursor.execute("SELECT id, alias_name FROM aliases WHERE alias_key IS NULL OR alias_key = ''")
        for alias_id, alias_name in cursor.fetchall():
            conn.execute(
                "UPDATE aliases SET alias_key = ? WHERE id = ?",
                (self.normalize_alias_key(alias_name) or f"__alias_{alias_id}", alias_id),
            )
        conn.execute("""
            UPDATE aliases
            SET alias_key = '__alias_' || id
            WHERE alias_key IS NULL OR alias_key = ''
        """)

        cursor.execute("""
            SELECT entity_id, alias_key, MIN(id), SUM(support_count), MAX(confidence),
                   MAX(last_seen), GROUP_CONCAT(evidence, '\n')
            FROM aliases
            WHERE alias_key IS NOT NULL AND alias_key != ''
            GROUP BY entity_id, alias_key
            HAVING COUNT(*) > 1
        """)
        for entity_id, alias_key, keep_id, support_count, confidence, last_seen, evidence in cursor.fetchall():
            conn.execute("""
                UPDATE aliases
                SET support_count = ?, confidence = ?, last_seen = ?, evidence = ?
                WHERE id = ?
            """, (support_count, confidence, last_seen, evidence, keep_id))
            conn.execute("""
                DELETE FROM aliases
                WHERE entity_id = ? AND alias_key = ? AND id != ?
            """, (entity_id, alias_key, keep_id))

        cursor.execute("""
            SELECT id, canonical_name, entity_type
            FROM entities
            WHERE importance_score IS NULL
               OR visibility_score IS NULL
               OR surface_form_class IS NULL
               OR (entity_type = 'LOCATION' AND location_subtype IS NULL)
        """)
        for entity_id, canonical_name, entity_type in cursor.fetchall():
            importance, visibility, surface_class, location_subtype = self._initial_importance(canonical_name, entity_type)
            conn.execute("""
                UPDATE entities
                SET importance_score = COALESCE(importance_score, ?),
                    visibility_score = COALESCE(visibility_score, ?),
                    surface_form_class = COALESCE(surface_form_class, ?),
                    location_subtype = COALESCE(location_subtype, ?)
                WHERE id = ?
            """, (importance, visibility, surface_class, location_subtype, entity_id))

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_aliases_entity_alias_key
            ON aliases(entity_id, alias_key)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_chapter ON events(chapter, event_order)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_participants_entity ON event_participants(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationship_history_event ON relationship_history(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_normalized ON mention_occurrences(normalized_form, chapter)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_title_links_key ON title_links(title_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_identity_promotions_resolved ON identity_promotions(resolved_entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_cluster_members_event ON event_cluster_members(event_id)")

    def _migrate_relationship_history_schema(self, conn):
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(relationship_history)")
        columns = {row[1] for row in cursor.fetchall()}

        needs_migration = (
            "interaction_order" not in columns
            or "interaction_type" not in columns
            or "event_id" not in columns
            or "consequence_id" not in columns
        )
        cursor.execute("PRAGMA index_list(relationship_history)")
        for _, index_name, is_unique, *_ in cursor.fetchall():
            if not is_unique:
                continue
            cursor.execute(f"PRAGMA index_info('{index_name}')")
            indexed_columns = {row[2] for row in cursor.fetchall()}
            if {"rel_key", "chapter"}.issubset(indexed_columns):
                needs_migration = True
                break

        if not needs_migration:
            return

        cursor.execute("""
            CREATE TABLE relationship_history_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rel_key TEXT,
                chapter INTEGER,
                interaction_order INTEGER,
                interaction_type TEXT DEFAULT 'interaction',
                trust_score INTEGER,
                reason TEXT,
                evidence TEXT,
                confidence REAL DEFAULT 0.7,
                event_id INTEGER,
                consequence_id INTEGER,
                FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL,
                FOREIGN KEY(consequence_id) REFERENCES event_consequences(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            SELECT rel_key, chapter, trust_score, reason, evidence, confidence, event_id, consequence_id
            FROM relationship_history
            ORDER BY id
        """)
        interaction_counts = {}
        for rel_key, chapter, trust_score, reason, evidence, confidence, event_id, consequence_id in cursor.fetchall():
            count_key = (rel_key, chapter)
            interaction_counts[count_key] = interaction_counts.get(count_key, 0) + 1
            cursor.execute("""
                INSERT INTO relationship_history_new (
                    rel_key, chapter, interaction_order, interaction_type,
                    trust_score, reason, evidence, confidence, event_id, consequence_id
                )
                VALUES (?, ?, ?, 'interaction', ?, ?, ?, ?, ?, ?)
            """, (
                rel_key,
                chapter,
                interaction_counts[count_key],
                trust_score,
                reason,
                evidence or reason,
                confidence if confidence is not None else 0.7,
                event_id,
                consequence_id,
            ))

        cursor.execute("DROP TABLE relationship_history")
        cursor.execute("ALTER TABLE relationship_history_new RENAME TO relationship_history")

    def get_pov_for_chapter(self, chapter: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entity_id FROM chapter_pov WHERE chapter <= ? ORDER BY chapter DESC LIMIT 1", (chapter,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_pov_for_chapter(self, chapter: int, entity_id: int):
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO chapter_pov (chapter, entity_id) VALUES (?, ?)", (chapter, entity_id))

    def record_conflict(
        self,
        conflict_type: str,
        chapter: int,
        payload: dict,
        entity_a_id: int | None = None,
        entity_b_id: int | None = None,
    ):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO conflict_records (
                    conflict_type, entity_a_id, entity_b_id, chapter, payload
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                conflict_type,
                entity_a_id,
                entity_b_id,
                chapter,
                json.dumps(payload, ensure_ascii=False),
            ))

    def resolve_conflict(self, conflict_id: int, status: str, resolution: str = ""):
        if status not in {"reviewed", "resolved", "rejected"}:
            raise ValueError("status must be reviewed, resolved, or rejected")
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE conflict_records
                SET status = ?,
                    reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                    resolution = ?,
                    resolved_at = CASE
                        WHEN ? IN ('resolved', 'rejected') THEN CURRENT_TIMESTAMP
                        ELSE resolved_at
                    END
                WHERE id = ?
            """, (status, resolution, status, conflict_id))

    def apply_confidence_decay(self, current_chapter: int):
        cutoff = max(0, current_chapter - CONFIDENCE_DECAY_AFTER_CHAPTERS)
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE aliases
                SET confidence = confidence * ?
                WHERE status IN ('candidate', 'probable', 'review') AND COALESCE(last_seen, chapter_found, 0) < ?
            """, (CONFIDENCE_DECAY_FACTOR, cutoff))
            conn.execute("""
                UPDATE aliases
                SET status = 'review'
                WHERE status IN ('candidate', 'probable') AND confidence < ?
            """, (ALIAS_REVIEW_CONFIDENCE,))
            conn.execute("""
                UPDATE aliases
                SET status = 'expired'
                WHERE status = 'review' AND confidence < ?
            """, (ALIAS_EXPIRED_CONFIDENCE,))
            conn.execute("""
                UPDATE entities
                SET confidence = confidence * ?
                WHERE confidence < ? AND COALESCE(last_verified_chapter, first_seen_chapter, 0) < ?
            """, (CONFIDENCE_DECAY_FACTOR, ENTITY_REVIEW_CONFIDENCE, cutoff))

    def get_resolution_matrices(self, entity_type: str):
        alias_to_id = {}
        id_to_canon = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, a.alias_name, a.alias_key
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                    AND a.status IN ('accepted', 'probable')
                WHERE e.entity_type = ?
            """, (entity_type,))
            
            for eid, canon, alias, alias_key in cursor.fetchall():
                id_to_canon[eid] = canon
                alias_to_id[self.normalize_alias_key(canon)] = eid
                if alias:
                    alias_to_id[alias_key or self.normalize_alias_key(alias)] = eid
            cursor.execute("""
                SELECT e.id, e.canonical_name, t.title_text, t.title_key
                FROM entities e
                JOIN title_links t ON e.id = t.entity_id
                WHERE e.entity_type = ?
                  AND t.status IN ('accepted', 'probable')
            """, (entity_type,))
            for eid, canon, title, title_key in cursor.fetchall():
                id_to_canon[eid] = canon
                alias_to_id[title_key or self.normalize_alias_key(title)] = eid
        return alias_to_id, id_to_canon

    def get_known_entities_text(self, entity_type: str, chapter_text_lower: str) -> str:
        active = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, GROUP_CONCAT(a.alias_name || ':' || a.status, '|') 
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                    AND a.status IN ('accepted', 'probable')
                WHERE e.entity_type = ?
                GROUP BY e.id, e.canonical_name
                ORDER BY e.visibility_score DESC, e.last_verified_chapter DESC, e.mention_count DESC
                LIMIT ?
            """, (entity_type, self.ACTIVE_ENTITY_LIMIT))
            
            for row in cursor.fetchall():
                entity_id = row[0]
                canon = row[1]
                aliases_raw = row[2].split('|') if row[2] else []
                aliases = [a for a in aliases_raw if a]
                alias_terms = [a.rsplit(":", 1)[0] for a in aliases]
                cursor.execute("""
                    SELECT title_text || ':' || status
                    FROM title_links
                    WHERE entity_id = ?
                      AND status IN ('accepted', 'probable')
                    ORDER BY confidence DESC, support_count DESC
                    LIMIT 4
                """, (entity_id,))
                titles = [title for (title,) in cursor.fetchall()]
                title_terms = [title.rsplit(":", 1)[0] for title in titles]
                
                search_terms = tuple([canon] + alias_terms + title_terms)
                
                if search_terms not in self._regex_cache:
                    pattern = r'\b(?:' + '|'.join(map(re.escape, [t.lower() for t in search_terms])) + r')\b'
                    self._regex_cache[search_terms] = re.compile(pattern)
                else:
                    self._regex_cache.move_to_end(search_terms)

                if len(self._regex_cache) > REGEX_CACHE_SIZE:
                    self._regex_cache.popitem(last=False)
                    
                if self._regex_cache[search_terms].search(chapter_text_lower):
                    active[canon] = aliases + titles
                    
        if not active:
            return f"No known {entity_type.lower()}s detected in this chapter's text yet."
            
        return "\n".join([f"- {c} (aliases/status: {', '.join(a)})" if a else f"- {c}" for c, a in active.items()])

    def add_entity(self, canonical_name: str, entity_type: str, chapter_idx: int) -> int:
        importance, visibility, surface_class, location_subtype = self._initial_importance(canonical_name, entity_type)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO entities (
                    canonical_name, entity_type, first_seen_chapter, last_verified_chapter,
                    mention_count, confidence, type_support_count,
                    importance_score, visibility_score, surface_form_class, location_subtype
                )
                VALUES (?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?)
            """, (
                canonical_name,
                entity_type,
                chapter_idx,
                chapter_idx,
                ENTITY_BASE_CONFIDENCE,
                importance,
                visibility,
                surface_class,
                location_subtype,
            ))
            inserted = cursor.rowcount == 1
            if inserted:
                cursor.execute("SELECT id FROM entities WHERE canonical_name = ?", (canonical_name,))
                entity_id = cursor.fetchone()[0]
                cursor.execute("""
                    INSERT OR IGNORE INTO entity_type_votes (
                        entity_id, entity_type, support_count, confidence, first_seen, last_seen
                    )
                    VALUES (?, ?, 1, ?, ?, ?)
                """, (entity_id, entity_type, ENTITY_BASE_CONFIDENCE, chapter_idx, chapter_idx))
                return entity_id

            cursor.execute("SELECT id FROM entities WHERE canonical_name = ?", (canonical_name,))
            entity_id = cursor.fetchone()[0]
            self.register_entity_type_vote(entity_id, entity_type, chapter_idx)
            return entity_id

    def update_entity_verification(self, entity_id: int, chapter_idx: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE entities
                SET last_verified_chapter = ?,
                    mention_count = mention_count + 1,
                    confidence = MIN(1.0, confidence + ?),
                    importance_score = MIN(1.0, importance_score + 0.03),
                    visibility_score = MIN(1.0, visibility_score + 0.03)
                WHERE id = ?
            """, (chapter_idx, ENTITY_SUPPORT_CONFIDENCE_BOOST, entity_id))

    def register_entity_type_vote(self, entity_id: int, entity_type: str, chapter_idx: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entity_type FROM entities WHERE id = ?", (entity_id,))
            current = cursor.fetchone()
            if current and current[0] != entity_type:
                self.record_conflict(
                    "entity_type_collision",
                    chapter_idx,
                    {"current_type": current[0], "proposed_type": entity_type},
                    entity_a_id=entity_id,
                )
            cursor.execute("""
                INSERT INTO entity_type_votes (
                    entity_id, entity_type, support_count, confidence, first_seen, last_seen
                )
                VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(entity_id, entity_type) DO UPDATE SET
                    support_count = support_count + 1,
                    confidence = MIN(1.0, confidence + ?),
                    last_seen = excluded.last_seen
            """, (
                entity_id,
                entity_type,
                ENTITY_BASE_CONFIDENCE,
                chapter_idx,
                chapter_idx,
                ENTITY_SUPPORT_CONFIDENCE_BOOST,
            ))

            cursor.execute("""
                SELECT entity_type, support_count, confidence
                FROM entity_type_votes
                WHERE entity_id = ?
                ORDER BY support_count DESC, confidence DESC
                LIMIT 1
            """, (entity_id,))
            best_type, support_count, confidence = cursor.fetchone()
            if support_count >= ENTITY_TYPE_CHANGE_SUPPORT and confidence >= ENTITY_TYPE_CHANGE_CONFIDENCE:
                conn.execute("""
                    UPDATE entities
                    SET entity_type = ?, type_support_count = ?, confidence = MAX(confidence, ?)
                    WHERE id = ?
                """, (best_type, support_count, confidence, entity_id))

    def add_mention_occurrence(
        self,
        surface_form: str,
        chapter_idx: int,
        sentence_offset: int | None = None,
        paragraph_offset: int | None = None,
        speaker: str | None = None,
        entity_type_guess: str | None = None,
        confidence: float = 0.5,
        source_quote: str = "",
        linked_entity_id: int | None = None,
    ) -> int | None:
        surface_form = " ".join(str(surface_form or "").split())
        normalized_form = self.normalize_alias_key(surface_form)
        if not surface_form or not normalized_form:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mention_occurrences (
                    surface_form, normalized_form, chapter, sentence_offset,
                    paragraph_offset, speaker, entity_type_guess, confidence,
                    source_quote, linked_entity_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                surface_form,
                normalized_form,
                chapter_idx,
                sentence_offset,
                paragraph_offset,
                speaker,
                entity_type_guess,
                confidence,
                source_quote,
                linked_entity_id,
            ))
            return cursor.lastrowid

    def add_title_link(
        self,
        entity_id: int,
        title_text: str,
        chapter_idx: int,
        evidence: str,
        confidence: float = 0.55,
        status: str = "candidate",
    ) -> str:
        title_text = " ".join(str(title_text or "").split())
        title_key = self.normalize_alias_key(title_text)
        if not title_key:
            return "rejected"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO title_links (
                    entity_id, title_text, title_key, chapter_found, evidence,
                    confidence, support_count, first_seen, last_seen, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(entity_id, title_key) DO UPDATE SET
                    title_text = excluded.title_text,
                    evidence = excluded.evidence,
                    confidence = MIN(1.0, title_links.confidence + ?),
                    support_count = title_links.support_count + 1,
                    last_seen = excluded.last_seen
            """, (
                entity_id,
                title_text,
                title_key,
                chapter_idx,
                evidence,
                confidence,
                chapter_idx,
                chapter_idx,
                status,
                ALIAS_SUPPORT_CONFIDENCE_BOOST,
            ))
            cursor.execute(
                "SELECT support_count, confidence FROM title_links WHERE entity_id = ? AND title_key = ?",
                (entity_id, title_key),
            )
            support_count, title_confidence = cursor.fetchone()
            if support_count >= ALIAS_ACCEPTED_SUPPORT:
                next_status = "accepted"
            elif support_count >= 2 or title_confidence >= ALIAS_ACCEPTED_CONFIDENCE:
                next_status = "probable"
            else:
                next_status = status
            conn.execute(
                "UPDATE title_links SET status = ? WHERE entity_id = ? AND title_key = ?",
                (next_status, entity_id, title_key),
            )
            return next_status

    def record_identity_promotion(
        self,
        placeholder_entity_id: int | None,
        resolved_entity_id: int,
        chapter_idx: int,
        evidence: str,
        confidence: float = 0.75,
        status: str = "candidate",
    ) -> int | None:
        if not resolved_entity_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO identity_promotions (
                    placeholder_entity_id, resolved_entity_id, chapter, evidence,
                    confidence, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(placeholder_entity_id, resolved_entity_id) DO UPDATE SET
                    chapter = excluded.chapter,
                    evidence = excluded.evidence,
                    confidence = MAX(identity_promotions.confidence, excluded.confidence),
                    status = excluded.status
            """, (
                placeholder_entity_id,
                resolved_entity_id,
                chapter_idx,
                evidence,
                confidence,
                status,
            ))
            cursor.execute("""
                SELECT id
                FROM identity_promotions
                WHERE placeholder_entity_id IS ? AND resolved_entity_id = ?
            """, (placeholder_entity_id, resolved_entity_id))
            row = cursor.fetchone()
            return row[0] if row else None

    def add_event_cluster_member(self, event_id: int, summary: str, confidence: float = RELATIONSHIP_BASE_CONFIDENCE):
        cluster_key = self.normalize_alias_key(summary)
        if not event_id or not cluster_key:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_clusters (cluster_key, representative_summary, confidence)
                VALUES (?, ?, ?)
                ON CONFLICT(cluster_key) DO UPDATE SET
                    confidence = MAX(event_clusters.confidence, excluded.confidence)
            """, (cluster_key, summary, confidence))
            cursor.execute("SELECT id FROM event_clusters WHERE cluster_key = ?", (cluster_key,))
            cluster_id = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO event_cluster_members (cluster_id, event_id, confidence)
                VALUES (?, ?, ?)
                ON CONFLICT(cluster_id, event_id) DO UPDATE SET
                    confidence = MAX(event_cluster_members.confidence, excluded.confidence)
            """, (cluster_id, event_id, confidence))
            return cluster_id

    def add_alias(
        self,
        entity_id: int,
        alias_name: str,
        chapter_idx: int,
        evidence: str,
        confidence: float | None = None,
        validation_status: str | None = None,
        validation_reason: str | None = None,
        initial_status: str = "candidate",
    ):
        confidence = ALIAS_BASE_CONFIDENCE if confidence is None else confidence
        alias_key = self.normalize_alias_key(alias_name)
        if not alias_key:
            return "rejected"
        if initial_status not in {"candidate", "probable", "accepted", "review", "rejected"}:
            initial_status = "candidate"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO aliases (
                    alias_name, alias_key, entity_id, chapter_found, evidence, confidence,
                    support_count, first_seen, last_seen, status, validation_status,
                    validation_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id, alias_key) DO UPDATE SET
                    alias_name = CASE
                        WHEN LENGTH(excluded.alias_name) > LENGTH(aliases.alias_name)
                        THEN excluded.alias_name
                        ELSE aliases.alias_name
                    END,
                    evidence = excluded.evidence,
                    confidence = MIN(1.0, aliases.confidence + ?),
                    support_count = aliases.support_count + 1,
                    last_seen = excluded.last_seen,
                    validation_status = excluded.validation_status,
                    validation_reason = excluded.validation_reason
            """, (
                alias_name,
                alias_key,
                entity_id,
                chapter_idx,
                evidence,
                confidence,
                chapter_idx,
                chapter_idx,
                initial_status,
                validation_status,
                validation_reason,
                ALIAS_SUPPORT_CONFIDENCE_BOOST,
            ))

            cursor.execute("""
                SELECT support_count, confidence
                FROM aliases
                WHERE entity_id = ? AND alias_key = ?
            """, (entity_id, alias_key))
            support_count, alias_confidence = cursor.fetchone()
            if initial_status in {"review", "rejected"}:
                status = initial_status
            elif support_count >= ALIAS_ACCEPTED_SUPPORT:
                status = "accepted"
            elif support_count >= 2 or alias_confidence >= ALIAS_ACCEPTED_CONFIDENCE:
                status = "probable"
            else:
                status = "candidate"

            conn.execute("""
                UPDATE aliases
                SET status = ?
                WHERE entity_id = ? AND alias_key = ?
            """, (status, entity_id, alias_key))
            return status

    def add_event(
        self,
        chapter: int,
        summary: str,
        event_order: int,
        event_type: str = "plot",
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        source_payload: dict | None = None,
    ) -> int | None:
        summary = " ".join(str(summary or "").strip().split())
        if not summary:
            return None
        normalized_summary = self.normalize_alias_key(summary)
        if not normalized_summary:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (
                    chapter, event_order, summary, normalized_summary,
                    event_type, confidence, source_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter, normalized_summary) DO UPDATE SET
                    summary = excluded.summary,
                    confidence = MAX(events.confidence, excluded.confidence),
                    source_payload = COALESCE(excluded.source_payload, events.source_payload)
            """, (
                chapter,
                event_order,
                summary,
                normalized_summary,
                event_type,
                confidence,
                json.dumps(source_payload, ensure_ascii=False) if source_payload else None,
            ))
            cursor.execute(
                "SELECT id FROM events WHERE chapter = ? AND normalized_summary = ?",
                (chapter, normalized_summary),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def add_event_participant(
        self,
        event_id: int | None,
        entity_id: int | None,
        role: str = "participant",
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
    ):
        if not event_id or not entity_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO event_participants (event_id, entity_id, role, confidence)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(event_id, entity_id, role) DO UPDATE SET
                    confidence = MAX(event_participants.confidence, excluded.confidence)
            """, (event_id, entity_id, role, confidence))

    def add_event_causal_edge(
        self,
        parent_event_id: int | None,
        child_event_id: int | None,
        relation_type: str = "precedes",
        confidence: float = 0.5,
    ):
        if not parent_event_id or not child_event_id or parent_event_id == child_event_id:
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO event_causal_edges (
                    parent_event_id, child_event_id, relation_type, confidence
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(parent_event_id, child_event_id, relation_type) DO UPDATE SET
                    confidence = MAX(event_causal_edges.confidence, excluded.confidence)
            """, (parent_event_id, child_event_id, relation_type, confidence))

    def add_event_consequence(
        self,
        event_id: int | None,
        rel_key: str | None,
        description: str,
        trust_delta: int | None = None,
        target_entity_id: int | None = None,
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        consequence_type: str = "relationship_change",
    ) -> int | None:
        if not event_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_consequences (
                    event_id, consequence_type, target_entity_id, rel_key,
                    description, trust_delta, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                consequence_type,
                target_entity_id,
                rel_key,
                description,
                trust_delta,
                confidence,
            ))
            return cursor.lastrowid

    def _recalculate_relationship_snapshot(self, conn, rel_key: str):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT trust_score, COALESCE(confidence, ?), chapter, event_id
            FROM relationship_history
            WHERE rel_key = ? AND trust_score IS NOT NULL
            ORDER BY chapter, interaction_order, id
        """, (RELATIONSHIP_BASE_CONFIDENCE, rel_key))
        rows = cursor.fetchall()
        if not rows:
            return
        weighted_total = sum(trust * max(confidence, 0.05) for trust, confidence, _chapter, _event_id in rows)
        weight = sum(max(confidence, 0.05) for _trust, confidence, _chapter, _event_id in rows)
        current_score = round(weighted_total / weight, 3) if weight else rows[-1][0]
        last_chapter = rows[-1][2]
        last_event_id = rows[-1][3]
        conn.execute("""
            UPDATE relationships
            SET current_trust_score = ?,
                last_updated_chapter = ?,
                last_event_id = COALESCE(?, last_event_id)
            WHERE rel_key = ?
        """, (current_score, last_chapter, last_event_id, rel_key))

    def add_relationship_event(
        self,
        source_id: int,
        target_id: int,
        chapter: int,
        trust: int,
        evidence: str,
        interaction_type: str = "interaction",
        confidence: float = RELATIONSHIP_BASE_CONFIDENCE,
        event_id: int | None = None,
        consequence_description: str | None = None,
    ):
        rel_key = f"{min(source_id, target_id)}::{max(source_id, target_id)}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conn.execute("INSERT OR IGNORE INTO relationships (rel_key, source_id, target_id) VALUES (?, ?, ?)", 
                         (rel_key, source_id, target_id))

            cursor.execute("""
                SELECT COALESCE(MAX(interaction_order), 0) + 1
                FROM relationship_history
                WHERE rel_key = ? AND chapter = ?
            """, (rel_key, chapter))
            interaction_order = cursor.fetchone()[0]

            cursor.execute("""
                SELECT trust_score, evidence, chapter
                FROM relationship_history
                WHERE rel_key = ?
                ORDER BY chapter DESC, interaction_order DESC
                LIMIT 1
            """, (rel_key,))
            previous = cursor.fetchone()
            previous_trust = None
            if previous:
                previous_trust, previous_evidence, previous_chapter = previous
                if (
                    previous_trust is not None
                    and trust is not None
                    and previous_trust * trust < 0
                    and abs(previous_trust - trust) >= RELATIONSHIP_CONTRADICTION_DELTA
                ):
                    self.record_conflict(
                        "relationship_contradiction",
                        chapter,
                        {
                            "rel_key": rel_key,
                            "previous_chapter": previous_chapter,
                            "previous_trust": previous_trust,
                            "previous_evidence": previous_evidence,
                            "new_trust": trust,
                            "new_evidence": evidence,
                        },
                        source_id,
                        target_id,
                    )

            trust_delta = trust - previous_trust if previous_trust is not None and trust is not None else trust
            consequence_id = self.add_event_consequence(
                event_id,
                rel_key,
                consequence_description or evidence,
                trust_delta=trust_delta,
                confidence=confidence,
            )

            conn.execute("""
                INSERT INTO relationship_history (
                    rel_key, chapter, interaction_order, interaction_type,
                    trust_score, reason, evidence, confidence, event_id, consequence_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rel_key,
                chapter,
                interaction_order,
                interaction_type,
                trust,
                evidence,
                evidence,
                confidence,
                event_id,
                consequence_id,
            ))
            self._recalculate_relationship_snapshot(conn, rel_key)

    def get_memory_cards_text(self, chapter_text_lower: str, limit: int = MEMORY_CARD_LIMIT) -> str:
        matched_entities = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, e.entity_type, e.first_seen_chapter,
                       e.last_verified_chapter, e.mention_count, e.importance_score,
                       e.visibility_score, e.surface_form_class, e.location_subtype,
                       GROUP_CONCAT(a.alias_name || ':' || a.status, '|')
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                    AND a.status IN ('accepted', 'probable')
                GROUP BY e.id, e.canonical_name, e.entity_type,
                         e.first_seen_chapter, e.last_verified_chapter, e.mention_count,
                         e.importance_score, e.visibility_score, e.surface_form_class, e.location_subtype
                ORDER BY e.visibility_score DESC, e.importance_score DESC,
                         e.last_verified_chapter DESC, e.mention_count DESC
            """)

            for row in cursor.fetchall():
                (
                    entity_id,
                    canon,
                    entity_type,
                    first_seen,
                    last_seen,
                    mention_count,
                    importance,
                    visibility,
                    surface_class,
                    location_subtype,
                    aliases_raw,
                ) = row
                aliases = [a for a in aliases_raw.split("|") if a] if aliases_raw else []
                alias_terms = [a.rsplit(":", 1)[0] for a in aliases]
                search_terms = [canon] + alias_terms
                if any(re.search(rf"\b{re.escape(term.lower())}\b", chapter_text_lower) for term in search_terms):
                    matched_entities.append((
                        entity_id,
                        canon,
                        entity_type,
                        first_seen,
                        last_seen,
                        mention_count,
                        aliases,
                        importance,
                        visibility,
                        surface_class,
                        location_subtype,
                    ))
                    if len(matched_entities) >= limit:
                        break

            cards = []
            for (
                entity_id,
                canon,
                entity_type,
                first_seen,
                last_seen,
                _mention_count,
                aliases,
                importance,
                visibility,
                surface_class,
                location_subtype,
            ) in matched_entities:
                cursor.execute("""
                    SELECT CASE WHEN r.source_id = ? THEN et.canonical_name ELSE es.canonical_name END AS other_name,
                           COALESCE(r.current_trust_score, rh.trust_score) AS trust_score,
                           rh.evidence,
                           rh.chapter,
                           ev.summary
                    FROM relationship_history rh
                    JOIN relationships r ON rh.rel_key = r.rel_key
                    JOIN entities es ON r.source_id = es.id
                    JOIN entities et ON r.target_id = et.id
                    LEFT JOIN events ev ON rh.event_id = ev.id
                    WHERE r.source_id = ? OR r.target_id = ?
                    ORDER BY rh.chapter DESC, rh.interaction_order DESC
                    LIMIT ?
                """, (entity_id, entity_id, entity_id, MEMORY_CARD_RELATIONSHIP_LIMIT))
                relationships = cursor.fetchall()

                cursor.execute("""
                    SELECT ev.chapter, ev.summary
                    FROM event_participants ep
                    JOIN events ev ON ep.event_id = ev.id
                    WHERE ep.entity_id = ?
                    ORDER BY ev.chapter DESC, ev.event_order DESC
                    LIMIT ?
                """, (entity_id, MEMORY_CARD_RECENT_EVENT_LIMIT))
                recent_events = cursor.fetchall()

                cursor.execute("""
                    SELECT title_text, status
                    FROM title_links
                    WHERE entity_id = ?
                      AND status IN ('accepted', 'probable', 'candidate')
                    ORDER BY confidence DESC, support_count DESC, last_seen DESC
                    LIMIT 5
                """, (entity_id,))
                title_links = cursor.fetchall()

                parts = [
                    f"- {canon}",
                    f"  type: {entity_type}",
                    f"  importance: {importance:.2f}",
                    f"  visibility: {visibility:.2f}",
                    f"  surface_form: {surface_class}",
                    f"  first_seen: {first_seen}",
                    f"  last_seen: {last_seen}",
                ]
                if location_subtype:
                    parts.append(f"  location_subtype: {location_subtype}")
                if aliases:
                    parts.append(f"  aliases/status: {', '.join(aliases[:5])}")
                if title_links:
                    parts.append(
                        "  titles/status: "
                        + ", ".join(f"{title}:{status}" for title, status in title_links)
                    )
                if relationships:
                    rel_text = "; ".join(
                        f"{other}: trust {trust} (ch {chapter}, event: {event_summary or 'unlinked'})"
                        for other, trust, _evidence, chapter, event_summary in relationships
                    )
                    parts.append(f"  relationship_snapshot: {rel_text}")
                if recent_events:
                    event_text = "; ".join(
                        f"ch {chapter}: {summary[:120]}"
                        for chapter, summary in recent_events
                        if summary
                    )
                    if event_text:
                        parts.append(f"  recent_events: {event_text}")
                cards.append("\n".join(parts))

        if not cards:
            return "No relevant accepted/probable memory cards found for this chapter."

        return "\n\n".join(cards)

    def get_relevant_events_text(self, chapter_text_lower: str, limit: int = EVENT_CONTEXT_LIMIT) -> str:
        rows = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ev.chapter, ev.summary, GROUP_CONCAT(e.canonical_name, ', ')
                FROM events ev
                LEFT JOIN event_participants ep ON ev.id = ep.event_id
                LEFT JOIN entities e ON ep.entity_id = e.id
                GROUP BY ev.id, ev.chapter, ev.summary, ev.event_order
                ORDER BY ev.chapter DESC, ev.event_order DESC
                LIMIT ?
            """, (limit * 3,))
            for chapter, summary, participants_raw in cursor.fetchall():
                participants = [p.strip() for p in (participants_raw or "").split(",") if p.strip()]
                terms = participants + [summary]
                if any(term and re.search(rf"\b{re.escape(term.lower())}\b", chapter_text_lower) for term in terms):
                    rows.append((chapter, summary, participants))
                if len(rows) >= limit:
                    break

        if not rows:
            return "No prior event history matched this chapter's text."

        return "\n".join(
            f"- ch {chapter}: {summary}"
            + (f" [participants: {', '.join(participants[:5])}]" if participants else "")
            for chapter, summary, participants in rows
        )

    def get_relationship_context_text(self, chapter_text_lower: str, limit: int = MEMORY_CARD_LIMIT) -> str:
        entity_ids = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, GROUP_CONCAT(a.alias_name, '|')
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id AND a.status IN ('accepted', 'probable')
                GROUP BY e.id, e.canonical_name
                ORDER BY e.visibility_score DESC, e.last_verified_chapter DESC, e.mention_count DESC
            """)
            for entity_id, canon, aliases_raw in cursor.fetchall():
                aliases = [a for a in aliases_raw.split("|") if a] if aliases_raw else []
                terms = [canon] + aliases
                if any(re.search(rf"\b{re.escape(term.lower())}\b", chapter_text_lower) for term in terms):
                    entity_ids.append(entity_id)
                if len(entity_ids) >= limit:
                    break

            if not entity_ids:
                return "No relationship context for current chapter entities."

            placeholders = ",".join("?" for _ in entity_ids)
            cursor.execute(f"""
                SELECT es.canonical_name, et.canonical_name,
                       COALESCE(r.current_trust_score, rh.trust_score),
                       rh.evidence, rh.chapter, ev.summary
                FROM relationship_history rh
                JOIN relationships r ON rh.rel_key = r.rel_key
                JOIN entities es ON r.source_id = es.id
                JOIN entities et ON r.target_id = et.id
                LEFT JOIN events ev ON rh.event_id = ev.id
                WHERE r.source_id IN ({placeholders}) OR r.target_id IN ({placeholders})
                ORDER BY rh.chapter DESC, rh.interaction_order DESC
                LIMIT ?
            """, (*entity_ids, *entity_ids, MEMORY_CARD_RELATIONSHIP_LIMIT * max(1, len(entity_ids))))
            rows = cursor.fetchall()

        if not rows:
            return "No relationship history for current chapter entities."

        return "\n".join(
            f"- {source} / {target}: trust {trust}, ch {chapter}, event: {event_summary or 'unlinked'}, evidence: {evidence}"
            for source, target, trust, evidence, chapter, event_summary in rows
            if evidence
        )

    def export_graph_state(self) -> dict:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            export = {}
            for table in (
                "entities",
                "aliases",
                "mention_occurrences",
                "title_links",
                "identity_promotions",
                "entity_type_votes",
                "relationships",
                "relationship_history",
                "events",
                "event_clusters",
                "event_cluster_members",
                "event_participants",
                "event_consequences",
                "event_causal_edges",
                "merge_candidates",
                "ghost_merge_candidates",
                "conflict_records",
                "schema_metadata",
            ):
                cursor.execute(f"SELECT * FROM {table}")
                export[table] = [dict(row) for row in cursor.fetchall()]
            conn.row_factory = None
            return export

    def register_merge_candidate(self, id_1: int, id_2: int) -> bool:
        entity_a_id = min(id_1, id_2)
        entity_b_id = max(id_1, id_2)
        
        if entity_a_id == entity_b_id: return False
        
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT entity_type, canonical_name FROM entities WHERE id = ?", (entity_a_id,))
            entity_a = cursor.fetchone()
            cursor.execute("SELECT entity_type, canonical_name FROM entities WHERE id = ?", (entity_b_id,))
            entity_b = cursor.fetchone()
            if entity_a and entity_b and entity_a[0] != entity_b[0]:
                self.record_conflict(
                    "merge_conflict",
                    0,
                    {
                        "entity_a_id": entity_a_id,
                        "entity_a_name": entity_a[1],
                        "entity_a_type": entity_a[0],
                        "entity_b_id": entity_b_id,
                        "entity_b_name": entity_b[1],
                        "entity_b_type": entity_b[0],
                    },
                    entity_a_id,
                    entity_b_id,
                )
                return False
            
            cursor.execute("SELECT COUNT(*) FROM aliases WHERE entity_id = ?", (entity_b_id,))
            alias_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM relationships WHERE source_id = ? OR target_id = ?", (entity_b_id, entity_b_id))
            edge_count = cursor.fetchone()[0]
            
            required_votes = min(5, 2 + ((alias_count + edge_count) // 2))

            cursor.execute("""
                INSERT INTO merge_candidates (entity_a_id, entity_b_id, votes)
                VALUES (?, ?, 1)
                ON CONFLICT(entity_a_id, entity_b_id) DO UPDATE SET votes = votes + 1
            """, (entity_a_id, entity_b_id))
            
            cursor.execute("SELECT votes FROM merge_candidates WHERE entity_a_id = ? AND entity_b_id = ?", (entity_a_id, entity_b_id))
            votes = cursor.fetchone()[0]
            
            if votes >= required_votes:
                return True
        return False

    def merge_entities(self, id_1: int, id_2: int, preferred_surviving_id: int | None = None):
        if preferred_surviving_id in {id_1, id_2}:
            surviving_id = preferred_surviving_id
            losing_id = id_2 if preferred_surviving_id == id_1 else id_1
        else:
            surviving_id = min(id_1, id_2)
            losing_id = max(id_1, id_2)
        
        if surviving_id == losing_id: return
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # P0 Fix: Metadata Absorption ensures graph weights and Top-K metrics remain accurate
            cursor.execute("SELECT mention_count, last_verified_chapter FROM entities WHERE id = ?", (losing_id,))
            losing_meta = cursor.fetchone()
            if losing_meta:
                l_count, l_verified = losing_meta
                conn.execute("""
                    UPDATE entities 
                    SET mention_count = mention_count + ?, 
                        last_verified_chapter = MAX(last_verified_chapter, ?)
                    WHERE id = ?
                """, (l_count, l_verified, surviving_id))
            
            conn.execute("""
                DELETE FROM aliases
                WHERE entity_id = ?
                  AND alias_key IN (
                      SELECT alias_key FROM aliases WHERE entity_id = ?
                  )
            """, (losing_id, surviving_id))
            conn.execute("UPDATE aliases SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("""
                DELETE FROM title_links
                WHERE entity_id = ?
                  AND title_key IN (
                      SELECT title_key FROM title_links WHERE entity_id = ?
                  )
            """, (losing_id, surviving_id))
            conn.execute("UPDATE title_links SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute(
                "UPDATE mention_occurrences SET linked_entity_id = ? WHERE linked_entity_id = ?",
                (surviving_id, losing_id),
            )
            conn.execute(
                "UPDATE identity_promotions SET resolved_entity_id = ? WHERE resolved_entity_id = ?",
                (surviving_id, losing_id),
            )
            conn.execute(
                "UPDATE identity_promotions SET placeholder_entity_id = NULL WHERE placeholder_entity_id = ?",
                (losing_id,),
            )
            conn.execute("UPDATE chapter_pov SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("""
                INSERT OR IGNORE INTO event_participants (event_id, entity_id, role, confidence)
                SELECT event_id, ?, role, confidence
                FROM event_participants
                WHERE entity_id = ?
            """, (surviving_id, losing_id))
            conn.execute("DELETE FROM event_participants WHERE entity_id = ?", (losing_id,))
            conn.execute("UPDATE event_consequences SET target_entity_id = ? WHERE target_entity_id = ?", (surviving_id, losing_id))
            
            cursor.execute("SELECT rel_key, source_id, target_id FROM relationships WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            obsolete_edges = cursor.fetchall()
            
            for old_key, src, tgt in obsolete_edges:
                new_src = surviving_id if src == losing_id else src
                new_tgt = surviving_id if tgt == losing_id else tgt
                if new_src == new_tgt: continue 
                
                new_key = f"{min(new_src, new_tgt)}::{max(new_src, new_tgt)}"
                conn.execute("INSERT OR IGNORE INTO relationships (rel_key, source_id, target_id) VALUES (?, ?, ?)", (new_key, new_src, new_tgt))
                
                cursor.execute("""
                    SELECT chapter, interaction_order, interaction_type, trust_score,
                           reason, evidence, confidence, event_id, consequence_id
                    FROM relationship_history
                    WHERE rel_key = ?
                """, (old_key,))
                obsolete_history = cursor.fetchall()
                
                for ch, order, interaction_type, trust, reason, evidence, confidence, event_id, consequence_id in obsolete_history:
                    conn.execute("""
                        INSERT INTO relationship_history (
                            rel_key, chapter, interaction_order, interaction_type,
                            trust_score, reason, evidence, confidence, event_id, consequence_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (new_key, ch, order, interaction_type, trust, reason, evidence, confidence, event_id, consequence_id))
                    conn.execute(
                        "UPDATE event_consequences SET rel_key = ? WHERE rel_key = ?",
                        (new_key, old_key),
                    )
                self._recalculate_relationship_snapshot(conn, new_key)
                
            conn.execute("DELETE FROM relationships WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            conn.execute("DELETE FROM merge_candidates WHERE entity_a_id = ? OR entity_b_id = ?", (losing_id, losing_id))
            conn.execute("DELETE FROM entities WHERE id = ?", (losing_id,))

    def register_ghost_merge(self, true_entity_id: int, required_votes: int = 2) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ghost_merge_candidates (target_id, votes)
                VALUES (?, 1)
                ON CONFLICT(target_id) DO UPDATE SET votes = votes + 1
            """, (true_entity_id,))
            
            cursor.execute("SELECT votes FROM ghost_merge_candidates WHERE target_id = ?", (true_entity_id,))
            votes = cursor.fetchone()[0]
            
            if votes >= required_votes:
                return True
        return False

    def merge_ghost_nodes(self, true_entity_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM entities WHERE canonical_name = ?", ("[UNNAMED_POV]",))
            row = cursor.fetchone()
            if row:
                self.merge_entities(true_entity_id, row[0])
                conn.execute("DELETE FROM ghost_merge_candidates")
