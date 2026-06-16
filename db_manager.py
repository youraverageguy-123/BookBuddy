import sqlite3
import os
import re
from collections import OrderedDict
from config import ACTIVE_ENTITY_LIMIT, GRAPH_SCHEMA_VERSION, REGEX_CACHE_SIZE

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
                    mention_count INTEGER DEFAULT 1
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_name TEXT,
                    entity_id INTEGER,
                    chapter_found INTEGER,
                    evidence TEXT,
                    UNIQUE(alias_name, entity_id),
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
                    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
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
                    FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE
                )
            """)
            self._migrate_relationship_history_schema(conn)
            conn.commit()

    def _migrate_relationship_history_schema(self, conn):
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(relationship_history)")
        columns = {row[1] for row in cursor.fetchall()}

        needs_migration = "interaction_order" not in columns or "interaction_type" not in columns
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
                FOREIGN KEY(rel_key) REFERENCES relationships(rel_key) ON DELETE CASCADE
            )
        """)

        cursor.execute("SELECT rel_key, chapter, trust_score, reason FROM relationship_history ORDER BY id")
        interaction_counts = {}
        for rel_key, chapter, trust_score, reason in cursor.fetchall():
            count_key = (rel_key, chapter)
            interaction_counts[count_key] = interaction_counts.get(count_key, 0) + 1
            cursor.execute("""
                INSERT INTO relationship_history_new (
                    rel_key, chapter, interaction_order, interaction_type, trust_score, reason
                )
                VALUES (?, ?, ?, 'interaction', ?, ?)
            """, (rel_key, chapter, interaction_counts[count_key], trust_score, reason))

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

    def get_resolution_matrices(self, entity_type: str):
        alias_to_id = {}
        id_to_canon = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.id, e.canonical_name, a.alias_name 
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                WHERE e.entity_type = ?
            """, (entity_type,))
            
            for eid, canon, alias in cursor.fetchall():
                id_to_canon[eid] = canon
                alias_to_id[canon.lower()] = eid
                if alias:
                    alias_to_id[alias.lower()] = eid
        return alias_to_id, id_to_canon

    def get_known_entities_text(self, entity_type: str, chapter_text_lower: str) -> str:
        active = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.canonical_name, GROUP_CONCAT(a.alias_name, '|') 
                FROM entities e
                LEFT JOIN aliases a ON e.id = a.entity_id
                WHERE e.entity_type = ?
                GROUP BY e.id, e.canonical_name
                ORDER BY e.last_verified_chapter DESC, e.mention_count DESC
                LIMIT ?
            """, (entity_type, self.ACTIVE_ENTITY_LIMIT))
            
            for row in cursor.fetchall():
                canon = row[0]
                aliases_raw = row[1].split('|') if row[1] else []
                aliases = [a for a in aliases_raw if a] 
                
                search_terms = tuple([canon] + aliases)
                
                if search_terms not in self._regex_cache:
                    pattern = r'\b(?:' + '|'.join(map(re.escape, [t.lower() for t in search_terms])) + r')\b'
                    self._regex_cache[search_terms] = re.compile(pattern)
                else:
                    self._regex_cache.move_to_end(search_terms)

                if len(self._regex_cache) > REGEX_CACHE_SIZE:
                    self._regex_cache.popitem(last=False)
                    
                if self._regex_cache[search_terms].search(chapter_text_lower):
                    active[canon] = aliases
                    
        if not active:
            return f"No known {entity_type.lower()}s detected in this chapter's text yet."
            
        return "\n".join([f"- {c} (Aliases: {', '.join(a)})" if a else f"- {c}" for c, a in active.items()])

    def add_entity(self, canonical_name: str, entity_type: str, chapter_idx: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO entities (canonical_name, entity_type, first_seen_chapter, last_verified_chapter, mention_count) 
                VALUES (?, ?, ?, ?, 1)
            """, (canonical_name, entity_type, chapter_idx, chapter_idx))
            if cursor.lastrowid:
                return cursor.lastrowid
            cursor.execute("SELECT id FROM entities WHERE canonical_name = ?", (canonical_name,))
            return cursor.fetchone()[0]

    def update_entity_verification(self, entity_id: int, chapter_idx: int):
        with self._get_connection() as conn:
            conn.execute("UPDATE entities SET last_verified_chapter = ?, mention_count = mention_count + 1 WHERE id = ?", (chapter_idx, entity_id))

    def add_alias(self, entity_id: int, alias_name: str, chapter_idx: int, evidence: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO aliases (alias_name, entity_id, chapter_found, evidence) 
                VALUES (?, ?, ?, ?)
            """, (alias_name, entity_id, chapter_idx, evidence))

    def add_relationship_event(
        self,
        source_id: int,
        target_id: int,
        chapter: int,
        trust: int,
        reason: str,
        interaction_type: str = "interaction",
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

            conn.execute("""
                INSERT INTO relationship_history (
                    rel_key, chapter, interaction_order, interaction_type, trust_score, reason
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (rel_key, chapter, interaction_order, interaction_type, trust, reason))

    def register_merge_candidate(self, id_1: int, id_2: int) -> bool:
        entity_a_id = min(id_1, id_2)
        entity_b_id = max(id_1, id_2)
        
        if entity_a_id == entity_b_id: return False
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
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

    def merge_entities(self, id_1: int, id_2: int):
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
            
            conn.execute("UPDATE aliases SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            conn.execute("UPDATE chapter_pov SET entity_id = ? WHERE entity_id = ?", (surviving_id, losing_id))
            
            cursor.execute("SELECT rel_key, source_id, target_id FROM relationships WHERE source_id = ? OR target_id = ?", (losing_id, losing_id))
            obsolete_edges = cursor.fetchall()
            
            for old_key, src, tgt in obsolete_edges:
                new_src = surviving_id if src == losing_id else src
                new_tgt = surviving_id if tgt == losing_id else tgt
                if new_src == new_tgt: continue 
                
                new_key = f"{min(new_src, new_tgt)}::{max(new_src, new_tgt)}"
                conn.execute("INSERT OR IGNORE INTO relationships (rel_key, source_id, target_id) VALUES (?, ?, ?)", (new_key, new_src, new_tgt))
                
                cursor.execute("""
                    SELECT chapter, interaction_order, interaction_type, trust_score, reason
                    FROM relationship_history
                    WHERE rel_key = ?
                """, (old_key,))
                obsolete_history = cursor.fetchall()
                
                for ch, order, interaction_type, trust, reason in obsolete_history:
                    conn.execute("""
                        INSERT INTO relationship_history (
                            rel_key, chapter, interaction_order, interaction_type, trust_score, reason
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (new_key, ch, order, interaction_type, trust, reason))
                
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
