import json
import hashlib
import sqlite3
import sys

from config import (
    CACHE_VERSION,
    GRAPH_SCHEMA_VERSION,
    IMAGE_EVIDENCE_SCHEMA_VERSION,
    NORMALIZATION_VERSION,
    PROMPT_VERSION,
)


ROLE_ONLY_CANONICALS = {
    "aunt", "brother", "captain", "child", "daughter", "doctor", "father",
    "friend", "guard", "husband", "mother", "sister", "son", "teacher",
    "uncle", "wife",
}

ACTIVE_NARRATIVE_TYPES = {"INDIVIDUAL", "GROUP", "LOCATION"}
REFERENCE_TYPES = {"CONCEPT_OR_LORE", "REFERENCE", "WORK_OF_ART"}
EVENT_PARTICIPANT_CATEGORIES = {"CHARACTER", "GROUP", "LOCATION", "OBJECT"}
LIFE_ACTUAL_STATUS_VALUES = {"alive", "dead", "missing", "unknown"}
LIFE_BELIEF_STATUS_VALUES = {"alive", "dead", "missing", "unknown"}
LIFE_APPEARANCE_STATUS_VALUES = {"possible_alive", "observed_alive", "confirmed_alive", "appears_dead", "unknown"}
LIFE_PARTICIPATION_TYPES = {
    "active_scene",
    "flashback",
    "memory",
    "vision",
    "letter",
    "recording",
    "historical_reference",
    "dream",
    "hallucination",
}


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,))
    return cursor.fetchone() is not None


