import json
import math

from config import LIFE_STATUS_DECAY_AFTER_CHAPTERS, LIFE_STATUS_DECAY_FACTOR


RESOLVER_VERSION = "life_status_resolver_v1"

NON_PHYSICAL_PARTICIPATION = {
    "flashback",
    "memory",
    "vision",
    "letter",
    "recording",
    "historical_reference",
    "dream",
    "hallucination",
}

DECAYABLE_ACTUAL_STATUSES = {"missing", "unknown"}
DECAYABLE_BELIEF_STATUSES = {"missing", "dead", "unknown"}
DECAYABLE_APPEARANCE_STATUSES = {"possible_alive", "observed_alive", "appears_dead", "unknown"}
CONFIRMED_APPEARANCES = {"confirmed_alive"}
CONFIRMED_OBSERVATIONS = {"direct"}


class LifeStatusResolver:
    """Compute cached life-status snapshots from append-only evidence.

    Evidence remains the source of truth. Snapshots and timeline segments are
    disposable resolver outputs for prompts, evaluation, and UI timelines.
    """

    def __init__(self, db):
        self.db = db

    def resolve_all(self):
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT entity_id FROM life_status_evidence")
            entity_ids = [entity_id for (entity_id,) in cursor.fetchall()]
        for entity_id in entity_ids:
            self.resolve_entity(entity_id)

    def resolve_entity(self, entity_id: int):
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chapter, narrative_order, actual_status,
                       belief_status, appearance_status, belief_owner_type,
                       belief_owner_entity_id, reader_visible,
                       participation_type, observation_type, status_reason,
                       identity_continuity_mode, confidence,
                       last_observation_chapter, last_confirmation_chapter,
                       supersedes_evidence_id, linked_event_id,
                       COALESCE(inherited_confidence, 1.0)
                FROM life_status_evidence
                WHERE entity_id = ?
                ORDER BY COALESCE(chapter, 0), COALESCE(narrative_order, 0), id
            """, (entity_id,))
            rows = [self._row_to_dict(row) for row in cursor.fetchall()]
            cursor.execute("DELETE FROM life_status_snapshots WHERE entity_id = ?", (entity_id,))
            cursor.execute("DELETE FROM life_status_timeline_segments WHERE entity_id = ?", (entity_id,))
            if not rows:
                return
            latest_chapter = self._current_graph_chapter(cursor, rows)
            active_rows = self._drop_superseded(rows)
            scopes = self._scopes_for_rows(active_rows)
            for scope_type, owner_id in scopes:
                scoped_rows = self._rows_for_scope(active_rows, scope_type, owner_id)
                snapshot = self._compute_snapshot(scoped_rows, latest_chapter, scope_type, owner_id)
                if snapshot:
                    self._write_snapshot(conn, entity_id, snapshot)
            self._write_timeline(conn, entity_id, rows)

    def reader_status_at(self, chapter: int) -> list[dict]:
        """Resolve the reader-visible life view without consulting future evidence."""
        chapter = int(chapter)
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT entity_id
                FROM life_status_evidence
                WHERE reader_visible = 1 AND COALESCE(chapter, 0) <= ?
                ORDER BY entity_id
            """, (chapter,))
            entity_ids = [row[0] for row in cursor.fetchall()]
            result = []
            for entity_id in entity_ids:
                cursor.execute("""
                    SELECT id, chapter, narrative_order, actual_status,
                           belief_status, appearance_status, belief_owner_type,
                           belief_owner_entity_id, reader_visible,
                           participation_type, observation_type, status_reason,
                           identity_continuity_mode, confidence,
                           last_observation_chapter, last_confirmation_chapter,
                           supersedes_evidence_id, linked_event_id,
                           COALESCE(inherited_confidence, 1.0)
                    FROM life_status_evidence
                    WHERE entity_id = ? AND reader_visible = 1
                      AND COALESCE(chapter, 0) <= ?
                    ORDER BY COALESCE(chapter, 0), COALESCE(narrative_order, 0), id
                """, (entity_id, chapter))
                rows = self._drop_superseded([self._row_to_dict(row) for row in cursor.fetchall()])
                snapshot = self._compute_snapshot(rows, chapter, "reader", None)
                if not snapshot:
                    continue
                cursor.execute("SELECT canonical_name FROM entities WHERE id = ?", (entity_id,))
                name_row = cursor.fetchone()
                if not name_row:
                    continue
                actual = snapshot["actual_status"]
                belief = snapshot["belief_status"]
                appearance = snapshot["appearance_status"]
                if actual != "unknown" and belief != "unknown" and actual != belief:
                    reader_state = "disputed"
                    status = belief
                elif actual != "unknown" and snapshot["actual_confidence"] >= 0.75:
                    reader_state = "known"
                    status = actual
                elif belief != "unknown":
                    reader_state = "believed"
                    status = belief
                elif appearance != "unknown":
                    reader_state = "believed"
                    status = appearance
                else:
                    reader_state = "unknown"
                    status = "unknown"
                result.append({
                    "entity": name_row[0],
                    "reader_state": reader_state,
                    "status": status,
                    "confidence": snapshot["confidence"],
                    "last_observation_chapter": snapshot["last_observation_chapter"],
                    "last_confirmation_chapter": snapshot["last_confirmation_chapter"],
                    "status_age": snapshot["status_age"],
                    "evidence_refs": [
                        {"table": "life_status_evidence", "id": evidence_id}
                        for evidence_id in json.loads(snapshot["source_evidence_ids"] or "[]")
                    ],
                })
        return result

    def _current_graph_chapter(self, cursor, rows):
        latest = max(int(row["chapter"] or 0) for row in rows)
        for table_name in ("chapter_boundaries", "events"):
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,))
            if not cursor.fetchone():
                continue
            cursor.execute(f"SELECT MAX(chapter) FROM {table_name}")
            row = cursor.fetchone()
            if row and row[0] is not None:
                latest = max(latest, int(row[0]))
        return latest

    def _row_to_dict(self, row):
        (
            evidence_id, chapter, narrative_order, actual_status,
            belief_status, appearance_status, belief_owner_type,
            belief_owner_entity_id, reader_visible, participation_type,
            observation_type, status_reason, identity_continuity_mode,
            confidence, last_observation_chapter, last_confirmation_chapter,
            supersedes_evidence_id, linked_event_id, inherited_confidence,
        ) = row
        return {
            "id": evidence_id,
            "chapter": chapter,
            "narrative_order": narrative_order,
            "actual_status": actual_status or "unknown",
            "belief_status": belief_status or "unknown",
            "appearance_status": appearance_status or "unknown",
            "belief_owner_type": belief_owner_type or "unknown",
            "belief_owner_entity_id": belief_owner_entity_id,
            "reader_visible": bool(reader_visible),
            "participation_type": participation_type or "active_scene",
            "observation_type": observation_type or "direct",
            "status_reason": status_reason or "unknown",
            "identity_continuity_mode": identity_continuity_mode or "unknown",
            "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
            "last_observation_chapter": last_observation_chapter or chapter,
            "last_confirmation_chapter": last_confirmation_chapter,
            "supersedes_evidence_id": supersedes_evidence_id,
            "linked_event_id": linked_event_id,
            "inherited_confidence": max(0.01, min(1.0, float(inherited_confidence or 1.0))),
        }

    def _drop_superseded(self, rows):
        superseded = {row["supersedes_evidence_id"] for row in rows if row["supersedes_evidence_id"]}
        return [row for row in rows if row["id"] not in superseded]

    def _scopes_for_rows(self, rows):
        scopes = {("global_story", None)}
        for row in rows:
            if row["reader_visible"]:
                scopes.add(("reader", None))
            owner_type = row["belief_owner_type"]
            owner_id = row["belief_owner_entity_id"]
            if owner_type in {"narrator", "character", "group"} and owner_id:
                scopes.add((owner_type, owner_id))
        return sorted(scopes, key=lambda item: (item[0], item[1] or 0))

    def _rows_for_scope(self, rows, scope_type, owner_id):
        if scope_type == "global_story":
            return rows
        if scope_type == "reader":
            return [row for row in rows if row["reader_visible"]]
        return [
            row for row in rows
            if row["belief_owner_type"] == scope_type and row["belief_owner_entity_id"] == owner_id
        ]

    def _compute_snapshot(self, rows, latest_chapter, scope_type, owner_id):
        if not rows:
            return None
        rows = sorted(rows, key=lambda row: (row["chapter"] or 0, row["narrative_order"] or 0, row["id"]))
        actual = self._winner(rows, "actual_status", latest_chapter, DECAYABLE_ACTUAL_STATUSES)
        belief = self._winner(rows, "belief_status", latest_chapter, DECAYABLE_BELIEF_STATUSES)
        appearance = self._winner(rows, "appearance_status", latest_chapter, DECAYABLE_APPEARANCE_STATUSES)
        latest = rows[-1]
        evidence_ids = [row["id"] for row in rows[-8:]]
        confidence = max(actual["score"], belief["score"], appearance["score"])
        confirmation_chapters = [
            row["last_confirmation_chapter"]
            for row in rows
            if row["last_confirmation_chapter"] is not None
        ]
        observation_chapters = [
            row["last_observation_chapter"]
            if row["last_observation_chapter"] is not None
            else row["chapter"]
            for row in rows
        ]
        latest_confirmation = max(confirmation_chapters) if confirmation_chapters else None
        latest_observation = max(observation_chapters) if observation_chapters else None
        status_age = max(0, int(latest_chapter or 0) - int(latest_confirmation or latest_observation or latest_chapter or 0))
        return {
            "scope_type": scope_type,
            "scope_owner_entity_id": owner_id,
            "actual_status": actual["value"],
            "belief_status": belief["value"],
            "appearance_status": appearance["value"],
            "actual_confidence": round(actual["score"], 4),
            "confidence": round(confidence, 4),
            "evidence_count": len(rows),
            "latest_evidence_id": latest["id"],
            "last_observation_chapter": latest_observation,
            "last_confirmation_chapter": latest_confirmation,
            "status_age": status_age,
            "source_evidence_ids": json.dumps(evidence_ids),
        }

    def _winner(self, rows, field, latest_chapter, decayable_values):
        scores = {}
        latest_order = {}
        for idx, row in enumerate(rows):
            value = row.get(field) or "unknown"
            if value == "unknown":
                continue
            score = self._effective_confidence(row, value, field, latest_chapter, decayable_values)
            if score <= 0:
                continue
            scores[value] = scores.get(value, 0.0) + score
            latest_order[value] = idx
        if not scores:
            return {"value": "unknown", "score": 0.0}
        value = max(scores, key=lambda key: (scores[key], latest_order.get(key, -1)))
        return {"value": value, "score": min(1.0, scores[value])}

    def _effective_confidence(self, row, value, field, latest_chapter, decayable_values):
        confidence = row["confidence"] * row["inherited_confidence"]
        observation = row["observation_type"]
        participation = row["participation_type"]
        continuity = row["identity_continuity_mode"]
        if field in {"actual_status", "appearance_status"} and participation in NON_PHYSICAL_PARTICIPATION:
            return 0.0
        if field == "actual_status":
            if observation in {"rumor", "assumed", "dream", "vision", "flashback"}:
                return min(confidence, 0.45)
            if value == "alive" and continuity not in {"same_identity", "revived", "unknown"}:
                return 0.0
        if field == "appearance_status" and value in CONFIRMED_APPEARANCES:
            confidence = max(confidence, 0.8)
        age_base = row["last_confirmation_chapter"] or row["last_observation_chapter"] or row["chapter"] or latest_chapter
        age = max(0, int(latest_chapter or 0) - int(age_base or 0))
        if value in decayable_values and age > LIFE_STATUS_DECAY_AFTER_CHAPTERS:
            confidence *= math.pow(LIFE_STATUS_DECAY_FACTOR, age - LIFE_STATUS_DECAY_AFTER_CHAPTERS)
        if (
            field == "actual_status"
            and value in {"alive", "dead"}
            and observation in CONFIRMED_OBSERVATIONS
            and row["inherited_confidence"] >= 0.999
        ):
            return max(confidence, 0.75)
        return confidence

    def _write_snapshot(self, conn, entity_id, snapshot):
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO life_status_snapshots (
                entity_id, scope_type, scope_owner_entity_id,
                actual_status, belief_status, appearance_status,
                confidence, evidence_count, latest_evidence_id,
                last_observation_chapter, last_confirmation_chapter,
                status_age, source_evidence_ids, resolver_version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(entity_id, scope_type, scope_owner_entity_id) DO UPDATE SET
                actual_status = excluded.actual_status,
                belief_status = excluded.belief_status,
                appearance_status = excluded.appearance_status,
                confidence = excluded.confidence,
                evidence_count = excluded.evidence_count,
                latest_evidence_id = excluded.latest_evidence_id,
                last_observation_chapter = excluded.last_observation_chapter,
                last_confirmation_chapter = excluded.last_confirmation_chapter,
                status_age = excluded.status_age,
                source_evidence_ids = excluded.source_evidence_ids,
                resolver_version = excluded.resolver_version,
                updated_at = CURRENT_TIMESTAMP
        """, (
            entity_id,
            snapshot["scope_type"],
            snapshot["scope_owner_entity_id"],
            snapshot["actual_status"],
            snapshot["belief_status"],
            snapshot["appearance_status"],
            snapshot["confidence"],
            snapshot["evidence_count"],
            snapshot["latest_evidence_id"],
            snapshot["last_observation_chapter"],
            snapshot["last_confirmation_chapter"],
            snapshot["status_age"],
            snapshot["source_evidence_ids"],
            RESOLVER_VERSION,
        ))
        if snapshot["scope_type"] == "global_story":
            cursor.execute("""
                UPDATE entities
                SET current_life_status = ?,
                    life_confidence = ?,
                    life_status_chapter = ?,
                    life_status_source = ?
                WHERE id = ?
            """, (
                snapshot["actual_status"],
                snapshot["actual_confidence"] if snapshot["actual_status"] != "unknown" else 0.0,
                snapshot["last_confirmation_chapter"] or snapshot["last_observation_chapter"],
                str(snapshot["latest_evidence_id"] or ""),
                entity_id,
            ))
        self.db.record_resolver_decision(
            "life_status",
            "entity",
            entity_id,
            snapshot["last_observation_chapter"],
            "status_resolved",
            confidence=snapshot["confidence"],
            supporting_evidence=[
                {"table": "life_status_evidence", "id": evidence_id}
                for evidence_id in json.loads(snapshot["source_evidence_ids"] or "[]")
            ],
            visibility="reader" if snapshot["scope_type"] == "reader" else "engine",
            metadata={
                "scope": snapshot["scope_type"],
                "actual_status": snapshot["actual_status"],
                "belief_status": snapshot["belief_status"],
                "appearance_status": snapshot["appearance_status"],
            },
            conn=conn,
        )

    def _write_timeline(self, conn, entity_id, rows):
        cursor = conn.cursor()
        if not rows:
            return
        ordered = sorted(rows, key=lambda row: (row["chapter"] or 0, row["narrative_order"] or 0, row["id"]))
        for idx, row in enumerate(ordered):
            next_row = ordered[idx + 1] if idx + 1 < len(ordered) else None
            end_chapter = None
            if next_row and next_row["chapter"] is not None:
                current_chapter = int(row["chapter"] or 0)
                end_chapter = max(current_chapter, int(next_row["chapter"]) - 1)
            cursor.execute("""
                INSERT INTO life_status_timeline_segments (
                    entity_id, scope_type, scope_owner_entity_id,
                    start_chapter, end_chapter, actual_status,
                    belief_status, appearance_status, confidence,
                    source_evidence_ids, timeline_position, resolver_version
                )
                VALUES (?, 'global_story', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_id,
                row["chapter"],
                end_chapter,
                row["actual_status"],
                row["belief_status"],
                row["appearance_status"],
                row["confidence"],
                json.dumps([row["id"]]),
                row["narrative_order"],
                RESOLVER_VERSION,
            ))
