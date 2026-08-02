"""Versioned chapter evidence, reader snapshots, and deterministic graph replay.

The graph remains the resolver workspace.  This module keeps the durable
boundary around it: immutable extraction evidence in, reader-safe snapshots
out, and checkpoints that make derived-state rebuilds explicit.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from config import (
    BOOKBUDDY_VERSION,
    CACHE_VERSION,
    GEMINI_MODEL_NAME,
    GRAPH_SCHEMA_VERSION,
    IMAGE_EVIDENCE_SCHEMA_VERSION,
    NORMALIZATION_VERSION,
    PROMPT_VERSION,
    REPLAY_VERSION,
    RESOLVER_DEPENDENCIES,
    RESOLVER_VERSIONS,
    SNAPSHOT_CONTRACT_VERSION,
)
from db_manager import BookDatabase


_RETENTION_TABLES = (
    "reader_snapshot_current",
    "chapter_processing_checkpoints",
    "reader_snapshot_revisions",
    "chapter_evidence_revisions",
    "image_evidence_revisions",
    "image_occurrence_provenance",
    "chapter_invalidations",
    "resolver_decisions",
    "image_parse_cache",
)
_CACHE_FILE_RE = re.compile(r"^chapter_(\d+)\.json$", re.IGNORECASE)
_EPHEMERAL_EVIDENCE_KEYS = {"_cache_status", "_merge_stats"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_hash(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_evidence_payload(payload: dict) -> dict:
    cleaned = copy.deepcopy(payload or {})
    for key in _EPHEMERAL_EVIDENCE_KEYS:
        cleaned.pop(key, None)
    return cleaned


def resolver_manifest() -> dict[str, str]:
    """Return the full derived-state manifest persisted with checkpoints."""
    manifest = {
        "prompt": PROMPT_VERSION,
        "cache": str(CACHE_VERSION),
        "graph_schema": str(GRAPH_SCHEMA_VERSION),
        "normalization": str(NORMALIZATION_VERSION),
        "snapshot_contract": SNAPSHOT_CONTRACT_VERSION,
        "replay": REPLAY_VERSION,
    }
    manifest.update({f"resolver:{key}": value for key, value in RESOLVER_VERSIONS.items()})
    return dict(sorted(manifest.items()))


def _affected_resolvers(changed: set[str]) -> list[str]:
    """Return changed resolvers plus their declared downstream closure."""
    reverse: dict[str, set[str]] = {}
    for resolver, upstream in RESOLVER_DEPENDENCIES.items():
        for dependency in upstream:
            reverse.setdefault(dependency, set()).add(resolver)
    affected = set(changed)
    pending = list(changed)
    while pending:
        current = pending.pop()
        for dependent in reverse.get(current, set()):
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)
    return sorted(affected)


def _changed_resolvers(previous: dict | None, current: dict | None = None) -> list[str]:
    previous = previous or {}
    current = current or resolver_manifest()
    changed_keys = {key for key in set(previous) | set(current) if previous.get(key) != current.get(key)}
    resolver_changes = {key.split(":", 1)[1] for key in changed_keys if key.startswith("resolver:")}
    # Older checkpoints store only resolver names. A non-resolver contract
    # change invalidates every resolver-derived snapshot deterministically.
    resolver_changes.update(key for key in changed_keys if key in RESOLVER_VERSIONS)
    if changed_keys - {f"resolver:{name}" for name in RESOLVER_VERSIONS} - set(RESOLVER_VERSIONS):
        resolver_changes.update(RESOLVER_VERSIONS)
    return _affected_resolvers(resolver_changes)


def _as_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


class EvidenceStore:
    """Append-only chapter extraction evidence backed by the session graph DB."""

    @staticmethod
    def record(
        db: BookDatabase,
        chapter: int,
        payload: dict,
        *,
        trigger_reason: str,
        source_metadata: dict | None = None,
        source_hash: str | None = None,
        activate: bool = True,
        preserve_existing_active: bool = False,
    ) -> dict:
        cleaned = _clean_evidence_payload(payload)
        payload_json = _canonical_json(cleaned)
        payload_hash = _stable_hash(cleaned)
        metadata = dict(source_metadata or {})
        metadata.setdefault("version_manifest", resolver_manifest())
        metadata_json = _canonical_json(metadata)
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, revision, payload_hash, payload_json
            FROM chapter_evidence_revisions
            WHERE chapter = ? AND is_active = 1
            """,
            (int(chapter),),
        )
        active = cursor.fetchone()
        if active and active[2] == payload_hash:
            if (
                cleaned.get("image_evidence_schema_version") == IMAGE_EVIDENCE_SCHEMA_VERSION
                and isinstance(cleaned.get("image_evidence"), list)
            ):
                db.persist_image_evidence(
                    int(active[0]), int(chapter), cleaned["image_evidence"], conn=conn
                )
                conn.commit()
            return {
                "id": int(active[0]),
                "chapter": int(chapter),
                "revision": int(active[1]),
                "payload_hash": payload_hash,
                "changed": False,
                "active": True,
            }
        if active and preserve_existing_active:
            return {
                "id": int(active[0]),
                "chapter": int(chapter),
                "revision": int(active[1]),
                "payload_hash": active[2],
                "changed": False,
                "active": True,
                "preserved_existing": True,
            }

        cursor.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM chapter_evidence_revisions WHERE chapter = ?",
            (int(chapter),),
        )
        next_revision = int(cursor.fetchone()[0] or 0) + 1
        if activate:
            cursor.execute(
                "UPDATE chapter_evidence_revisions SET is_active = 0 WHERE chapter = ? AND is_active = 1",
                (int(chapter),),
            )
        cursor.execute(
            """
            INSERT INTO chapter_evidence_revisions (
                chapter, revision, payload_json, payload_hash, source_hash,
                trigger_reason, source_metadata_json, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(chapter),
                next_revision,
                payload_json,
                payload_hash,
                source_hash or "",
                trigger_reason or "manual_rebuild",
                metadata_json,
                1 if activate else 0,
            ),
        )
        evidence_id = int(cursor.lastrowid)
        if active and activate:
            cursor.execute(
                """
                INSERT INTO chapter_invalidations (from_chapter, reason, details_json)
                VALUES (?, ?, ?)
                """,
                (
                    int(chapter),
                    trigger_reason or "evidence_changed",
                    _canonical_json(
                        {
                            "previous_evidence_revision": int(active[1]),
                            "current_evidence_revision": next_revision,
                            "previous_payload_hash": active[2],
                            "current_payload_hash": payload_hash,
                        }
                    ),
                ),
            )
        if (
            activate
            and cleaned.get("image_evidence_schema_version") == IMAGE_EVIDENCE_SCHEMA_VERSION
            and isinstance(cleaned.get("image_evidence"), list)
        ):
            db.persist_image_evidence(
                evidence_id, int(chapter), cleaned["image_evidence"], conn=conn
            )
        conn.commit()
        return {
            "id": evidence_id,
            "chapter": int(chapter),
            "revision": next_revision,
            "payload_hash": payload_hash,
            "changed": True,
            "active": bool(activate),
        }

    @staticmethod
    def import_legacy_caches(db: BookDatabase, db_dir: str) -> list[dict]:
        imported = []
        cache_root = Path(db_dir)
        if not cache_root.is_dir():
            return imported
        for path in sorted(cache_root.iterdir(), key=lambda item: item.name):
            match = _CACHE_FILE_RE.match(path.name)
            if not match or not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            chapter = int(match.group(1))
            imported.append(
                EvidenceStore.record(
                    db,
                    chapter,
                    payload,
                    trigger_reason="legacy_import",
                    source_metadata={"cache_file": path.name, "import_mode": "immutable_legacy"},
                    source_hash=_file_hash(str(path)),
                    preserve_existing_active=True,
                )
            )
        return imported

    @staticmethod
    def active_records(db: BookDatabase) -> list[dict]:
        cursor = db._get_connection().cursor()
        cursor.execute(
            """
            SELECT id, chapter, revision, payload_json, payload_hash,
                   trigger_reason, source_metadata_json
            FROM chapter_evidence_revisions
            WHERE is_active = 1
            ORDER BY chapter, revision
            """
        )
        records = []
        for row in cursor.fetchall():
            records.append(
                {
                    "id": int(row[0]),
                    "chapter": int(row[1]),
                    "revision": int(row[2]),
                    "payload": _as_json(row[3], {}),
                    "payload_hash": row[4],
                    "trigger_reason": row[5],
                    "source_metadata": _as_json(row[6], {}),
                }
            )
        return records

    @staticmethod
    def active_payload(db: BookDatabase, chapter: int) -> dict | None:
        cursor = db._get_connection().cursor()
        cursor.execute(
            """
            SELECT payload_json FROM chapter_evidence_revisions
            WHERE chapter = ? AND is_active = 1
            """,
            (int(chapter),),
        )
        row = cursor.fetchone()
        return _as_json(row[0], {}) if row else None


class ReaderSnapshotBuilder:
    """Build a reader-safe, as-of-chapter view from the derived graph."""

    def __init__(self, db: BookDatabase):
        self.db = db

    def build(self, chapter: int) -> dict:
        chapter = int(chapter)
        return {
            "contract_version": SNAPSHOT_CONTRACT_VERSION,
            "chapter": chapter,
            "reader_contract": {
                "scope": "reader",
                "as_of_chapter": chapter,
                "knowledge_states": ["known", "believed", "disputed", "unknown"],
                "engine_truth_included": False,
            },
            "analysis_status": {"state": "complete", "as_of_chapter": chapter},
            "visible_entities": self._visible_entities(chapter),
            "visible_relationships": self._visible_relationships(chapter),
            "life_status": self._life_status(chapter),
            "landmarks": self._landmarks(chapter),
            "unresolved_mentions": self._unresolved_mentions(chapter),
            "reference_mentions": self._reference_mentions(chapter),
            "language_observations": self._language_observations(chapter),
            "translator_dictionary_status": self._translator_status(chapter),
            "ontology_changes": self._ontology_changes(chapter),
            "legacy_signals": self._legacy_signals(chapter),
            "timeline_changes": self._timeline_changes(chapter),
            "explanation_references": self._reader_explanation_references(chapter),
            "explanations": {
                "scope": "reader",
                "visibility_policy": "strict_as_of_chapter",
                "raw_engine_evidence_included": False,
            },
        }

    def _rows(self, statement: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        conn = self.db._get_connection()
        previous_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(statement, parameters).fetchall()
        finally:
            conn.row_factory = previous_factory

    def _visible_entities(self, chapter: int) -> list[dict]:
        entities = self._rows(
            """
            SELECT id, canonical_name, entity_type, first_seen_chapter,
                   COALESCE(inherited_confidence, 1.0) AS inherited_confidence, source_session
            FROM entities
            WHERE COALESCE(first_seen_chapter, 0) <= ?
            ORDER BY entity_type, lower(canonical_name), canonical_name
            """,
            (chapter,),
        )
        evidence_rows = self._rows(
            """
            SELECT entity_id, ontology_field, new_value
            FROM entity_ontology_evidence
            WHERE chapter IS NOT NULL AND chapter <= ?
            ORDER BY entity_id, chapter, id
            """,
            (chapter,),
        )
        states: dict[int, dict[str, object]] = {
            int(row["id"]): {
                "entity_category": "UNKNOWN",
                "species_or_kind": "unknown",
                "sentience": "unknown",
                "narrative_role": "unknown",
                "active_status": "uncertain",
                "identity_status": "unknown",
                "entity_persistence": "persistent",
                "literal_status": "literal",
                "interpretation_status": "actual",
                "language_status": "natural_language",
                "translation_status": "not_applicable",
            }
            for row in entities
        }
        for row in evidence_rows:
            entity_state = states.get(int(row["entity_id"]))
            if entity_state is not None and row["ontology_field"] in entity_state:
                entity_state[row["ontology_field"]] = row["new_value"]

        visible = []
        for row in entities:
            ontology = states[int(row["id"])]
            if str(ontology["active_status"] or "").lower() in {"referenced_only", "reference_only"}:
                continue
            visible.append(
                {
                    "id": int(row["id"]),
                    "name": row["canonical_name"],
                    "canonical_name": row["canonical_name"],
                    "entity_type": row["entity_type"],
                    "ontology": {
                        "category": ontology["entity_category"],
                        "kind": ontology["species_or_kind"],
                        "sentience": ontology["sentience"],
                        "narrative_role": ontology["narrative_role"],
                        "active_status": ontology["active_status"],
                        "identity_status": ontology["identity_status"],
                        "persistence": ontology["entity_persistence"],
                        "literal_status": ontology["literal_status"],
                        "interpretation_status": ontology["interpretation_status"],
                    },
                    "language_status": ontology["language_status"],
                    "translation_status": ontology["translation_status"],
                    "first_seen_chapter": row["first_seen_chapter"],
                    "provenance": self._provenance(row),
                }
            )
        return visible

    def _visible_relationships(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT rh.rel_key, source.id AS source_id, target.id AS target_id,
                   source.canonical_name AS source_name,
                   target.canonical_name AS target_name, rh.chapter,
                   rh.interaction_order, rh.trust_score, rh.hostility_score,
                   rh.respect_score, rh.fear_score, rh.evidence_source_type,
                   rh.scene_scope, COALESCE(rh.inherited_confidence, 1.0) AS inherited_confidence,
                   rh.source_session
            FROM relationship_history rh
            JOIN relationships relation ON relation.rel_key = rh.rel_key
            JOIN entities source ON source.id = relation.source_id
            JOIN entities target ON target.id = relation.target_id
            WHERE rh.chapter <= ?
            ORDER BY rh.rel_key, rh.chapter, rh.interaction_order, rh.id
            """,
            (chapter,),
        )
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            latest[row["rel_key"]] = row
        return [
            {
                "relationship_key": row["rel_key"],
                "source_id": int(row["source_id"]),
                "target_id": int(row["target_id"]),
                "source": row["source_name"],
                "target": row["target_name"],
                "trust_score": row["trust_score"],
                "hostility_score": row["hostility_score"],
                "respect_score": row["respect_score"],
                "fear_score": row["fear_score"],
                "last_observed_chapter": row["chapter"],
                "evidence_source_type": row["evidence_source_type"],
                "scene_scope": row["scene_scope"],
                "provenance": self._provenance(row),
            }
            for _key, row in sorted(latest.items(), key=lambda item: (item[1]["source_name"], item[1]["target_name"]))
        ]

    def build_entity(self, entity_id: int, chapter: int) -> dict:
        """Build one aggregate reader object using the same strict chapter boundary."""
        entity_id = int(entity_id)
        chapter = int(chapter)
        snapshot = self.build(chapter)
        entity = next((item for item in snapshot["visible_entities"] if item["id"] == entity_id), None)
        if entity is None:
            raise LookupError("Reader-visible entity not found at this chapter")
        aliases = self._rows(
            """
            SELECT alias_name, first_seen, last_seen, status
            FROM aliases
            WHERE entity_id = ? AND COALESCE(first_seen, 0) <= ?
              AND COALESCE(status, 'active') != 'rejected'
            ORDER BY lower(alias_name), alias_name
            """,
            (entity_id, chapter),
        )
        events = self._rows(
            """
            SELECT event.id, event.chapter, event.summary, event.event_type,
                   participant.role, event.reader_known_since_chapter
            FROM event_participants participant
            JOIN events event ON event.id = participant.event_id
            WHERE participant.entity_id = ? AND event.chapter <= ?
              AND COALESCE(event.reader_known_since_chapter, event.chapter) <= ?
            ORDER BY event.chapter, event.event_order, event.id
            """,
            (entity_id, chapter, chapter),
        )
        importance_rows = self._rows(
            """
            SELECT historical_importance, emotional_importance, political_importance,
                   familial_importance, memory_strength
            FROM entity_legacy_signals
            WHERE entity_id = ? AND chapter <= ?
            ORDER BY chapter, id
            """,
            (entity_id, chapter),
        )
        importance = {
            "historical": max((float(row["historical_importance"] or 0) for row in importance_rows), default=0.0),
            "emotional": max((float(row["emotional_importance"] or 0) for row in importance_rows), default=0.0),
            "political": max((float(row["political_importance"] or 0) for row in importance_rows), default=0.0),
            "familial": max((float(row["familial_importance"] or 0) for row in importance_rows), default=0.0),
            "memory": max((float(row["memory_strength"] or 0) for row in importance_rows), default=0.0),
        }
        return {
            "contract_version": "reader_entity_v1",
            "as_of_chapter": chapter,
            "entity": entity,
            "aliases": [
                {"name": row["alias_name"], "first_seen_chapter": row["first_seen"], "last_seen_chapter": row["last_seen"], "status": row["status"]}
                for row in aliases
            ],
            "relationships": [
                item for item in snapshot["visible_relationships"]
                if entity_id in {item["source_id"], item["target_id"]}
            ],
            "events": [
                {"id": int(row["id"]), "chapter": int(row["chapter"]), "summary": row["summary"], "event_type": row["event_type"], "role": row["role"]}
                for row in events
            ],
            "status": next((item for item in snapshot["life_status"] if item.get("entity") == entity["canonical_name"]), {"reader_state": "unknown", "status": "unknown"}),
            "importance": importance,
            "portrait": {"status": "unavailable", "images": []},
            "dictionary": {"status": "unavailable"},
        }

    def _life_status(self, chapter: int) -> list[dict]:
        from life_status_resolver import LifeStatusResolver

        return LifeStatusResolver(self.db).reader_status_at(chapter)

    def _reader_explanation_references(self, chapter: int) -> list[dict]:
        references = []
        for decision in self.db.get_resolver_decisions(chapter=chapter):
            if decision["visibility"] != "reader":
                continue
            references.append(
                {
                    "decision_id": decision["id"],
                    "resolver": decision["resolver"],
                    "subject": decision["subject"],
                    "chapter": decision["chapter"],
                }
            )
        return references

    def _landmarks(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT lm.identity_key, lm.lifecycle, lm.landmark_type, lm.event_state,
                   lm.event_reliability, lm.reader_visibility, lm.geographic_scope,
                   lm.narrative_first_chapter, lm.reader_known_since_chapter,
                   lm.historical_start_text, lm.duration_text,
                   COALESCE(name.name_text, '') AS display_name,
                   COALESCE(lm.inherited_confidence, 1.0) AS inherited_confidence,
                   lm.source_session
            FROM event_landmarks lm
            LEFT JOIN landmark_names name ON name.id = lm.preferred_name_id
            WHERE COALESCE(lm.narrative_first_chapter, 0) <= ?
              AND COALESCE(lm.reader_known_since_chapter, 0) <= ?
              AND COALESCE(lm.reader_visibility, 'partially_known') != 'hidden'
            ORDER BY COALESCE(lm.reader_known_since_chapter, 0), lm.identity_key
            """,
            (chapter, chapter),
        )
        return [
            {
                "identity_key": row["identity_key"],
                "name": row["display_name"],
                "lifecycle": row["lifecycle"],
                "type": row["landmark_type"],
                "state": row["event_state"],
                "reliability": row["event_reliability"],
                "visibility": row["reader_visibility"],
                "geographic_scope": row["geographic_scope"],
                "reader_known_since_chapter": row["reader_known_since_chapter"],
                "historical_start": row["historical_start_text"],
                "duration": row["duration_text"],
                "provenance": self._provenance(row),
            }
            for row in rows
        ]

    def _unresolved_mentions(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT mention_text, mention_key, entity_type, chapter, confidence,
                   reason, mention_class, title_category
            FROM unresolved_mentions
            WHERE chapter <= ?
            ORDER BY chapter, mention_key, id
            """,
            (chapter,),
        )
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            latest[f"{row['entity_type']}::{row['mention_key']}"] = row
        return [
            {
                "surface": row["mention_text"],
                "entity_type": row["entity_type"],
                "first_unresolved_chapter": row["chapter"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "mention_class": row["mention_class"],
                "title_category": row["title_category"],
            }
            for _key, row in sorted(latest.items())
        ]

    def _reference_mentions(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT surface_form, normalized_form, chapter, entity_type_guess,
                   reference_subtype, participation_score, reference_score,
                   promotion_state, source_section_type
            FROM reference_mentions
            WHERE chapter <= ? AND COALESCE(promotion_state, 'reference') = 'reference'
            ORDER BY chapter, normalized_form, id
            """,
            (chapter,),
        )
        return [
            {
                "surface": row["surface_form"],
                "normalized": row["normalized_form"],
                "chapter": row["chapter"],
                "entity_type": row["entity_type_guess"],
                "reference_subtype": row["reference_subtype"],
                "participation_score": row["participation_score"],
                "reference_score": row["reference_score"],
                "source_section_type": row["source_section_type"],
            }
            for row in rows
        ]

    def _language_observations(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT normalized_text, language, writing_system, translation_status,
                   decoder_source, first_seen, confidence
            FROM language_observations
            WHERE COALESCE(first_seen, 0) <= ?
            ORDER BY first_seen, normalized_text
            """,
            (chapter,),
        )
        return [
            {
                "text": row["normalized_text"],
                "language": row["language"],
                "writing_system": row["writing_system"],
                "translation_status": row["translation_status"],
                "decoder_source": row["decoder_source"],
                "first_seen_chapter": row["first_seen"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    def _translator_status(self, chapter: int) -> dict:
        rows = self._rows(
            """
            SELECT translation_status, COUNT(*) AS observation_count
            FROM language_observations
            WHERE COALESCE(first_seen, 0) <= ?
            GROUP BY translation_status
            ORDER BY translation_status
            """,
            (chapter,),
        )
        return {
            "status_counts": {str(row["translation_status"] or "unknown"): int(row["observation_count"]) for row in rows},
            "dictionary_available": False,
        }

    def _ontology_changes(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT e.canonical_name, oe.ontology_field, oe.old_value, oe.new_value,
                   oe.confidence
            FROM entity_ontology_evidence oe
            JOIN entities e ON e.id = oe.entity_id
            WHERE oe.chapter = ?
            ORDER BY lower(e.canonical_name), oe.ontology_field, oe.id
            """,
            (chapter,),
        )
        return [
            {
                "entity": row["canonical_name"],
                "field": row["ontology_field"],
                "old_value": row["old_value"],
                "new_value": row["new_value"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    def _legacy_signals(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT e.canonical_name, ls.signal_type, ls.confidence,
                   ls.historical_importance, ls.emotional_importance,
                   ls.political_importance, ls.familial_importance, ls.memory_strength
            FROM entity_legacy_signals ls
            JOIN entities e ON e.id = ls.entity_id
            WHERE ls.chapter = ?
            ORDER BY lower(e.canonical_name), ls.signal_type, ls.id
            """,
            (chapter,),
        )
        return [
            {
                "entity": row["canonical_name"],
                "signal_type": row["signal_type"],
                "confidence": row["confidence"],
                "importance": {
                    "historical": row["historical_importance"],
                    "emotional": row["emotional_importance"],
                    "political": row["political_importance"],
                    "familial": row["familial_importance"],
                    "memory": row["memory_strength"],
                },
            }
            for row in rows
        ]

    def _timeline_changes(self, chapter: int) -> list[dict]:
        rows = self._rows(
            """
            SELECT summary, event_type, event_identity_key, story_time_text,
                   story_time_confidence, source_section_type
            FROM events
            WHERE chapter = ?
            ORDER BY event_order, id
            """,
            (chapter,),
        )
        return [
            {
                "summary": row["summary"],
                "event_type": row["event_type"],
                "identity_key": row["event_identity_key"],
                "story_time": row["story_time_text"],
                "story_time_confidence": row["story_time_confidence"],
                "source_section_type": row["source_section_type"],
            }
            for row in rows
        ]

    @staticmethod
    def _provenance(row: sqlite3.Row) -> dict:
        inherited_confidence = float(row["inherited_confidence"] or 1.0)
        return {
            "origin": "inherited" if inherited_confidence < 0.999 else "local",
            "source_session": row["source_session"],
        }


class SnapshotStore:
    """Persist only semantic snapshot changes while retaining version history."""

    @staticmethod
    def capture(
        db: BookDatabase,
        chapter: int,
        evidence: dict,
        *,
        trigger_reason: str,
        parent_graph_hash: str = "",
    ) -> dict:
        chapter = int(chapter)
        content = ReaderSnapshotBuilder(db).build(chapter)
        content_hash = _stable_hash(content)
        manifest = resolver_manifest()
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sr.id, sr.revision, sr.content_hash, sr.content_json,
                   sr.resolver_manifest_json
            FROM reader_snapshot_current current
            JOIN reader_snapshot_revisions sr ON sr.id = current.snapshot_revision_id
            WHERE current.chapter = ?
            """,
            (chapter,),
        )
        current = cursor.fetchone()
        previous_manifest = _as_json(current[4], {}) if current else {}
        changed_resolvers = _changed_resolvers(previous_manifest, manifest)
        if current and current[2] == content_hash:
            snapshot_id = int(current[0])
            revision = int(current[1])
            changed = False
            summary = {"changed": False, "affected": {"entities": [], "landmarks": [], "relationships": []}, "sections": {}}
        else:
            previous_content = _as_json(current[3], {}) if current else {}
            summary = SnapshotStore._change_summary(previous_content, content)
            cursor.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM reader_snapshot_revisions WHERE chapter = ?",
                (chapter,),
            )
            revision = int(cursor.fetchone()[0] or 0) + 1
            cursor.execute(
                """
                INSERT INTO reader_snapshot_revisions (
                    chapter, revision, contract_version, content_json, content_hash,
                    evidence_revision_id, trigger_reason, changed_resolvers_json,
                    resolver_manifest_json, version_metadata_json, change_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter,
                    revision,
                    SNAPSHOT_CONTRACT_VERSION,
                    _canonical_json(content),
                    content_hash,
                    evidence.get("id"),
                    trigger_reason or "manual_rebuild",
                    _canonical_json(changed_resolvers),
                    _canonical_json(manifest),
                    _canonical_json(SnapshotStore._version_metadata(parent_graph_hash)),
                    _canonical_json(summary),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO reader_snapshot_current (chapter, snapshot_revision_id, content_hash, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter) DO UPDATE SET
                    snapshot_revision_id = excluded.snapshot_revision_id,
                    content_hash = excluded.content_hash,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chapter, snapshot_id, content_hash),
            )
            changed = True

        cursor.execute(
            """
            INSERT INTO chapter_processing_checkpoints (
                chapter, evidence_revision_id, evidence_hash, resolver_manifest_json,
                resolver_manifest_hash, graph_schema_version, snapshot_revision_id,
                snapshot_hash, parent_graph_hash, state, error_text, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(chapter) DO UPDATE SET
                evidence_revision_id = excluded.evidence_revision_id,
                evidence_hash = excluded.evidence_hash,
                resolver_manifest_json = excluded.resolver_manifest_json,
                resolver_manifest_hash = excluded.resolver_manifest_hash,
                graph_schema_version = excluded.graph_schema_version,
                snapshot_revision_id = excluded.snapshot_revision_id,
                snapshot_hash = excluded.snapshot_hash,
                parent_graph_hash = excluded.parent_graph_hash,
                state = 'complete', error_text = NULL,
                completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            """,
            (
                chapter,
                evidence.get("id"),
                evidence.get("payload_hash", ""),
                _canonical_json(manifest),
                _stable_hash(manifest),
                GRAPH_SCHEMA_VERSION,
                snapshot_id,
                content_hash,
                parent_graph_hash or "",
            ),
        )
        conn.commit()
        return {
            "id": snapshot_id,
            "chapter": chapter,
            "revision": revision,
            "content_hash": content_hash,
            "changed": changed,
            "change_summary": summary,
        }

    @staticmethod
    def get(db: BookDatabase, chapter: int, revision: int | None = None) -> dict | None:
        cursor = db._get_connection().cursor()
        if revision is None:
            cursor.execute(
                """
                SELECT sr.id, sr.chapter, sr.revision, sr.contract_version, sr.content_json,
                       sr.content_hash, sr.evidence_revision_id, sr.trigger_reason,
                       sr.changed_resolvers_json, sr.resolver_manifest_json,
                       sr.version_metadata_json, sr.change_summary_json, sr.created_at
                FROM reader_snapshot_current current
                JOIN reader_snapshot_revisions sr ON sr.id = current.snapshot_revision_id
                WHERE current.chapter = ?
                """,
                (int(chapter),),
            )
        else:
            cursor.execute(
                """
                SELECT id, chapter, revision, contract_version, content_json, content_hash,
                       evidence_revision_id, trigger_reason, changed_resolvers_json,
                       resolver_manifest_json, version_metadata_json, change_summary_json, created_at
                FROM reader_snapshot_revisions
                WHERE chapter = ? AND revision = ?
                """,
                (int(chapter), int(revision)),
            )
        row = cursor.fetchone()
        return SnapshotStore._row_payload(row) if row else None

    @staticmethod
    def history(db: BookDatabase, chapter: int) -> list[dict]:
        cursor = db._get_connection().cursor()
        cursor.execute(
            """
            SELECT id, chapter, revision, contract_version, content_json, content_hash,
                   evidence_revision_id, trigger_reason, changed_resolvers_json,
                   resolver_manifest_json, version_metadata_json, change_summary_json, created_at
            FROM reader_snapshot_revisions
            WHERE chapter = ?
            ORDER BY revision
            """,
            (int(chapter),),
        )
        return [SnapshotStore._row_payload(row, include_content=False) for row in cursor.fetchall()]

    @staticmethod
    def _row_payload(row: tuple, include_content: bool = True) -> dict:
        payload = {
            "snapshot_id": int(row[0]),
            "chapter": int(row[1]),
            "revision": int(row[2]),
            "contract_version": row[3],
            "content_hash": row[5],
            "evidence_revision_id": row[6],
            "trigger_reason": row[7],
            "changed_resolvers": _as_json(row[8], []),
            "resolver_manifest": _as_json(row[9], {}),
            "version_metadata": _as_json(row[10], {}),
            "change_summary": _as_json(row[11], {}),
            "created_at": row[12],
        }
        if include_content:
            payload["snapshot"] = _as_json(row[4], {})
        return payload

    @staticmethod
    def _version_metadata(parent_graph_hash: str) -> dict:
        return {
            "bookbuddy_version": BOOKBUDDY_VERSION,
            "model_name": GEMINI_MODEL_NAME,
            "version_manifest": resolver_manifest(),
            "parent_graph_hash": parent_graph_hash or "",
        }

    @staticmethod
    def _change_summary(previous: dict, current: dict) -> dict:
        sections = {}
        affected = {"entities": set(), "landmarks": set(), "relationships": set()}
        section_keys = {
            "visible_entities": lambda item: f"{item.get('entity_type')}::{item.get('canonical_name')}",
            "visible_relationships": lambda item: f"{item.get('source')}->{item.get('target')}",
            "life_status": lambda item: item.get("entity"),
            "landmarks": lambda item: item.get("identity_key") or item.get("name"),
            "unresolved_mentions": lambda item: f"{item.get('entity_type')}::{item.get('surface')}",
            "reference_mentions": lambda item: f"{item.get('normalized')}::{item.get('chapter')}",
            "language_observations": lambda item: item.get("text"),
            "ontology_changes": lambda item: f"{item.get('entity')}::{item.get('field')}",
            "legacy_signals": lambda item: f"{item.get('entity')}::{item.get('signal_type')}",
            "timeline_changes": lambda item: item.get("identity_key") or item.get("summary"),
        }
        for section, key_fn in section_keys.items():
            before = {str(key_fn(item)): item for item in previous.get(section, []) if key_fn(item) is not None}
            after = {str(key_fn(item)): item for item in current.get(section, []) if key_fn(item) is not None}
            added = sorted(key for key in after if key not in before)
            removed = sorted(key for key in before if key not in after)
            updated = sorted(key for key in after if key in before and after[key] != before[key])
            if added or removed or updated:
                sections[section] = {"added": added, "removed": removed, "updated": updated}
            for key in added + removed + updated:
                if section in {"visible_entities", "life_status", "ontology_changes", "legacy_signals"}:
                    affected["entities"].add(key.split("::", 1)[-1])
                elif section == "visible_relationships":
                    affected["relationships"].add(key)
                    affected["entities"].update(part for part in key.split("->") if part)
                elif section == "landmarks":
                    affected["landmarks"].add(key)
        return {
            "changed": bool(sections),
            "sections": sections,
            "affected": {name: sorted(values) for name, values in affected.items()},
        }


class ReplayCoordinator:
    """Rebuild a session graph in staging and promote it only after success."""

    def __init__(self, db_dir: str, observer=None, fault_injector=None):
        self.db_dir = os.path.abspath(db_dir)
        self.graph_path = os.path.join(self.db_dir, "graph.db")
        self.observer = observer
        self.fault_injector = fault_injector

    def _fault(self, point: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector.hit(point)

    def import_legacy_evidence(self) -> list[dict]:
        db = BookDatabase(self.db_dir)
        try:
            return EvidenceStore.import_legacy_caches(db, self.db_dir)
        finally:
            db.close()

    def replay(self, reason: str = "manual_rebuild", mode: str = "normal") -> dict:
        """Compatibility entry point for explicit deterministic replay modes."""
        return self.run(mode=mode, reason=reason)

    def run(self, *, mode: str = "normal", reason: str = "manual_rebuild") -> dict:
        if mode not in {"normal", "full", "verify"}:
            raise ValueError("mode must be normal, full, or verify")
        # Verification intentionally leaves legacy cache import alone because it
        # must not mutate the live graph before comparing derived output.
        if mode != "verify":
            self.import_legacy_evidence()
        source_db = BookDatabase(self.db_dir)
        try:
            evidence_records = EvidenceStore.active_records(source_db)
            if not evidence_records:
                return {
                    "rebuilt": False,
                    "mode": mode,
                    "promoted": False,
                    "verified": mode == "verify",
                    "reason": "no_active_evidence",
                    "chapters": 0,
                }
            parent_hash = self._parent_graph_hash()
            if mode != "verify":
                self._record_version_invalidations(source_db, parent_hash)
            scope = self._normal_replay_scope(source_db)
            if mode == "normal" and not scope["required"]:
                return {
                    "rebuilt": False,
                    "mode": mode,
                    "promoted": False,
                    "verified": True,
                    "reason": "already_current",
                    "chapters": 0,
                    "snapshots_changed": 0,
                    "snapshots": [],
                    "affected_from_chapter": None,
                }
            source_graph = source_db.db_path
            source_hashes = self._snapshot_hashes(source_db)
        finally:
            source_db.close()

        staging_root = tempfile.mkdtemp(prefix=".chapter-replay-", dir=self.db_dir)
        stage_db: BookDatabase | None = None
        try:
            parent_hash, inherited = self._seed_staging(staging_root)
            stage_db = BookDatabase(staging_root)
            if inherited:
                stage_db.mark_graph_as_inherited(**inherited)
            self._copy_retention_history(source_graph, stage_db)

            from analysis_engine import ingest_ai_payload
            from graph_invariant_tests import assert_graph_invariants

            snapshots = []
            for evidence in evidence_records:
                self._fault("replay.before_chapter")
                payload = evidence["payload"]
                if "System skipped" not in str(payload.get("major_events", [])):
                    ingest_ai_payload(payload, evidence["chapter"], stage_db)
                snapshots.append(
                    SnapshotStore.capture(
                        stage_db,
                        evidence["chapter"],
                        evidence,
                        trigger_reason=reason or evidence["trigger_reason"],
                        parent_graph_hash=parent_hash,
                    )
                )
                self._fault("replay.after_snapshot")

            stage_db._get_connection().execute(
                "UPDATE chapter_invalidations SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE status = 'open'"
            )
            stage_db._get_connection().commit()
            stage_db.close()
            stage_db = None
            assert_graph_invariants(os.path.join(staging_root, "graph.db"))
            stage_hashes = self._snapshot_hashes_from_path(os.path.join(staging_root, "graph.db"))
            verification_mismatches = self._snapshot_mismatches(source_hashes, stage_hashes)
            if mode == "verify":
                from audit.database import compare_databases
                database_comparison = compare_databases(
                    source_graph,
                    os.path.join(staging_root, "graph.db"),
                    categories=("derived",),
                )
                return {
                    "rebuilt": True,
                    "mode": mode,
                    "promoted": False,
                    "verified": not verification_mismatches and database_comparison["matched"],
                    "verification_mismatches": verification_mismatches,
                    "database_comparison": database_comparison,
                    "chapters": len(evidence_records),
                    "reason": reason,
                    "affected_from_chapter": scope["from_chapter"],
                    "snapshots_changed": sum(1 for item in snapshots if item["changed"]),
                }
            self._fault("replay.before_promote")
            os.replace(os.path.join(staging_root, "graph.db"), self.graph_path)
            return {
                "rebuilt": True,
                "mode": mode,
                "promoted": True,
                "verified": True,
                "chapters": len(evidence_records),
                "reason": reason,
                "affected_from_chapter": 0 if mode == "full" else scope["from_chapter"],
                "parent_graph_hash": parent_hash,
                "snapshots_changed": sum(1 for item in snapshots if item["changed"]),
                "snapshots": snapshots,
            }
        except Exception as exc:
            if stage_db is not None:
                stage_db.close()
            if mode != "verify":
                self._record_failed_replay(reason, str(exc))
            raise
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

    @staticmethod
    def _snapshot_hashes(db: BookDatabase) -> dict[int, str]:
        rows = db._get_connection().execute(
            "SELECT chapter, content_hash FROM reader_snapshot_current ORDER BY chapter"
        ).fetchall()
        return {int(chapter): str(content_hash) for chapter, content_hash in rows}

    @staticmethod
    def _snapshot_hashes_from_path(graph_path: str) -> dict[int, str]:
        conn = sqlite3.connect(graph_path)
        try:
            rows = conn.execute("SELECT chapter, content_hash FROM reader_snapshot_current ORDER BY chapter").fetchall()
            return {int(chapter): str(content_hash) for chapter, content_hash in rows}
        finally:
            conn.close()

    @staticmethod
    def _snapshot_mismatches(expected: dict[int, str], actual: dict[int, str]) -> list[dict]:
        return [
            {"chapter": chapter, "expected_hash": expected.get(chapter), "actual_hash": actual.get(chapter)}
            for chapter in sorted(set(expected) | set(actual))
            if expected.get(chapter) != actual.get(chapter)
        ]

    @staticmethod
    def _normal_replay_scope(db: BookDatabase) -> dict:
        conn = db._get_connection()
        open_row = conn.execute(
            "SELECT MIN(from_chapter) FROM chapter_invalidations WHERE status = 'open'"
        ).fetchone()
        missing_rows = conn.execute(
            """
            SELECT evidence.chapter
            FROM chapter_evidence_revisions evidence
            LEFT JOIN chapter_processing_checkpoints checkpoint
              ON checkpoint.evidence_revision_id = evidence.id AND checkpoint.state = 'complete'
            WHERE evidence.is_active = 1 AND checkpoint.chapter IS NULL
            ORDER BY evidence.chapter
            """
        ).fetchall()
        candidates = [int(open_row[0])] if open_row and open_row[0] is not None else []
        candidates.extend(int(row[0]) for row in missing_rows)
        return {"required": bool(candidates), "from_chapter": min(candidates) if candidates else None}

    def _seed_staging(self, staging_root: str) -> tuple[str, dict | None]:
        continuity_path = os.path.join(os.path.dirname(self.db_dir), "continuity.json")
        try:
            with open(continuity_path, "r", encoding="utf-8") as handle:
                continuity = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continuity = {}
        parent_book = continuity.get("parent_book")
        parent_session = continuity.get("parent_session")
        session_dir = os.path.dirname(self.db_dir)
        parent_graph = self._parent_graph_path(continuity)
        if not os.path.exists(parent_graph):
            return "", None
        staging_graph = os.path.join(staging_root, "graph.db")
        shutil.copy2(parent_graph, staging_graph)
        from continuity_manager import prune_inherited_graph

        prune_inherited_graph(staging_graph)
        return _file_hash(parent_graph), {
            "parent_book": str(parent_book),
            "parent_session": str(parent_session),
            "target_book": continuity.get("current_book"),
            "target_session": os.path.basename(session_dir),
        }

    def _parent_graph_path(self, continuity: dict | None = None) -> str:
        if continuity is None:
            continuity_path = os.path.join(os.path.dirname(self.db_dir), "continuity.json")
            try:
                with open(continuity_path, "r", encoding="utf-8") as handle:
                    continuity = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continuity = {}
        parent_book = continuity.get("parent_book")
        parent_session = continuity.get("parent_session")
        if not parent_book or not parent_session:
            return ""
        session_dir = os.path.dirname(self.db_dir)
        library_dir = os.path.dirname(os.path.dirname(session_dir))
        return os.path.join(library_dir, str(parent_book), str(parent_session), "database", "graph.db")

    def _parent_graph_hash(self) -> str:
        return _file_hash(self._parent_graph_path())

    @staticmethod
    def _record_version_invalidations(db: BookDatabase, parent_graph_hash: str) -> None:
        conn = db._get_connection()
        cursor = conn.cursor()
        manifest = resolver_manifest()
        manifest_hash = _stable_hash(manifest)
        cursor.execute(
            """
            SELECT chapter, resolver_manifest_json, resolver_manifest_hash,
                   graph_schema_version, parent_graph_hash
            FROM chapter_processing_checkpoints
            WHERE state = 'complete'
            ORDER BY chapter
            """
        )
        mismatches: dict[str, list[int]] = {}
        for chapter, saved_manifest_json, saved_manifest_hash, schema_version, saved_parent_hash in cursor.fetchall():
            reason = ""
            affected = []
            if saved_manifest_hash and saved_manifest_hash != manifest_hash:
                reason = "resolver_manifest_changed"
                affected = _changed_resolvers(_as_json(saved_manifest_json, {}), manifest)
            elif schema_version is not None and int(schema_version) != int(GRAPH_SCHEMA_VERSION):
                reason = "graph_schema_changed"
                affected = sorted(RESOLVER_VERSIONS)
            elif parent_graph_hash and saved_parent_hash and saved_parent_hash != parent_graph_hash:
                reason = "parent_graph_changed"
                affected = sorted(RESOLVER_VERSIONS)
            if reason:
                mismatches.setdefault(reason, []).append((int(chapter), affected))
        for reason, mismatch_rows in mismatches.items():
            chapters = [chapter for chapter, _affected in mismatch_rows]
            affected = sorted({item for _chapter, items in mismatch_rows for item in items})
            cursor.execute(
                """
                INSERT INTO chapter_invalidations (from_chapter, reason, details_json)
                VALUES (?, ?, ?)
                """,
                (
                    min(chapters),
                    reason,
                    _canonical_json(
                        {
                            "chapters": chapters,
                            "version_manifest": manifest,
                            "affected_resolvers": affected,
                            "graph_schema_version": GRAPH_SCHEMA_VERSION,
                            "parent_graph_hash": parent_graph_hash,
                        }
                    ),
                ),
            )
        if mismatches:
            conn.commit()

    @staticmethod
    def _copy_retention_history(source_graph: str, target_db: BookDatabase) -> None:
        source = sqlite3.connect(source_graph)
        source.row_factory = sqlite3.Row
        target = target_db._get_connection()
        delete_order = (
            "reader_snapshot_current",
            "chapter_processing_checkpoints",
            "reader_snapshot_revisions",
            "resolver_decisions",
            "image_occurrence_provenance",
            "image_evidence_revisions",
            "chapter_evidence_revisions",
            "chapter_invalidations",
            "image_parse_cache",
        )
        insert_order = (
            "image_parse_cache",
            "chapter_evidence_revisions",
            "image_evidence_revisions",
            "image_occurrence_provenance",
            "resolver_decisions",
            "reader_snapshot_revisions",
            "reader_snapshot_current",
            "chapter_processing_checkpoints",
            "chapter_invalidations",
        )
        try:
            for table in delete_order:
                target.execute(f"DELETE FROM {table}")
            for table in insert_order:
                source_exists = source.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
                ).fetchone()
                if not source_exists:
                    continue
                columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
                if not columns:
                    continue
                rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
                if not rows:
                    continue
                placeholders = ", ".join("?" for _ in columns)
                target.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    [tuple(row[column] for column in columns) for row in rows],
                )
            target.commit()
        finally:
            source.close()

    def _record_failed_replay(self, reason: str, error: str) -> None:
        db = BookDatabase(self.db_dir)
        try:
            conn = db._get_connection()
            conn.execute(
                """
                INSERT INTO chapter_invalidations (from_chapter, reason, details_json, status)
                VALUES (0, ?, ?, 'failed')
                """,
                (reason or "manual_rebuild", _canonical_json({"error": error[:2000]})),
            )
            conn.execute(
                "UPDATE chapter_processing_checkpoints SET state = 'failed', error_text = ?, updated_at = CURRENT_TIMESTAMP",
                (error[:2000],),
            )
            conn.commit()
        finally:
            db.close()
