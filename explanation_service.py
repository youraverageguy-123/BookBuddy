"""Internal, engine-scoped explanations built from append-only resolver records."""

from __future__ import annotations

import json
from typing import Any

from db_manager import BookDatabase
from snapshot_manager import EvidenceStore, SnapshotStore


class ExplanationService:
    """Read-only explanation facade; it never mutates evidence or snapshots."""

    _KINDS = {"entity", "landmark", "life_status", "relationship", "snapshot", "evidence_revision"}

    def __init__(self, db: BookDatabase):
        self.db = db

    def explain(
        self,
        kind: str,
        subject: str | int,
        *,
        chapter: int | None = None,
        revision: int | None = None,
    ) -> dict[str, Any]:
        kind = str(kind or "").strip().lower()
        if kind not in self._KINDS:
            raise ValueError(f"kind must be one of: {', '.join(sorted(self._KINDS))}")
        if kind == "entity":
            detail, subject_key = self._entity_detail(subject)
            decisions = self._decisions_for_entity(subject_key, chapter)
            conflicts = self._conflicts("entity", subject_key)
        elif kind == "landmark":
            detail, subject_key = self._landmark_detail(subject)
            decisions = self.db.get_resolver_decisions(
                resolver_key="landmarks", subject_type="landmark", subject_key=subject_key, chapter=chapter
            )
            conflicts = self._conflicts("landmark", subject_key)
        elif kind == "life_status":
            detail, subject_key = self._life_status_detail(subject, chapter)
            decisions = self.db.get_resolver_decisions(
                resolver_key="life_status", subject_type="entity", subject_key=subject_key, chapter=chapter
            )
            conflicts = self._conflicts("entity", subject_key)
        elif kind == "relationship":
            detail, subject_key = self._relationship_detail(subject)
            decisions = self.db.get_resolver_decisions(
                resolver_key="relationships", subject_type="relationship", subject_key=subject_key, chapter=chapter
            )
            conflicts = self._conflicts("relationship", subject_key)
        elif kind == "snapshot":
            snapshot_chapter = int(chapter if chapter is not None else subject)
            detail = SnapshotStore.get(self.db, snapshot_chapter, revision)
            subject_key = str(snapshot_chapter)
            decisions = self.db.get_resolver_decisions(chapter=snapshot_chapter)
            conflicts = []
        else:
            detail, subject_key = self._evidence_detail(subject, revision)
            decisions = self.db.get_resolver_decisions(chapter=detail["chapter"] if detail else chapter)
            conflicts = []
        return {
            "scope": "engine_debug",
            "kind": kind,
            "subject": str(subject_key),
            "chapter": chapter,
            "detail": detail,
            "decisions": decisions,
            "conflicts": conflicts,
        }

    def _entity_detail(self, subject: str | int) -> tuple[dict, str]:
        conn = self.db._get_connection()
        if str(subject).isdigit():
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (int(subject),)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM entities WHERE lower(canonical_name) = lower(?) ORDER BY id LIMIT 1", (str(subject),)
            ).fetchone()
        if not row:
            raise LookupError("entity not found")
        columns = [item[1] for item in conn.execute("PRAGMA table_info(entities)").fetchall()]
        return dict(zip(columns, row)), str(row[0])

    def _landmark_detail(self, subject: str | int) -> tuple[dict, str]:
        conn = self.db._get_connection()
        if str(subject).isdigit():
            row = conn.execute("SELECT id FROM event_landmarks WHERE id = ?", (int(subject),)).fetchone()
        else:
            row = conn.execute("SELECT id FROM event_landmarks WHERE identity_key = ?", (str(subject),)).fetchone()
        if not row:
            raise LookupError("landmark not found")
        landmark_id = int(row[0])
        return self.db.get_landmark_explanation(landmark_id), str(landmark_id)

    def _life_status_detail(self, subject: str | int, chapter: int | None) -> tuple[dict, str]:
        entity, entity_key = self._entity_detail(subject)
        conn = self.db._get_connection()
        rows = conn.execute(
            """
            SELECT scope_type, scope_owner_entity_id, actual_status, belief_status, appearance_status,
                   confidence, last_observation_chapter, last_confirmation_chapter, status_age,
                   source_evidence_ids, resolver_version, updated_at
            FROM life_status_snapshots WHERE entity_id = ?
            ORDER BY scope_type, scope_owner_entity_id
            """,
            (int(entity_key),),
        ).fetchall()
        return {
            "entity": entity["canonical_name"],
            "entity_id": int(entity_key),
            "as_of_chapter": chapter,
            "resolved_scopes": [
                {
                    "scope": row[0], "owner_entity_id": row[1], "actual_status": row[2],
                    "belief_status": row[3], "appearance_status": row[4], "confidence": row[5],
                    "last_observation_chapter": row[6], "last_confirmation_chapter": row[7],
                    "status_age": row[8], "evidence_ids": self._json(row[9], []),
                    "resolver_version": row[10], "updated_at": row[11],
                }
                for row in rows
            ],
        }, entity_key

    def _relationship_detail(self, subject: str | int) -> tuple[dict, str]:
        rel_key = str(subject)
        conn = self.db._get_connection()
        relation = conn.execute("SELECT * FROM relationships WHERE rel_key = ?", (rel_key,)).fetchone()
        if not relation:
            raise LookupError("relationship not found; use its source_id::target_id key")
        columns = [item[1] for item in conn.execute("PRAGMA table_info(relationships)").fetchall()]
        history_columns = [item[1] for item in conn.execute("PRAGMA table_info(relationship_history)").fetchall()]
        history = conn.execute("SELECT * FROM relationship_history WHERE rel_key = ? ORDER BY chapter, interaction_order, id", (rel_key,)).fetchall()
        return {"relationship": dict(zip(columns, relation)), "history": [dict(zip(history_columns, row)) for row in history]}, rel_key

    def _evidence_detail(self, subject: str | int, revision: int | None) -> tuple[dict, str]:
        chapter = int(subject)
        if revision is None:
            payload = EvidenceStore.active_payload(self.db, chapter)
            if payload is None:
                raise LookupError("active evidence revision not found")
            row = self.db._get_connection().execute(
                """SELECT id, chapter, revision, payload_hash, trigger_reason, source_metadata_json, created_at
                   FROM chapter_evidence_revisions WHERE chapter = ? AND is_active = 1""",
                (chapter,),
            ).fetchone()
        else:
            row = self.db._get_connection().execute(
                """SELECT id, chapter, revision, payload_hash, trigger_reason, source_metadata_json, created_at
                   FROM chapter_evidence_revisions WHERE chapter = ? AND revision = ?""",
                (chapter, int(revision)),
            ).fetchone()
            payload_row = self.db._get_connection().execute(
                "SELECT payload_json FROM chapter_evidence_revisions WHERE chapter = ? AND revision = ?", (chapter, int(revision))
            ).fetchone()
            payload = self._json(payload_row[0], {}) if payload_row else None
        if not row or payload is None:
            raise LookupError("evidence revision not found")
        return {
            "id": row[0], "chapter": row[1], "revision": row[2], "payload_hash": row[3],
            "trigger_reason": row[4], "source_metadata": self._json(row[5], {}), "created_at": row[6],
            "payload": payload,
        }, str(chapter)

    def _decisions_for_entity(self, entity_key: str, chapter: int | None) -> list[dict]:
        return [
            *self.db.get_resolver_decisions(resolver_key="identity", subject_type="entity", subject_key=entity_key, chapter=chapter),
            *self.db.get_resolver_decisions(resolver_key="ontology", subject_type="entity", subject_key=entity_key, chapter=chapter),
        ]

    def _conflicts(self, subject_type: str, subject_key: str) -> list[dict]:
        rows = self.db._get_connection().execute(
            """
            SELECT id, conflict_type, chapter, payload, resolver_key, subject_type, subject_key,
                   evidence_refs_json, alternatives_json, severity, status, created_at
            FROM conflict_records
            WHERE subject_type = ? AND subject_key = ?
            ORDER BY chapter, id
            """,
            (subject_type, str(subject_key)),
        ).fetchall()
        return [
            {
                "id": row[0], "type": row[1], "chapter": row[2], "payload": self._json(row[3], {}),
                "resolver": row[4], "subject": {"type": row[5], "key": row[6]},
                "evidence_refs": self._json(row[7], []), "alternatives": self._json(row[8], []),
                "severity": row[9], "status": row[10], "created_at": row[11],
            }
            for row in rows
        ]

    @staticmethod
    def _json(value: str | None, fallback: Any) -> Any:
        try:
            return json.loads(value) if value else fallback
        except (TypeError, json.JSONDecodeError):
            return fallback