def run_graph_sanity(graph_path: str) -> dict:
    conn = sqlite3.connect(graph_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        issues = []

        cursor.execute("""
            SELECT lower(canonical_name), entity_type,
                   COALESCE(boundary_book_id, boundary_title_id, ''),
                   COALESCE(boundary_volume_id, ''),
                   COALESCE(session_id, ''),
                   COUNT(*),
                   GROUP_CONCAT(id)
            FROM entities
            GROUP BY lower(canonical_name), entity_type,
                     COALESCE(boundary_book_id, boundary_title_id, ''),
                     COALESCE(boundary_volume_id, ''),
                     COALESCE(session_id, '')
            HAVING COUNT(*) > 1
        """)
        for name, entity_type, book_id, volume_id, session_id, count, ids in cursor.fetchall():
            issues.append({
                "type": "duplicate_canonical_within_boundary",
                "name": name,
                "entity_type": entity_type,
                "book_id": book_id,
                "volume_id": volume_id,
                "session_id": session_id,
                "count": count,
                "entity_ids": ids,
            })

        cursor.execute("""
            SELECT a.id, a.alias_name, a.entity_id
            FROM aliases a
            LEFT JOIN entities e ON a.entity_id = e.id
            WHERE e.id IS NULL
        """)
        for alias_id, alias_name, entity_id in cursor.fetchall():
            issues.append({"type": "orphan_alias", "alias_id": alias_id, "alias": alias_name, "entity_id": entity_id})

        cursor.execute("""
            SELECT a.id, e.canonical_name, a.alias_name
            FROM aliases a
            JOIN entities e ON a.entity_id = e.id
            WHERE lower(e.canonical_name) = lower(a.alias_name)
        """)
        for alias_id, canonical_name, alias_name in cursor.fetchall():
            issues.append({"type": "self_alias", "alias_id": alias_id, "canonical_name": canonical_name, "alias": alias_name})

        if _table_exists(cursor, "terminology_aliases"):
            cursor.execute("""
                SELECT a.id, a.term_id, a.alias
                FROM terminology_aliases a
                LEFT JOIN terminology_objects t ON a.term_id = t.id
                WHERE t.id IS NULL
            """)
            for alias_id, term_id, alias in cursor.fetchall():
                issues.append({"type": "orphan_terminology_alias", "alias_id": alias_id, "term_id": term_id, "alias": alias})
        if _table_exists(cursor, "terminology_evidence"):
            cursor.execute("""
                SELECT e.id, e.term_id
                FROM terminology_evidence e
                LEFT JOIN terminology_objects t ON e.term_id = t.id
                WHERE e.term_id IS NOT NULL AND t.id IS NULL
            """)
            for evidence_id, term_id in cursor.fetchall():
                issues.append({"type": "orphan_terminology_evidence", "evidence_id": evidence_id, "term_id": term_id})

        if _table_exists(cursor, "identity_promotions"):
            cursor.execute("SELECT id FROM entities WHERE canonical_name = '[UNNAMED_POV]'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM identity_promotions WHERE COALESCE(status, 'candidate') = 'accepted'")
                if cursor.fetchone()[0] == 0:
                    issues.append({"type": "unpromoted_narrator", "entity": "[UNNAMED_POV]"})

        cursor.execute("""
            SELECT ep.event_id, ep.entity_id
            FROM event_participants ep
            LEFT JOIN events ev ON ep.event_id = ev.id
            LEFT JOIN entities e ON ep.entity_id = e.id
            WHERE ev.id IS NULL OR e.id IS NULL
        """)
        for event_id, entity_id in cursor.fetchall():
            issues.append({"type": "orphan_event_participant", "event_id": event_id, "entity_id": entity_id})

        if _table_exists(cursor, "title_links"):
            cursor.execute("""
                SELECT title_key, COUNT(DISTINCT entity_id), GROUP_CONCAT(entity_id)
                FROM title_links
                WHERE COALESCE(status, 'candidate') != 'rejected'
                GROUP BY title_key
                HAVING COUNT(DISTINCT entity_id) > 1
            """)
            for title_key, count, ids in cursor.fetchall():
                issues.append({"type": "conflicting_title_link", "title_key": title_key, "count": count, "entity_ids": ids})

        if _table_exists(cursor, "aliases"):
            cursor.execute("""
                SELECT e.id, e.canonical_name, COUNT(*) AS alias_count
                FROM entities e
                JOIN aliases a ON e.id = a.entity_id
                WHERE COALESCE(a.status, 'candidate') != 'rejected'
                GROUP BY e.id, e.canonical_name
                HAVING COUNT(*) > 25
            """)
            for entity_id, canonical_name, alias_count in cursor.fetchall():
                issues.append({
                    "type": "oversized_alias_group",
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "alias_count": alias_count,
                })

        if _table_exists(cursor, "relationship_history"):
            cursor.execute("""
                SELECT rel_key, chapter, COALESCE(interaction_order, -1),
                       COALESCE(event_id, -1), COUNT(*)
                FROM relationship_history
                GROUP BY rel_key, chapter, COALESCE(interaction_order, -1),
                         COALESCE(event_id, -1), COALESCE(evidence, '')
                HAVING COUNT(*) > 1
            """)
            for rel_key, chapter, interaction_order, event_id, count in cursor.fetchall():
                issues.append({
                    "type": "duplicate_relationship_history",
                    "rel_key": rel_key,
                    "chapter": chapter,
                    "interaction_order": interaction_order,
                    "event_id": event_id,
                    "count": count,
                })

        if _table_exists(cursor, "entity_search_terms"):
            cursor.execute("""
                SELECT e.id, e.canonical_name
                FROM entities e
                LEFT JOIN entity_search_terms est ON e.id = est.entity_id
                WHERE est.entity_id IS NULL
            """)
            for entity_id, canonical_name in cursor.fetchall():
                issues.append({
                    "type": "missing_entity_search_terms",
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                })

        cursor.execute("""
            SELECT id, canonical_name, entity_type
            FROM entities
            WHERE lower(canonical_name) IN ({})
               OR COALESCE(surface_form_class, '') IN ('role', 'kinship')
        """.format(",".join("?" for _ in ROLE_ONLY_CANONICALS)), tuple(sorted(ROLE_ONLY_CANONICALS)))
        for entity_id, canonical_name, entity_type in cursor.fetchall():
            issues.append({
                "type": "role_only_canonical",
                "entity_id": entity_id,
                "canonical_name": canonical_name,
                "entity_type": entity_type,
            })

        if _table_exists(cursor, "unresolved_mentions"):
            cursor.execute("""
                SELECT mention_key, entity_type, COUNT(*)
                FROM unresolved_mentions
                WHERE COALESCE(ambiguous, 1) = 1
                GROUP BY mention_key, entity_type
                HAVING COUNT(*) > 10
            """)
            for mention_key, entity_type, count in cursor.fetchall():
                issues.append({
                    "type": "high_unresolved_mention_count",
                    "mention_key": mention_key,
                    "entity_type": entity_type,
                    "count": count,
                })

            cursor.execute("""
                SELECT u.id, u.mention_text, u.mention_class, e.id
                FROM unresolved_mentions u
                JOIN entities e ON lower(e.canonical_name) = lower(u.mention_text)
                WHERE COALESCE(u.ambiguous, 1) = 1
                  AND COALESCE(u.mention_class, 'entity') IN ('kinship', 'title')
            """)
            for mention_id, mention_text, mention_class, entity_id in cursor.fetchall():
                issues.append({
                    "type": "unresolved_role_promoted",
                    "mention_id": mention_id,
                    "mention": mention_text,
                    "mention_class": mention_class,
                    "entity_id": entity_id,
                })

        if _table_exists(cursor, "entities"):
            cursor.execute("""
                SELECT id, canonical_name
                FROM entities
                WHERE COALESCE(display_name, '') = ''
            """)
            for entity_id, canonical_name in cursor.fetchall():
                issues.append({
                    "type": "missing_display_name",
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                })

        if _table_exists(cursor, "relationships"):
            cursor.execute("""
                SELECT rel_key, source_id, target_id
                FROM relationships
                WHERE source_id = target_id
            """)
            for rel_key, source_id, target_id in cursor.fetchall():
                issues.append({
                    "type": "self_relationship",
                    "rel_key": rel_key,
                    "source_id": source_id,
                    "target_id": target_id,
                })

            cursor.execute("""
                SELECT rel_key, source_id, target_id
                FROM relationships
                WHERE rel_key != CAST(source_id AS TEXT) || '::' || CAST(target_id AS TEXT)
            """)
            for rel_key, source_id, target_id in cursor.fetchall():
                issues.append({
                    "type": "non_directional_relationship_key",
                    "rel_key": rel_key,
                    "source_id": source_id,
                    "target_id": target_id,
                })

            cursor.execute("""
                SELECT r.rel_key,
                       es.entity_type, COALESCE(es.entity_category, 'UNKNOWN'),
                       COALESCE(es.sentience, 'unknown'), COALESCE(es.can_form_relationships, 'unknown'),
                       et.entity_type, COALESCE(et.entity_category, 'UNKNOWN'),
                       COALESCE(et.sentience, 'unknown'), COALESCE(et.can_form_relationships, 'unknown')
                FROM relationships r
                JOIN entities es ON r.source_id = es.id
                JOIN entities et ON r.target_id = et.id
                WHERE COALESCE(es.entity_category, 'UNKNOWN') IN ('REFERENCE', 'CONCEPT')
                   OR COALESCE(et.entity_category, 'UNKNOWN') IN ('REFERENCE', 'CONCEPT')
                   OR (
                       COALESCE(es.entity_category, 'UNKNOWN') != 'GROUP'
                       AND COALESCE(es.sentience, 'unknown') != 'true'
                       AND COALESCE(es.can_form_relationships, 'unknown') != 'true'
                   )
                   OR (
                       COALESCE(et.entity_category, 'UNKNOWN') != 'GROUP'
                       AND COALESCE(et.sentience, 'unknown') != 'true'
                       AND COALESCE(et.can_form_relationships, 'unknown') != 'true'
                   )
            """)
            for rel_key, source_type, source_category, source_sentience, source_can_form, target_type, target_category, target_sentience, target_can_form in cursor.fetchall():
                issues.append({
                    "type": "ontology_invalid_relationship",
                    "rel_key": rel_key,
                    "source_type": source_type,
                    "source_category": source_category,
                    "source_sentience": source_sentience,
                    "source_can_form_relationships": source_can_form,
                    "target_type": target_type,
                    "target_category": target_category,
                    "target_sentience": target_sentience,
                    "target_can_form_relationships": target_can_form,
                })

        if _table_exists(cursor, "event_participants"):
            cursor.execute("""
                SELECT ep.event_id, ep.entity_id, e.entity_type,
                       COALESCE(e.entity_category, 'UNKNOWN'),
                       COALESCE(e.active_status, 'uncertain'),
                       COALESCE(e.entity_persistence, 'persistent'),
                       COALESCE(e.interpretation_status, 'actual')
                FROM event_participants ep
                JOIN entities e ON ep.entity_id = e.id
                WHERE COALESCE(e.entity_category, 'UNKNOWN') NOT IN ('CHARACTER', 'GROUP', 'LOCATION', 'OBJECT')
                   OR COALESCE(e.active_status, 'uncertain') IN ('referenced_only', 'historical_only', 'symbolic_only')
                   OR COALESCE(e.entity_persistence, 'persistent') IN ('dream_only', 'hallucination_only')
                   OR COALESCE(e.interpretation_status, 'actual') LIKE '%dream%'
                   OR COALESCE(e.interpretation_status, 'actual') LIKE '%hallucination%'
                   OR COALESCE(e.interpretation_status, 'actual') LIKE '%imagined%'
                   OR COALESCE(e.interpretation_status, 'actual') LIKE '%metaphorical%'
            """)
            for event_id, entity_id, entity_type, category, active_status, persistence, interpretation in cursor.fetchall():
                issues.append({
                    "type": "ontology_invalid_event_participant",
                    "event_id": event_id,
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "entity_category": category,
                    "active_status": active_status,
                    "entity_persistence": persistence,
                    "interpretation_status": interpretation,
                })

        if _table_exists(cursor, "chapter_boundaries"):
            cursor.execute("""
                SELECT chapter
                FROM chapter_boundaries
                WHERE COALESCE(inherited_confidence, 1.0) < 1.0
                  AND (source_session IS NULL OR source_session = '')
            """)
            for (chapter,) in cursor.fetchall():
                issues.append({
                    "type": "inherited_boundary_missing_source",
                    "chapter": chapter,
                })
            cursor.execute("""
                SELECT chapter
                FROM chapter_boundaries
                WHERE COALESCE(book_id, title_id, '') = ''
            """)
            for (chapter,) in cursor.fetchall():
                issues.append({"type": "chapter_boundary_missing_book_id", "chapter": chapter})

        if _table_exists(cursor, "schema_metadata"):
            expected_metadata = {
                "graph_schema_version": str(GRAPH_SCHEMA_VERSION),
                "cache_version": str(CACHE_VERSION),
                "prompt_version": PROMPT_VERSION,
                "normalization_version": str(NORMALIZATION_VERSION),
            }
            for key, expected in expected_metadata.items():
                cursor.execute("SELECT value FROM schema_metadata WHERE key = ?", (key,))
                row = cursor.fetchone()
                if not row or str(row[0]) != expected:
                    issues.append({
                        "type": "schema_metadata_mismatch",
                        "key": key,
                        "expected": expected,
                        "actual": row[0] if row else None,
                    })

        if _table_exists(cursor, "chapter_pov"):
            cursor.execute("""
                SELECT chapter, entity_id
                FROM chapter_pov
                WHERE entity_id IS NULL
                   OR COALESCE(narrator_type, '') = ''
            """)
            for chapter, entity_id in cursor.fetchall():
                issues.append({
                    "type": "chapter_pov_missing_narrator_state",
                    "chapter": chapter,
                    "entity_id": entity_id,
                })

        if _table_exists(cursor, "events"):
            cursor.execute("""
                SELECT id, chapter
                FROM events
                WHERE COALESCE(event_identity_key, '') = ''
                   OR COALESCE(scene_scope, '') = ''
            """)
            for event_id, chapter in cursor.fetchall():
                issues.append({
                    "type": "event_missing_identity_or_scope",
                    "event_id": event_id,
                    "chapter": chapter,
                })

            cursor.execute("""
                SELECT id, chapter
                FROM events
                WHERE COALESCE(evidence_source_type, '') = ''
                   OR COALESCE(actuality_status, '') = ''
                   OR narrative_order IS NULL
                   OR COALESCE(source_section_type, '') = ''
            """)
            for event_id, chapter in cursor.fetchall():
                issues.append({
                    "type": "event_missing_source_or_order_metadata",
                    "event_id": event_id,
                    "chapter": chapter,
                })

        if _table_exists(cursor, "event_landmarks"):
            cursor.execute("""
                SELECT id, identity_key, lifecycle, event_state, event_reliability, reader_visibility
                FROM event_landmarks
                WHERE COALESCE(identity_key, '') = ''
                   OR COALESCE(lifecycle, '') NOT IN ('candidate', 'landmark', 'historically_referenced', 'legacy_landmark')
                   OR COALESCE(event_state, '') NOT IN ('planned', 'ongoing', 'completed', 'remembered', 'historical', 'unknown')
                   OR COALESCE(event_reliability, '') NOT IN ('direct', 'reported', 'historical', 'rumor', 'legend', 'myth', 'unknown')
                   OR COALESCE(reader_visibility, '') NOT IN ('hidden', 'partially_known', 'fully_known')
            """)
            for landmark_id, identity_key, lifecycle, event_state, reliability, visibility in cursor.fetchall():
                issues.append({
                    "type": "landmark_invalid_snapshot",
                    "landmark_id": landmark_id,
                    "identity_key": identity_key,
                    "lifecycle": lifecycle,
                    "event_state": event_state,
                    "reliability": reliability,
                    "visibility": visibility,
                })

        if _table_exists(cursor, "landmark_names"):
            cursor.execute("""
                SELECT ln.id, ln.landmark_id, ln.name_text
                FROM landmark_names ln
                LEFT JOIN event_landmarks lm ON lm.id = ln.landmark_id
                WHERE lm.id IS NULL OR COALESCE(ln.name_key, '') = '' OR COALESCE(ln.name_text, '') = ''
            """)
            for name_id, landmark_id, name_text in cursor.fetchall():
                issues.append({
                    "type": "invalid_landmark_name",
                    "name_id": name_id,
                    "landmark_id": landmark_id,
                    "name": name_text,
                })

        if _table_exists(cursor, "landmark_event_links"):
            cursor.execute("""
                SELECT lel.landmark_id, lel.event_id, lel.link_type
                FROM landmark_event_links lel
                LEFT JOIN event_landmarks lm ON lm.id = lel.landmark_id
                LEFT JOIN events ev ON ev.id = lel.event_id
                WHERE lm.id IS NULL OR ev.id IS NULL
            """)
            for landmark_id, event_id, link_type in cursor.fetchall():
                issues.append({
                    "type": "orphan_landmark_event_link",
                    "landmark_id": landmark_id,
                    "event_id": event_id,
                    "link_type": link_type,
                })
            cursor.execute("""
                SELECT ev.id, ev.landmark_id
                FROM events ev
                WHERE ev.landmark_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM landmark_event_links lel
                      WHERE lel.event_id = ev.id AND lel.landmark_id = ev.landmark_id
                  )
            """)
            for event_id, landmark_id in cursor.fetchall():
                issues.append({
                    "type": "event_landmark_missing_link",
                    "event_id": event_id,
                    "landmark_id": landmark_id,
                })

        if _table_exists(cursor, "landmark_hierarchy"):
            cursor.execute("""
                SELECT parent_landmark_id, child_landmark_id, relation_type
                FROM landmark_hierarchy
                WHERE parent_landmark_id = child_landmark_id
            """)
            for parent_id, child_id, relation_type in cursor.fetchall():
                issues.append({
                    "type": "self_landmark_hierarchy",
                    "landmark_id": parent_id,
                    "relation_type": relation_type,
                })

        if _table_exists(cursor, "relationship_history"):
            cursor.execute("""
                SELECT id, rel_key, chapter
                FROM relationship_history
                WHERE COALESCE(inherited_confidence, 1.0) < 1.0
                  AND (source_session IS NULL OR source_session = '')
            """)
            for history_id, rel_key, chapter in cursor.fetchall():
                issues.append({
                    "type": "inherited_relationship_missing_source",
                    "relationship_history_id": history_id,
                    "rel_key": rel_key,
                    "chapter": chapter,
                })
            cursor.execute("""
                SELECT id, rel_key, chapter
                FROM relationship_history
                WHERE COALESCE(scene_scope, '') = ''
            """)
            for history_id, rel_key, chapter in cursor.fetchall():
                issues.append({
                    "type": "relationship_history_missing_scene_scope",
                    "relationship_history_id": history_id,
                    "rel_key": rel_key,
                    "chapter": chapter,
                })

        if _table_exists(cursor, "relationship_social_edges"):
            cursor.execute("""
                SELECT edge_key, source_id, target_id
                FROM relationship_social_edges
                WHERE source_id = target_id
            """)
            for edge_key, source_id, target_id in cursor.fetchall():
                issues.append({
                    "type": "self_social_edge",
                    "edge_key": edge_key,
                    "source_id": source_id,
                    "target_id": target_id,
                })

            cursor.execute("""
                SELECT se.edge_key,
                       es.entity_type, COALESCE(es.entity_category, 'UNKNOWN'),
                       COALESCE(es.sentience, 'unknown'), COALESCE(es.can_form_relationships, 'unknown'),
                       et.entity_type, COALESCE(et.entity_category, 'UNKNOWN'),
                       COALESCE(et.sentience, 'unknown'), COALESCE(et.can_form_relationships, 'unknown')
                FROM relationship_social_edges se
                JOIN entities es ON se.source_id = es.id
                JOIN entities et ON se.target_id = et.id
                WHERE COALESCE(es.entity_category, 'UNKNOWN') IN ('REFERENCE', 'CONCEPT')
                   OR COALESCE(et.entity_category, 'UNKNOWN') IN ('REFERENCE', 'CONCEPT')
                   OR (
                       COALESCE(es.entity_category, 'UNKNOWN') != 'GROUP'
                       AND COALESCE(es.sentience, 'unknown') != 'true'
                       AND COALESCE(es.can_form_relationships, 'unknown') != 'true'
                   )
                   OR (
                       COALESCE(et.entity_category, 'UNKNOWN') != 'GROUP'
                       AND COALESCE(et.sentience, 'unknown') != 'true'
                       AND COALESCE(et.can_form_relationships, 'unknown') != 'true'
                   )
            """)
            for edge_key, source_type, source_category, source_sentience, source_can_form, target_type, target_category, target_sentience, target_can_form in cursor.fetchall():
                issues.append({
                    "type": "ontology_invalid_social_edge",
                    "edge_key": edge_key,
                    "source_type": source_type,
                    "source_category": source_category,
                    "source_sentience": source_sentience,
                    "source_can_form_relationships": source_can_form,
                    "target_type": target_type,
                    "target_category": target_category,
                    "target_sentience": target_sentience,
                    "target_can_form_relationships": target_can_form,
                })

            cursor.execute("""
                SELECT edge_key, edge_layer, promotion_state
                FROM relationship_social_edges
                WHERE edge_layer IN ('chapter_copresence', 'cooccurrence', 'group_proximity')
                  AND promotion_state = 'confirmed'
            """)
            for edge_key, edge_layer, promotion_state in cursor.fetchall():
                issues.append({
                    "type": "weak_social_edge_overpromoted",
                    "edge_key": edge_key,
                    "edge_layer": edge_layer,
                    "promotion_state": promotion_state,
                })

            cursor.execute("""
                SELECT edge_key
                FROM relationship_social_edges
                WHERE COALESCE(inherited_confidence, 1.0) < 1.0
                  AND (source_session IS NULL OR source_session = '')
            """)
            for (edge_key,) in cursor.fetchall():
                issues.append({
                    "type": "inherited_social_edge_missing_source",
                    "edge_key": edge_key,
                })

        if _table_exists(cursor, "relationship_social_evidence"):
            cursor.execute("""
                SELECT rse.id, rse.edge_key
                FROM relationship_social_evidence rse
                LEFT JOIN relationship_social_edges se ON rse.edge_key = se.edge_key
                WHERE se.edge_key IS NULL
            """)
            for evidence_id, edge_key in cursor.fetchall():
                issues.append({
                    "type": "orphan_social_evidence",
                    "social_evidence_id": evidence_id,
                    "edge_key": edge_key,
                })

            cursor.execute("""
                SELECT id, edge_key, chapter
                FROM relationship_social_evidence
                WHERE COALESCE(scene_scope, '') = ''
            """)
            for evidence_id, edge_key, chapter in cursor.fetchall():
                issues.append({
                    "type": "social_evidence_missing_scene_scope",
                    "social_evidence_id": evidence_id,
                    "edge_key": edge_key,
                    "chapter": chapter,
                })

        if _table_exists(cursor, "relationship_community_members"):
            cursor.execute("""
                SELECT rcm.community_key, rcm.entity_id
                FROM relationship_community_members rcm
                LEFT JOIN relationship_communities rc ON rcm.community_key = rc.community_key
                WHERE rc.community_key IS NULL
            """)
            for community_key, entity_id in cursor.fetchall():
                issues.append({
                    "type": "orphan_community_member",
                    "community_key": community_key,
                    "entity_id": entity_id,
                })

        if _table_exists(cursor, "mention_occurrences"):
            cursor.execute("""
                SELECT id, surface_form, chapter
                FROM mention_occurrences
                WHERE COALESCE(mention_source_type, '') = ''
                   OR COALESCE(source_section_type, '') = ''
            """)
            for mention_id, surface_form, chapter in cursor.fetchall():
                issues.append({
                    "type": "mention_missing_source_metadata",
                    "mention_id": mention_id,
                    "surface_form": surface_form,
                    "chapter": chapter,
                })

        if _table_exists(cursor, "reference_mentions"):
            cursor.execute("""
                SELECT id, surface_form, chapter
                FROM reference_mentions
                WHERE COALESCE(reference_subtype, '') = ''
                   OR COALESCE(promotion_state, '') = ''
                   OR COALESCE(score_breakdown, '') = ''
            """)
            for mention_id, surface_form, chapter in cursor.fetchall():
                issues.append({
                    "type": "reference_mention_missing_score_metadata",
                    "mention_id": mention_id,
                    "surface_form": surface_form,
                    "chapter": chapter,
                })

            if _table_exists(cursor, "name_semantic_relations"):
                cursor.execute("""
                    SELECT rm.id, rm.surface_form, rm.chapter, rm.reference_subtype
                    FROM reference_mentions rm
                    WHERE rm.reference_subtype IN (
                        'namesake_reference', 'vehicle_reference', 'place_reference',
                        'artifact_reference', 'institution_reference',
                        'commemorative_reference'
                    )
                      AND COALESCE(rm.reference_score, 0) > COALESCE(rm.participation_score, 0)
                      AND NOT EXISTS (
                          SELECT 1
                          FROM name_semantic_relations nsr
                          WHERE nsr.reference_mention_id = rm.id
                             OR nsr.source_normalized = rm.normalized_form
                             OR nsr.target_normalized = rm.normalized_form
                      )
                """)
                for mention_id, surface_form, chapter, reference_subtype in cursor.fetchall():
                    issues.append({
                        "type": "reference_missing_name_semantic_relation",
                        "mention_id": mention_id,
                        "surface_form": surface_form,
                        "chapter": chapter,
                        "reference_subtype": reference_subtype,
                    })

        if _table_exists(cursor, "name_semantic_relations"):
            cursor.execute("""
                SELECT id, relation_type, chapter
                FROM name_semantic_relations
                WHERE COALESCE(relation_type, '') = ''
                   OR (COALESCE(source_normalized, '') = '' AND COALESCE(target_normalized, '') = '')
                   OR COALESCE(relation_context, source_quote, '') = ''
            """)
            for relation_id, relation_type, chapter in cursor.fetchall():
                issues.append({
                    "type": "name_semantic_relation_missing_provenance",
                    "relation_id": relation_id,
                    "relation_type": relation_type,
                    "chapter": chapter,
                })

            cursor.execute("""
                SELECT e.id, e.canonical_name, e.entity_type, nsr.relation_type
                FROM entities e
                JOIN name_semantic_relations nsr
                 ON e.entity_type IN ('INDIVIDUAL', 'GROUP', 'LOCATION')
                 AND (
                     lower(e.canonical_name) = nsr.source_normalized
                     OR lower(e.canonical_name) = nsr.target_normalized
                 )
                WHERE nsr.relation_type IN ('namesake', 'eponym_attribution', 'possessive_reference')
                  AND COALESCE(e.mention_count, 0) <= 1
                  AND NOT EXISTS (
                      SELECT 1 FROM event_participants ep WHERE ep.entity_id = e.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM relationships r WHERE r.source_id = e.id OR r.target_id = e.id
                  )
            """)
            for entity_id, canonical_name, entity_type, relation_type in cursor.fetchall():
                issues.append({
                    "type": "active_entity_only_supported_by_name_reference",
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "relation_type": relation_type,
                })

        if _table_exists(cursor, "life_status_evidence"):
            cursor.execute("""
                SELECT id, entity_id, actual_status, belief_status,
                       appearance_status, participation_type, evidence_text,
                       COALESCE(inherited_confidence, 1.0), source_session
                FROM life_status_evidence
            """)
            for (
                evidence_id, entity_id, actual_status, belief_status,
                appearance_status, participation_type, evidence_text,
                inherited_confidence, source_session
            ) in cursor.fetchall():
                if actual_status not in LIFE_ACTUAL_STATUS_VALUES:
                    issues.append({"type": "invalid_life_actual_status", "evidence_id": evidence_id, "value": actual_status})
                if belief_status not in LIFE_BELIEF_STATUS_VALUES:
                    issues.append({"type": "invalid_life_belief_status", "evidence_id": evidence_id, "value": belief_status})
                if appearance_status not in LIFE_APPEARANCE_STATUS_VALUES:
                    issues.append({"type": "invalid_life_appearance_status", "evidence_id": evidence_id, "value": appearance_status})
                if participation_type not in LIFE_PARTICIPATION_TYPES:
                    issues.append({"type": "invalid_life_participation_type", "evidence_id": evidence_id, "value": participation_type})
                if not evidence_text:
                    issues.append({"type": "life_status_missing_evidence_text", "evidence_id": evidence_id, "entity_id": entity_id})
                if float(inherited_confidence or 1.0) < 1.0 and not source_session:
                    issues.append({"type": "inherited_life_status_missing_source", "evidence_id": evidence_id, "entity_id": entity_id})
                if participation_type in {"dream", "vision", "flashback", "memory", "letter", "recording", "historical_reference", "hallucination"} and actual_status in {"alive", "dead"}:
                    issues.append({
                        "type": "non_physical_participation_updates_actual_life_status",
                        "evidence_id": evidence_id,
                        "entity_id": entity_id,
                        "participation_type": participation_type,
                        "actual_status": actual_status,
                    })

        if _table_exists(cursor, "life_status_snapshots") and _table_exists(cursor, "life_status_evidence"):
            cursor.execute("""
                SELECT s.entity_id, s.actual_status, s.latest_evidence_id
                FROM life_status_snapshots s
                LEFT JOIN life_status_evidence lse ON s.latest_evidence_id = lse.id
                WHERE s.scope_type = 'global_story'
                  AND (s.latest_evidence_id IS NULL OR lse.id IS NULL)
            """)
            for entity_id, actual_status, latest_evidence_id in cursor.fetchall():
                issues.append({
                    "type": "life_status_snapshot_missing_evidence",
                    "entity_id": entity_id,
                    "actual_status": actual_status,
                    "latest_evidence_id": latest_evidence_id,
                })

        if _table_exists(cursor, "entity_legacy_signals"):
            cursor.execute("""
                SELECT id, entity_id, evidence_text,
                       COALESCE(inherited_confidence, 1.0), source_session
                FROM entity_legacy_signals
                WHERE COALESCE(evidence_text, '') = ''
                   OR (COALESCE(inherited_confidence, 1.0) < 1.0
                       AND COALESCE(source_session, '') = '')
            """)
            for signal_id, entity_id, evidence_text, inherited_confidence, source_session in cursor.fetchall():
                issues.append({
                    "type": "legacy_signal_missing_evidence_or_source",
                    "signal_id": signal_id,
                    "entity_id": entity_id,
                    "missing_evidence": not bool(evidence_text),
                    "missing_inherited_source": float(inherited_confidence or 1.0) < 1.0 and not source_session,
                })

        if _table_exists(cursor, "relationship_history") and _table_exists(cursor, "entities"):
            cursor.execute("""
                SELECT rh.id, rh.rel_key, rh.chapter, es.current_life_status, et.current_life_status
                FROM relationship_history rh
                JOIN relationships r ON rh.rel_key = r.rel_key
                JOIN entities es ON r.source_id = es.id
                JOIN entities et ON r.target_id = et.id
                WHERE COALESCE(rh.evidence_source_type, 'observed_fact') IN ('observed_fact', 'direct', 'dialogue')
                  AND (COALESCE(es.current_life_status, 'unknown') = 'dead'
                       OR COALESCE(et.current_life_status, 'unknown') = 'dead')
            """)
            for history_id, rel_key, chapter, source_life, target_life in cursor.fetchall():
                issues.append({
                    "type": "active_relationship_with_dead_snapshot",
                    "relationship_history_id": history_id,
                    "rel_key": rel_key,
                    "chapter": chapter,
                    "source_life_status": source_life,
                    "target_life_status": target_life,
                })

        if _table_exists(cursor, "entities"):
            if _table_exists(cursor, "entity_ontology_evidence"):
                cursor.execute("""
                    SELECT e.id, e.canonical_name, e.entity_category, e.species_or_kind
                    FROM entities e
                    WHERE COALESCE(e.entity_category, 'UNKNOWN') != 'UNKNOWN'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM entity_ontology_evidence ev
                          WHERE ev.entity_id = e.id
                            AND ev.ontology_field = 'entity_category'
                      )
                """)
                for entity_id, canonical_name, entity_category, species_or_kind in cursor.fetchall():
                    issues.append({
                        "type": "ontology_missing_provenance",
                        "entity_id": entity_id,
                        "canonical_name": canonical_name,
                        "entity_category": entity_category,
                        "species_or_kind": species_or_kind,
                    })

            cursor.execute("""
                SELECT e.id, e.canonical_name, e.entity_category,
                       e.entity_persistence, e.interpretation_status
                FROM entities e
                WHERE (
                    COALESCE(e.entity_persistence, 'persistent') IN ('dream_only', 'hallucination_only')
                    OR COALESCE(e.interpretation_status, 'actual') LIKE '%dream%'
                    OR COALESCE(e.interpretation_status, 'actual') LIKE '%hallucination%'
                    OR COALESCE(e.interpretation_status, 'actual') LIKE '%imagined%'
                    OR COALESCE(e.interpretation_status, 'actual') LIKE '%metaphorical%'
                )
                  AND (
                      EXISTS (SELECT 1 FROM relationships r WHERE r.source_id = e.id OR r.target_id = e.id)
                      OR EXISTS (SELECT 1 FROM relationship_social_edges se WHERE se.source_id = e.id OR se.target_id = e.id)
                      OR EXISTS (SELECT 1 FROM event_participants ep WHERE ep.entity_id = e.id)
                  )
            """)
            for entity_id, canonical_name, entity_category, persistence, interpretation_status in cursor.fetchall():
                issues.append({
                    "type": "non_actual_entity_promoted_to_graph",
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "entity_category": entity_category,
                    "entity_persistence": persistence,
                    "interpretation_status": interpretation_status,
                })

            cursor.execute("""
                SELECT e.id, e.canonical_name, e.entity_category
                FROM entities e
                WHERE COALESCE(e.entity_category, 'UNKNOWN') = 'OBJECT'
                  AND COALESCE(e.sentience, 'unknown') != 'true'
                  AND COALESCE(e.can_form_relationships, 'unknown') != 'true'
                  AND (
                      EXISTS (SELECT 1 FROM relationships r WHERE r.source_id = e.id OR r.target_id = e.id)
                      OR EXISTS (SELECT 1 FROM relationship_social_edges se WHERE se.source_id = e.id OR se.target_id = e.id)
                  )
            """)
            for entity_id, canonical_name, entity_category in cursor.fetchall():
                issues.append({
                    "type": "non_sentient_object_has_social_edge",
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "entity_category": entity_category,
                })

        if _table_exists(cursor, "events"):
            cursor.execute("""
                SELECT id, chapter
                FROM events
                WHERE COALESCE(inherited_confidence, 1.0) < 1.0
                  AND (source_session IS NULL OR source_session = '')
            """)
            for event_id, chapter in cursor.fetchall():
                issues.append({
                    "type": "inherited_event_missing_source",
                    "event_id": event_id,
                    "chapter": chapter,
                })

        if _table_exists(cursor, "event_landmarks"):
            cursor.execute("""
                SELECT id, identity_key
                FROM event_landmarks
                WHERE COALESCE(inherited_confidence, 1.0) < 1.0
                  AND (source_session IS NULL OR source_session = '')
            """)
            for landmark_id, identity_key in cursor.fetchall():
                issues.append({
                    "type": "inherited_landmark_missing_source",
                    "landmark_id": landmark_id,
                    "identity_key": identity_key,
                })

        if _table_exists(cursor, "merge_candidates"):
            cursor.execute("""
                SELECT COUNT(*)
                FROM merge_candidates
                WHERE COALESCE(state, 'candidate') != 'rejected'
            """)
            backlog_count = cursor.fetchone()[0]
            if backlog_count:
                issues.append({"type": "stale_merge_candidate_backlog", "count": backlog_count})

            cursor.execute("""
                SELECT mc.entity_a_id, mc.entity_b_id, mc.votes,
                       MIN(5, 2 + CAST((
                           (
                               SELECT COUNT(*)
                               FROM aliases a
                               WHERE a.entity_id = mc.entity_b_id
                           ) + (
                               SELECT COUNT(*)
                               FROM relationships r
                               WHERE r.source_id = mc.entity_b_id
                                  OR r.target_id = mc.entity_b_id
                           )
                       ) / 2 AS INTEGER)) AS required_votes
                FROM merge_candidates mc
                WHERE COALESCE(mc.state, 'candidate') != 'rejected'
                  AND mc.votes >= MIN(5, 2 + CAST((
                    (
                        SELECT COUNT(*)
                        FROM aliases a
                        WHERE a.entity_id = mc.entity_b_id
                    ) + (
                        SELECT COUNT(*)
                        FROM relationships r
                        WHERE r.source_id = mc.entity_b_id
                           OR r.target_id = mc.entity_b_id
                    )
                ) / 2 AS INTEGER))
            """)
            for entity_a_id, entity_b_id, votes, required_votes in cursor.fetchall():
                issues.append({
                    "type": "merge_candidate_ready",
                    "entity_a_id": entity_a_id,
                    "entity_b_id": entity_b_id,
                    "votes": votes,
                    "required_votes": required_votes,
                })

        if _table_exists(cursor, "reader_snapshot_current") and _table_exists(cursor, "reader_snapshot_revisions"):
            cursor.execute("""
                SELECT current.chapter, current.snapshot_revision_id
                FROM reader_snapshot_current current
                LEFT JOIN reader_snapshot_revisions revision
                    ON revision.id = current.snapshot_revision_id
                WHERE revision.id IS NULL
                   OR revision.chapter != current.chapter
                   OR revision.content_hash != current.content_hash
            """)
            for chapter, revision_id in cursor.fetchall():
                issues.append({
                    "type": "snapshot_current_pointer_mismatch",
                    "chapter": chapter,
                    "snapshot_revision_id": revision_id,
                })

            cursor.execute("""
                SELECT chapter, content_hash, COUNT(*)
                FROM reader_snapshot_revisions
                GROUP BY chapter, content_hash
                HAVING COUNT(*) > 1
            """)
            for chapter, content_hash, count in cursor.fetchall():
                issues.append({
                    "type": "duplicate_semantic_snapshot_revision",
                    "chapter": chapter,
                    "content_hash": content_hash,
                    "count": count,
                })

        if _table_exists(cursor, "chapter_processing_checkpoints"):
            cursor.execute("""
                SELECT checkpoint.chapter, checkpoint.state
                FROM chapter_processing_checkpoints checkpoint
                LEFT JOIN chapter_evidence_revisions evidence
                    ON evidence.id = checkpoint.evidence_revision_id
                LEFT JOIN reader_snapshot_revisions snapshot
                    ON snapshot.id = checkpoint.snapshot_revision_id
                WHERE checkpoint.state = 'complete'
                  AND (evidence.id IS NULL OR snapshot.id IS NULL
                       OR checkpoint.evidence_hash != evidence.payload_hash
                       OR checkpoint.snapshot_hash != snapshot.content_hash)
            """)
            for chapter, state in cursor.fetchall():
                issues.append({
                    "type": "checkpoint_dependency_mismatch",
                    "chapter": chapter,
                    "state": state,
                })

        if _table_exists(cursor, "chapter_evidence_revisions") and _table_exists(cursor, "reader_snapshot_current"):
            cursor.execute("""
                SELECT evidence.chapter, evidence.revision
                FROM chapter_evidence_revisions evidence
                LEFT JOIN reader_snapshot_current current ON current.chapter = evidence.chapter
                WHERE evidence.is_active = 1 AND current.chapter IS NULL
            """)
            for chapter, revision in cursor.fetchall():
                issues.append({
                    "type": "active_evidence_missing_reader_snapshot",
                    "chapter": chapter,
                    "evidence_revision": revision,
                })

        if _table_exists(cursor, "image_evidence_revisions"):
            cursor.execute("""
                SELECT chapter, occurrence_order, COUNT(*)
                FROM image_evidence_revisions
                WHERE is_active = 1
                GROUP BY chapter, occurrence_order
                HAVING COUNT(*) > 1
            """)
            for chapter, occurrence_order, count in cursor.fetchall():
                issues.append({
                    "type": "multiple_active_image_occurrence_revisions",
                    "chapter": chapter,
                    "occurrence_order": occurrence_order,
                    "count": count,
                })

            cursor.execute("""
                SELECT id, chapter, occurrence_order, schema_version,
                       payload_json, payload_hash
                FROM image_evidence_revisions
                WHERE is_active = 1
            """)
            for row_id, chapter, occurrence_order, schema_version, payload_json, payload_hash in cursor.fetchall():
                actual_hash = hashlib.sha256(str(payload_json or "").encode("utf-8")).hexdigest()
                if actual_hash != payload_hash:
                    issues.append({
                        "type": "image_evidence_payload_hash_mismatch",
                        "image_evidence_revision_id": row_id,
                        "chapter": chapter,
                        "occurrence_order": occurrence_order,
                    })
                if schema_version != IMAGE_EVIDENCE_SCHEMA_VERSION:
                    issues.append({
                        "type": "invalid_active_image_evidence_schema",
                        "image_evidence_revision_id": row_id,
                        "schema_version": schema_version,
                    })
                try:
                    parsed_payload = json.loads(payload_json)
                except (TypeError, json.JSONDecodeError):
                    parsed_payload = {}
                if "raw_bytes" in parsed_payload or "raw_bytes" in str(payload_json):
                    issues.append({
                        "type": "serialized_image_raw_bytes",
                        "image_evidence_revision_id": row_id,
                    })

        if _table_exists(cursor, "image_occurrence_provenance"):
            cursor.execute("""
                SELECT provenance.id, provenance.image_evidence_revision_id
                FROM image_occurrence_provenance provenance
                LEFT JOIN image_evidence_revisions revision
                  ON revision.id = provenance.image_evidence_revision_id
                WHERE revision.id IS NULL
            """)
            for provenance_id, revision_id in cursor.fetchall():
                issues.append({
                    "type": "orphan_image_occurrence_provenance",
                    "provenance_id": provenance_id,
                    "image_evidence_revision_id": revision_id,
                })

        if _table_exists(cursor, "chapter_evidence_revisions") and _table_exists(cursor, "image_evidence_revisions"):
            cursor.execute("""
                SELECT id, chapter, payload_json
                FROM chapter_evidence_revisions
                WHERE is_active = 1
                ORDER BY chapter
            """)
            for evidence_id, chapter, payload_json in cursor.fetchall():
                try:
                    payload = json.loads(payload_json)
                except (TypeError, json.JSONDecodeError):
                    continue
                if (
                    payload.get("image_evidence_schema_version") != IMAGE_EVIDENCE_SCHEMA_VERSION
                    or not isinstance(payload.get("image_evidence"), list)
                ):
                    continue
                expected = sorted(
                    int((item.get("descriptor") or {}).get("occurrence_order", 0) or 0)
                    for item in payload["image_evidence"]
                    if isinstance(item, dict)
                )
                actual = [
                    int(row[0])
                    for row in cursor.execute("""
                        SELECT occurrence_order
                        FROM image_evidence_revisions
                        WHERE chapter_evidence_revision_id = ? AND is_active = 1
                        ORDER BY occurrence_order
                    """, (evidence_id,)).fetchall()
                ]
                if expected != actual:
                    issues.append({
                        "type": "authoritative_image_evidence_not_normalized",
                        "chapter": chapter,
                        "evidence_revision_id": evidence_id,
                        "expected_occurrences": expected,
                        "actual_occurrences": actual,
                    })

        if _table_exists(cursor, "image_parse_cache"):
            cursor.execute("""
                SELECT image_hash, parser_fingerprint
                FROM image_parse_cache
                WHERE image_hash = '' OR parser_fingerprint = ''
            """)
            for image_hash, parser_fingerprint in cursor.fetchall():
                issues.append({
                    "type": "invalid_image_cache_identity",
                    "image_hash": image_hash,
                    "parser_fingerprint": parser_fingerprint,
                })

        return {"issue_count": len(issues), "issues": issues}
    finally:
        conn.close()


def main():
    if len(sys.argv) != 2:
        print("Usage: python graph_sanity.py <graph.db>")
        sys.exit(1)
    print(json.dumps(run_graph_sanity(sys.argv[1]), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
