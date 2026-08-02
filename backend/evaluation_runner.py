import json
import os
import sqlite3
import sys


def _norm(value: str) -> str:
    return " ".join(str(value).lower().strip().split())


def _norm_pair(source: str, target: str) -> tuple[str, str]:
    return tuple(sorted((_norm(source), _norm(target))))


def _f1(predicted: set, expected: set) -> dict:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "predicted": len(predicted),
        "expected": len(expected),
        "true_positive": true_positive,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _load_chapter_cache(db_dir: str) -> list[dict]:
    chapters = []
    idx = 0
    while True:
        path = os.path.join(db_dir, f"chapter_{idx}.json")
        if not os.path.exists(path):
            break
        with open(path, "r", encoding="utf-8") as f:
            chapters.append(json.load(f))
        idx += 1
    return chapters


def _load_graph_predictions(db_dir: str) -> dict | None:
    graph_path = os.path.join(db_dir, "graph.db")
    if not os.path.exists(graph_path):
        return None

    conn = sqlite3.connect(graph_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tables = {row[0] for row in cursor.fetchall()}

        predictions = {
            "aliases": set(),
            "entities": set(),
            "relationships": set(),
            "social_relationships": set(),
            "events": set(),
            "spoiler_events": set(),
            "title_links": set(),
            "identity_promotions": set(),
            "mentions": set(),
            "event_clusters": set(),
            "landmarks": set(),
            "landmark_names": set(),
            "landmark_occurrences": set(),
            "landmark_resolution": set(),
            "alias_conflicts": set(),
            "surface_owners": {},
            "merge_candidates": set(),
            "conflict_records": set(),
            "identity_resolution_states": {},
            "unresolved_mentions": set(),
            "reference_mentions": set(),
            "name_semantic_relations": set(),
            "entity_ontology": set(),
            "entity_ontology_evidence": set(),
            "entity_state_history": set(),
            "entity_semantic_relations": set(),
            "language_observations": set(),
            "life_status_evidence": set(),
            "life_status_snapshots": set(),
            "life_status_timeline_segments": set(),
            "legacy_signals": set(),
            "ontology_compatibility_failures": set(),
            "conflict_priorities": set(),
            "communities": set(),
            "social_metrics": {},
        }

        if {"entities", "aliases"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, a.alias_name
                FROM aliases a
                JOIN entities e ON a.entity_id = e.id
                WHERE COALESCE(a.status, 'candidate') IN ('accepted', 'probable')
            """)
            predictions["aliases"] = {
                (_norm(canonical_name), _norm(alias_name))
                for canonical_name, alias_name in cursor.fetchall()
                if alias_name
            }
            cursor.execute("""
                SELECT e.canonical_name, a.alias_name
                FROM aliases a
                JOIN entities e ON a.entity_id = e.id
                WHERE COALESCE(a.status, 'candidate') IN ('accepted', 'probable')
            """)
            for canonical_name, alias_name in cursor.fetchall():
                predictions["surface_owners"][_norm(alias_name)] = _norm(canonical_name)

        if "entities" in tables:
            cursor.execute("SELECT canonical_name, entity_type FROM entities")
            predictions["entities"] = {
                (_norm(name), _norm(entity_type))
                for name, entity_type in cursor.fetchall()
            }
            for name, _entity_type in predictions["entities"]:
                predictions["surface_owners"][name] = name

            cursor.execute("""
                SELECT canonical_name, entity_category, species_or_kind,
                       sentience, active_status, identity_status,
                       entity_persistence, interpretation_status
                FROM entities
            """)
            predictions["entity_ontology"] = {
                (
                    _norm(name),
                    _norm(entity_category),
                    _norm(species_or_kind),
                    _norm(sentience),
                    _norm(active_status),
                    _norm(identity_status),
                    _norm(entity_persistence),
                    _norm(interpretation_status),
                )
                for (
                    name,
                    entity_category,
                    species_or_kind,
                    sentience,
                    active_status,
                    identity_status,
                    entity_persistence,
                    interpretation_status,
                ) in cursor.fetchall()
            }

        if {"relationships", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT es.canonical_name, et.canonical_name
                FROM relationships r
                JOIN entities es ON r.source_id = es.id
                JOIN entities et ON r.target_id = et.id
                WHERE r.current_trust_score IS NOT NULL
                   OR EXISTS (
                       SELECT 1
                       FROM relationship_history rh
                       WHERE rh.rel_key = r.rel_key
                   )
            """)
            predictions["relationships"] = {
                tuple(sorted((_norm(source), _norm(target))))
                for source, target in cursor.fetchall()
            }

        if {"relationship_social_edges", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT es.canonical_name, et.canonical_name,
                       se.edge_layer, se.edge_subtype, se.promotion_state
                FROM relationship_social_edges se
                JOIN entities es ON se.source_id = es.id
                JOIN entities et ON se.target_id = et.id
                WHERE COALESCE(se.promotion_state, 'weak') IN ('inferred', 'stable', 'confirmed')
            """)
            predictions["social_relationships"] = {
                (
                    *_norm_pair(source, target),
                    _norm(edge_layer),
                    _norm(edge_subtype),
                    _norm(promotion_state),
                )
                for source, target, edge_layer, edge_subtype, promotion_state in cursor.fetchall()
            }

        if "events" in tables:
            cursor.execute("SELECT chapter, summary FROM events")
            predictions["events"] = {
                (int(chapter), _norm(summary))
                for chapter, summary in cursor.fetchall()
            }
            predictions["spoiler_events"] = {event for _chapter, event in predictions["events"]}

        if {"event_landmarks", "landmark_names"}.issubset(tables):
            cursor.execute("""
                SELECT lm.landmark_type, lm.event_state, lm.event_reliability,
                       COALESCE(preferred.name_text, fallback.name_text, '')
                FROM event_landmarks lm
                LEFT JOIN landmark_names preferred ON preferred.id = lm.preferred_name_id
                LEFT JOIN landmark_names fallback ON fallback.landmark_id = lm.id
                    AND COALESCE(fallback.status, 'accepted') != 'rejected'
                GROUP BY lm.id
            """)
            predictions["landmarks"] = {
                (_norm(name), _norm(landmark_type), _norm(event_state), _norm(reliability))
                for landmark_type, event_state, reliability, name in cursor.fetchall()
            }
            cursor.execute("""
                SELECT ln.name_text, ln.name_role, ln.name_source_type,
                       ln.audience_type, ln.framing_polarity, ln.literal_status
                FROM landmark_names ln
                WHERE COALESCE(ln.status, 'accepted') != 'rejected'
            """)
            predictions["landmark_names"] = {
                (_norm(name), _norm(role), _norm(source_type), _norm(audience), _norm(framing), _norm(literal))
                for name, role, source_type, audience, framing, literal in cursor.fetchall()
            }

        if {"landmark_event_links", "events", "event_landmarks", "landmark_names"}.issubset(tables):
            cursor.execute("""
                SELECT ev.chapter, COALESCE(preferred.name_text, fallback.name_text, ''), lel.link_type
                FROM landmark_event_links lel
                JOIN events ev ON ev.id = lel.event_id
                JOIN event_landmarks lm ON lm.id = lel.landmark_id
                LEFT JOIN landmark_names preferred ON preferred.id = lm.preferred_name_id
                LEFT JOIN landmark_names fallback ON fallback.landmark_id = lm.id
                    AND COALESCE(fallback.status, 'accepted') != 'rejected'
                GROUP BY lel.landmark_id, lel.event_id, lel.link_type
            """)
            predictions["landmark_occurrences"] = {
                (int(chapter), _norm(name), _norm(link_type))
                for chapter, name, link_type in cursor.fetchall()
            }

        if "landmark_resolution_evidence" in tables:
            cursor.execute("SELECT decision, COUNT(*) FROM landmark_resolution_evidence GROUP BY decision")
            predictions["landmark_resolution"] = {
                (_norm(decision), int(count)) for decision, count in cursor.fetchall()
            }

        if {"title_links", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, t.title_text
                FROM title_links t
                JOIN entities e ON t.entity_id = e.id
                WHERE COALESCE(t.status, 'candidate') IN ('accepted', 'probable', 'candidate', 'review')
            """)
            predictions["title_links"] = {
                (_norm(canonical_name), _norm(title_text))
                for canonical_name, title_text in cursor.fetchall()
                if title_text
            }
            for canonical_name, title_text in predictions["title_links"]:
                predictions["surface_owners"][title_text] = canonical_name

        if {"identity_promotions", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT COALESCE(ep.canonical_name, '[UNNAMED_POV]'), er.canonical_name
                FROM identity_promotions p
                LEFT JOIN entities ep ON p.placeholder_entity_id = ep.id
                JOIN entities er ON p.resolved_entity_id = er.id
                WHERE COALESCE(p.status, 'candidate') IN ('accepted', 'probable')
            """)
            predictions["identity_promotions"] = {
                (_norm(placeholder), _norm(resolved))
                for placeholder, resolved in cursor.fetchall()
            }

        if "mention_occurrences" in tables:
            cursor.execute("SELECT chapter, surface_form, entity_type_guess FROM mention_occurrences")
            predictions["mentions"] = {
                (int(chapter), _norm(surface_form), _norm(entity_type_guess))
                for chapter, surface_form, entity_type_guess in cursor.fetchall()
            }

        if {"event_clusters", "event_cluster_members", "events"}.issubset(tables):
            cursor.execute("""
                SELECT ec.cluster_key, ev.chapter, ev.summary
                FROM event_cluster_members ecm
                JOIN event_clusters ec ON ecm.cluster_id = ec.id
                JOIN events ev ON ecm.event_id = ev.id
            """)
            predictions["event_clusters"] = {
                (_norm(cluster_key), int(chapter), _norm(summary))
                for cluster_key, chapter, summary in cursor.fetchall()
            }

        if "conflict_records" in tables:
            cursor.execute("""
                SELECT chapter, conflict_type, payload, status, COALESCE(severity, 6)
                FROM conflict_records
            """)
            for chapter, conflict_type, payload, status, severity in cursor.fetchall():
                predictions["conflict_records"].add((_norm(conflict_type), _norm(status)))
                predictions["conflict_priorities"].add((_norm(conflict_type), int(severity or 6)))
                if conflict_type != "alias_collision":
                    if conflict_type == "merge_conflict":
                        try:
                            decoded = json.loads(payload) if payload else {}
                        except json.JSONDecodeError:
                            decoded = {}
                        reason = _norm(decoded.get("reason", ""))
                        if "ontology" in reason or "reference entity" in reason or "location cannot merge" in reason:
                            predictions["ontology_compatibility_failures"].add((
                                int(chapter or 0),
                                int(decoded.get("entity_a_id") or 0),
                                int(decoded.get("entity_b_id") or 0),
                                reason,
                            ))
                    continue
                try:
                    decoded = json.loads(payload) if payload else {}
                except json.JSONDecodeError:
                    decoded = {}
                predictions["alias_conflicts"].add((int(chapter or 0), _norm(decoded.get("alias", ""))))

        if "merge_candidates" in tables:
            cursor.execute("SELECT entity_a_id, entity_b_id, votes FROM merge_candidates")
            predictions["merge_candidates"] = {
                (int(entity_a_id), int(entity_b_id), int(votes or 0))
                for entity_a_id, entity_b_id, votes in cursor.fetchall()
            }

        if "identity_resolution_evidence" in tables:
            cursor.execute("""
                SELECT state, COUNT(*)
                FROM identity_resolution_evidence
                GROUP BY state
            """)
            predictions["identity_resolution_states"] = {
                _norm(state): int(count)
                for state, count in cursor.fetchall()
            }

        if "unresolved_mentions" in tables:
            cursor.execute("""
                SELECT chapter, mention_key, entity_type, COALESCE(ambiguous, 1)
                FROM unresolved_mentions
            """)
            predictions["unresolved_mentions"] = {
                (int(chapter), _norm(mention_key), _norm(entity_type), int(ambiguous or 0))
                for chapter, mention_key, entity_type, ambiguous in cursor.fetchall()
            }

        if "reference_mentions" in tables:
            cursor.execute("""
                SELECT chapter, normalized_form, reference_subtype, promotion_state
                FROM reference_mentions
            """)
            predictions["reference_mentions"] = {
                (int(chapter), _norm(normalized_form), _norm(reference_subtype), _norm(promotion_state))
                for chapter, normalized_form, reference_subtype, promotion_state in cursor.fetchall()
            }

        if "name_semantic_relations" in tables:
            cursor.execute("""
                SELECT chapter, relation_type, source_normalized, target_normalized, reference_subtype, status
                FROM name_semantic_relations
            """)
            predictions["name_semantic_relations"] = {
                (
                    int(chapter or 0),
                    _norm(relation_type),
                    _norm(source_normalized),
                    _norm(target_normalized),
                    _norm(reference_subtype),
                    _norm(status),
                )
                for chapter, relation_type, source_normalized, target_normalized, reference_subtype, status in cursor.fetchall()
            }

        if {"entity_ontology_evidence", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, ev.ontology_field, ev.new_value,
                       ev.ontology_source, ev.chapter
                FROM entity_ontology_evidence ev
                JOIN entities e ON ev.entity_id = e.id
            """)
            predictions["entity_ontology_evidence"] = {
                (
                    _norm(canonical_name),
                    _norm(ontology_field),
                    _norm(new_value),
                    _norm(ontology_source),
                    int(chapter or 0),
                )
                for canonical_name, ontology_field, new_value, ontology_source, chapter in cursor.fetchall()
            }

        if {"entity_state_history", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, sh.state_field, sh.old_state,
                       sh.new_state, sh.chapter, sh.source
                FROM entity_state_history sh
                JOIN entities e ON sh.entity_id = e.id
            """)
            predictions["entity_state_history"] = {
                (
                    _norm(canonical_name),
                    _norm(state_field),
                    _norm(old_state),
                    _norm(new_state),
                    int(chapter or 0),
                    _norm(source),
                )
                for canonical_name, state_field, old_state, new_state, chapter, source in cursor.fetchall()
            }

        if "entity_semantic_relations" in tables:
            cursor.execute("""
                SELECT chapter, relation_type, source_surface,
                       target_surface, ontology_source, status
                FROM entity_semantic_relations
            """)
            predictions["entity_semantic_relations"] = {
                (
                    int(chapter or 0),
                    _norm(relation_type),
                    _norm(source_surface),
                    _norm(target_surface),
                    _norm(ontology_source),
                    _norm(status),
                )
                for chapter, relation_type, source_surface, target_surface, ontology_source, status in cursor.fetchall()
            }

        if "language_observations" in tables:
            cursor.execute("""
                SELECT first_seen, normalized_text, language, writing_system,
                       translation_status, decoder_source, resolved_chapter
                FROM language_observations
            """)
            predictions["language_observations"] = {
                (
                    int(first_seen or 0),
                    _norm(normalized_text),
                    _norm(language),
                    _norm(writing_system),
                    _norm(translation_status),
                    _norm(decoder_source),
                    int(resolved_chapter or 0),
                )
                for first_seen, normalized_text, language, writing_system, translation_status, decoder_source, resolved_chapter in cursor.fetchall()
            }

        if {"life_status_evidence", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, lse.chapter, lse.actual_status,
                       lse.belief_status, lse.appearance_status,
                       lse.belief_owner_type, lse.reader_visible,
                       lse.participation_type, lse.observation_type,
                       lse.status_reason, lse.identity_continuity_mode
                FROM life_status_evidence lse
                JOIN entities e ON lse.entity_id = e.id
            """)
            predictions["life_status_evidence"] = {
                (
                    _norm(canonical_name),
                    int(chapter or 0),
                    _norm(actual_status),
                    _norm(belief_status),
                    _norm(appearance_status),
                    _norm(belief_owner_type),
                    bool(reader_visible),
                    _norm(participation_type),
                    _norm(observation_type),
                    _norm(status_reason),
                    _norm(identity_continuity_mode),
                )
                for (
                    canonical_name, chapter, actual_status, belief_status,
                    appearance_status, belief_owner_type, reader_visible,
                    participation_type, observation_type, status_reason,
                    identity_continuity_mode
                ) in cursor.fetchall()
            }

        if {"life_status_snapshots", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, scope_type, actual_status,
                       belief_status, appearance_status, confidence,
                       evidence_count
                FROM life_status_snapshots s
                JOIN entities e ON s.entity_id = e.id
            """)
            predictions["life_status_snapshots"] = {
                (
                    _norm(canonical_name),
                    _norm(scope_type),
                    _norm(actual_status),
                    _norm(belief_status),
                    _norm(appearance_status),
                    round(float(confidence or 0), 4),
                    int(evidence_count or 0),
                )
                for canonical_name, scope_type, actual_status, belief_status, appearance_status, confidence, evidence_count in cursor.fetchall()
            }

        if {"life_status_timeline_segments", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, start_chapter, end_chapter,
                       actual_status, belief_status, appearance_status,
                       confidence
                FROM life_status_timeline_segments seg
                JOIN entities e ON seg.entity_id = e.id
            """)
            predictions["life_status_timeline_segments"] = {
                (
                    _norm(canonical_name),
                    int(start_chapter or 0),
                    int(end_chapter or 0),
                    _norm(actual_status),
                    _norm(belief_status),
                    _norm(appearance_status),
                    round(float(confidence or 0), 4),
                )
                for canonical_name, start_chapter, end_chapter, actual_status, belief_status, appearance_status, confidence in cursor.fetchall()
            }

        if {"entity_legacy_signals", "entities"}.issubset(tables):
            cursor.execute("""
                SELECT e.canonical_name, els.chapter, els.signal_type,
                       els.historical_importance, els.emotional_importance,
                       els.political_importance, els.familial_importance,
                       els.memory_strength
                FROM entity_legacy_signals els
                JOIN entities e ON els.entity_id = e.id
            """)
            predictions["legacy_signals"] = {
                (
                    _norm(canonical_name),
                    int(chapter or 0),
                    _norm(signal_type),
                    round(float(historical or 0), 4),
                    round(float(emotional or 0), 4),
                    round(float(political or 0), 4),
                    round(float(familial or 0), 4),
                    round(float(memory or 0), 4),
                )
                for canonical_name, chapter, signal_type, historical, emotional, political, familial, memory in cursor.fetchall()
            }

        if "relationship_communities" in tables:
            cursor.execute("""
                SELECT community_key, member_count, edge_count, density, cohesion_score, bridge_count
                FROM relationship_communities
            """)
            predictions["communities"] = {
                (
                    _norm(community_key),
                    int(member_count or 0),
                    int(edge_count or 0),
                    round(float(density or 0), 4),
                    round(float(cohesion_score or 0), 4),
                    int(bridge_count or 0),
                )
                for community_key, member_count, edge_count, density, cohesion_score, bridge_count in cursor.fetchall()
            }

        if "entity_social_metrics" in tables:
            cursor.execute("""
                SELECT COUNT(*), COALESCE(SUM(social_degree), 0),
                       COALESCE(SUM(bridge_score), 0),
                       COALESCE(AVG(local_density), 0.0),
                       COALESCE(AVG(cluster_strength), 0.0)
                FROM entity_social_metrics
            """)
            count, social_degree_sum, bridge_score_sum, avg_density, avg_cluster_strength = cursor.fetchone()
            predictions["social_metrics"] = {
                "entity_metric_count": int(count or 0),
                "social_degree_sum": int(social_degree_sum or 0),
                "bridge_score_sum": round(float(bridge_score_sum or 0), 4),
                "avg_local_density": round(float(avg_density or 0), 4),
                "avg_cluster_strength": round(float(avg_cluster_strength or 0), 4),
            }

        return predictions
    finally:
        conn.close()


def _fragmentation_metrics(surface_owners: dict, expected_aliases: set) -> dict:
    expected_by_identity = {}
    for canonical_name, alias_name in expected_aliases:
        expected_by_identity.setdefault(canonical_name, {canonical_name}).add(alias_name)

    checked = 0
    fragmented = 0
    for forms in expected_by_identity.values():
        owners = {surface_owners[form] for form in forms if form in surface_owners}
        if len(owners) > 0:
            checked += 1
        if len(owners) > 1:
            fragmented += 1

    rate = fragmented / checked if checked else 0.0
    return {
        "identities_checked": checked,
        "fragmented_identities": fragmented,
        "fragmentation_rate": round(rate, 4),
    }


def _conflict_resolution_metrics(conflict_records: set) -> dict:
    total = len(conflict_records)
    resolved = sum(1 for _conflict_type, status in conflict_records if status in {"resolved", "accepted", "rejected"})
    return {
        "total_conflict_types": total,
        "resolved_conflict_types": resolved,
        "success_rate": round(resolved / total, 4) if total else 1.0,
    }


def evaluate(db_dir: str, truth_path: str) -> dict:
    chapters = _load_chapter_cache(db_dir)
    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    predicted_aliases = set()
    predicted_entities = set()
    predicted_relationships = set()
    predicted_events = set()

    for chapter_idx, data in enumerate(chapters):
        for alias in data.get("new_aliases_discovered", []):
            predicted_aliases.add((_norm(alias.get("canonical_name", "")), _norm(alias.get("new_alias", ""))))
        for entity in data.get("entities_present", []):
            predicted_entities.add((_norm(entity.get("name", "")), _norm(entity.get("entity_type", ""))))
        for rel in data.get("relationships", []):
            pair = tuple(sorted((_norm(rel.get("source", "")), _norm(rel.get("target", "")))))
            predicted_relationships.add(pair)
        for event in data.get("major_events", []):
            summary = event.get("summary", event.get("event", "")) if isinstance(event, dict) else event
            predicted_events.add((chapter_idx, _norm(summary)))

    expected_aliases = {
        (_norm(item.get("canonical_name", "")), _norm(item.get("alias", item.get("new_alias", ""))))
        for item in truth.get("aliases", [])
    }
    expected_entities = {
        (_norm(item.get("name", "")), _norm(item.get("entity_type", "")))
        for item in truth.get("entities", [])
    }
    expected_relationships = {
        tuple(sorted((_norm(item.get("source", "")), _norm(item.get("target", "")))))
        for item in truth.get("relationships", [])
    }
    expected_events = {
        (int(item.get("chapter", 0)), _norm(item.get("event", "")))
        for item in truth.get("major_events", [])
    }
    expected_title_links = {
        (_norm(item.get("canonical_name", "")), _norm(item.get("title", item.get("title_text", ""))))
        for item in truth.get("title_links", [])
    }
    expected_identity_promotions = {
        (_norm(item.get("placeholder", "[UNNAMED_POV]")), _norm(item.get("resolved", item.get("canonical_name", ""))))
        for item in truth.get("identity_promotions", truth.get("narrator_promotions", []))
    }
    expected_mentions = {
        (int(item.get("chapter", 0)), _norm(item.get("surface_form", "")), _norm(item.get("entity_type_guess", "")))
        for item in truth.get("mention_occurrences", truth.get("mentions", []))
    }
    expected_event_clusters = {
        (_norm(item.get("cluster_key", "")), int(item.get("chapter", 0)), _norm(item.get("event", item.get("summary", ""))))
        for item in truth.get("event_clusters", [])
    }
    expected_landmarks = {
        (
            _norm(item.get("name", item.get("landmark_name", ""))),
            _norm(item.get("landmark_type", "event")),
            _norm(item.get("event_state", "unknown")),
            _norm(item.get("event_reliability", "unknown")),
        )
        for item in truth.get("landmarks", [])
    }
    expected_landmark_names = {
        (
            _norm(item.get("name", "")),
            _norm(item.get("name_role", "public")),
            _norm(item.get("name_source_type", "unknown")),
            _norm(item.get("audience_type", "reader")),
            _norm(item.get("framing_polarity", "neutral")),
            _norm(item.get("literal_status", "literal")),
        )
        for item in truth.get("landmark_names", [])
    }
    expected_landmark_occurrences = {
        (int(item.get("chapter", 0)), _norm(item.get("landmark_name", item.get("name", ""))), _norm(item.get("link_type", "occurrence")))
        for item in truth.get("landmark_occurrences", [])
    }
    expected_entity_ontology = {
        (
            _norm(item.get("name", "")),
            _norm(item.get("entity_category", "")),
            _norm(item.get("species_or_kind", "")),
            _norm(item.get("sentience", "")),
            _norm(item.get("active_status", "")),
            _norm(item.get("identity_status", "")),
            _norm(item.get("entity_persistence", "")),
            _norm(item.get("interpretation_status", "")),
        )
        for item in truth.get("entity_ontology", [])
    }
    expected_entity_semantic_relations = {
        (
            int(item.get("chapter", 0)),
            _norm(item.get("relation_type", "")),
            _norm(item.get("source", item.get("source_surface", ""))),
            _norm(item.get("target", item.get("target_surface", ""))),
            _norm(item.get("ontology_source", "llm")),
            _norm(item.get("status", "observed")),
        )
        for item in truth.get("entity_semantic_relations", [])
    }
    expected_language_observations = {
        (
            int(item.get("chapter", item.get("first_seen", 0))),
            _norm(item.get("surface_text", item.get("normalized_text", ""))),
            _norm(item.get("language", "")),
            _norm(item.get("writing_system", "")),
            _norm(item.get("translation_status", "")),
            _norm(item.get("decoder_source", "")),
            int(item.get("resolved_chapter", 0) or 0),
        )
        for item in truth.get("language_observations", [])
    }
    expected_life_status_evidence = {
        (
            _norm(item.get("subject", item.get("canonical_name", ""))),
            int(item.get("chapter", 0)),
            _norm(item.get("actual_status", "unknown")),
            _norm(item.get("belief_status", "unknown")),
            _norm(item.get("appearance_status", "unknown")),
            _norm(item.get("belief_owner_type", "unknown")),
            bool(item.get("reader_visible", True)),
            _norm(item.get("participation_type", "active_scene")),
            _norm(item.get("observation_type", "direct")),
            _norm(item.get("status_reason", "unknown")),
            _norm(item.get("identity_continuity_mode", "unknown")),
        )
        for item in truth.get("life_status_events", truth.get("life_status_evidence", []))
    }
    expected_legacy_signals = {
        (
            _norm(item.get("subject", item.get("canonical_name", ""))),
            int(item.get("chapter", 0)),
            _norm(item.get("signal_type", "legacy")),
            round(float(item.get("historical_importance", 0) or 0), 4),
            round(float(item.get("emotional_importance", 0) or 0), 4),
            round(float(item.get("political_importance", 0) or 0), 4),
            round(float(item.get("familial_importance", 0) or 0), 4),
            round(float(item.get("memory_strength", 0) or 0), 4),
        )
        for item in truth.get("legacy_signals", [])
    }

    spoiler_leakage_count = sum(
        1 for leak in truth.get("spoiler_leaks", [])
        if _norm(leak.get("text", "")) in {event for _chapter, event in predicted_events}
    )

    result = {
        "alias": _f1(predicted_aliases, expected_aliases),
        "entity": _f1(predicted_entities, expected_entities),
        "relationship_pair": _f1(predicted_relationships, expected_relationships),
        "major_event": _f1(predicted_events, expected_events),
        "spoiler_leakage_count": spoiler_leakage_count,
        "chapters_evaluated": len(chapters),
    }
    graph_predictions = _load_graph_predictions(db_dir)
    if graph_predictions:
        result["graph_alias"] = _f1(graph_predictions["aliases"], expected_aliases)
        result["graph_entity"] = _f1(graph_predictions["entities"], expected_entities)
        result["graph_relationship_pair"] = _f1(graph_predictions["relationships"], expected_relationships)
        result["graph_social_relationship_count"] = len(graph_predictions["social_relationships"])
        result["graph_community_count"] = len(graph_predictions["communities"])
        result["graph_social_metrics"] = graph_predictions["social_metrics"]
        result["graph_event"] = _f1(graph_predictions["events"], expected_events)
        result["graph_title_link"] = _f1(graph_predictions["title_links"], expected_title_links)
        result["graph_identity_promotion"] = _f1(graph_predictions["identity_promotions"], expected_identity_promotions)
        result["graph_mention_provenance"] = _f1(graph_predictions["mentions"], expected_mentions)
        result["graph_event_cluster"] = _f1(graph_predictions["event_clusters"], expected_event_clusters)
        result["graph_landmark"] = _f1(graph_predictions["landmarks"], expected_landmarks)
        result["graph_landmark_name"] = _f1(graph_predictions["landmark_names"], expected_landmark_names)
        result["graph_landmark_occurrence"] = _f1(graph_predictions["landmark_occurrences"], expected_landmark_occurrences)
        result["landmark_resolution_counts"] = dict(graph_predictions["landmark_resolution"])
        result["graph_entity_ontology"] = _f1(graph_predictions["entity_ontology"], expected_entity_ontology)
        result["graph_entity_semantic_relation"] = _f1(
            graph_predictions["entity_semantic_relations"],
            expected_entity_semantic_relations,
        )
        result["graph_language_observation"] = _f1(
            graph_predictions["language_observations"],
            expected_language_observations,
        )
        result["graph_life_status_evidence"] = _f1(
            graph_predictions["life_status_evidence"],
            expected_life_status_evidence,
        )
        result["graph_legacy_signal"] = _f1(
            graph_predictions["legacy_signals"],
            expected_legacy_signals,
        )
        result["graph_life_status_snapshot_count"] = len(graph_predictions["life_status_snapshots"])
        result["graph_life_status_timeline_count"] = len(graph_predictions["life_status_timeline_segments"])
        result["graph_entity_ontology_evidence_count"] = len(graph_predictions["entity_ontology_evidence"])
        result["graph_entity_state_history_count"] = len(graph_predictions["entity_state_history"])
        result["graph_ontology_compatibility_failure_count"] = len(graph_predictions["ontology_compatibility_failures"])
        result["graph_alias_conflict_count"] = len(graph_predictions["alias_conflicts"])
        result["fragmentation"] = _fragmentation_metrics(graph_predictions["surface_owners"], expected_aliases)
        result["alias_promotion_precision"] = result["graph_alias"]["precision"]
        result["title_link_precision"] = result["graph_title_link"]["precision"]
        result["narrator_promotion_success"] = result["graph_identity_promotion"]["recall"]
        result["merge_quality"] = {
            "open_merge_candidates": len(graph_predictions["merge_candidates"]),
            "backlog_per_entity": round(
                len(graph_predictions["merge_candidates"]) / max(1, len(graph_predictions["entities"])),
                4,
            ),
        }
        result["identity_resolution_states"] = graph_predictions["identity_resolution_states"]
        result["name_semantic_relation_count"] = len(graph_predictions["name_semantic_relations"])
        result["conflict_resolution_success"] = _conflict_resolution_metrics(graph_predictions["conflict_records"])
        result["graph_spoiler_leakage_count"] = sum(
            1 for leak in truth.get("spoiler_leaks", [])
            if _norm(leak.get("text", "")) in graph_predictions["spoiler_events"]
        )

    return result


def main():
    if len(sys.argv) != 3:
        print("Usage: python evaluation_runner.py <db_dir> <truth.json>")
        sys.exit(1)

    result = evaluate(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
