"""Evidence-first resolution for historical landmarks and event containers."""

from __future__ import annotations

from typing import Any


LANDMARK_LIFECYCLES = {
    "candidate",
    "landmark",
    "historically_referenced",
    "legacy_landmark",
}
EVENT_STATES = {"planned", "ongoing", "completed", "remembered", "historical", "unknown"}
EVENT_RELIABILITIES = {"direct", "reported", "historical", "rumor", "legend", "myth", "unknown"}
READER_VISIBILITIES = {"hidden", "partially_known", "fully_known"}


def _clamp_confidence(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


class LandmarkResolver:
    """Resolve event records without treating names as immutable identities."""

    def __init__(self, db):
        self.db = db

    def resolve_or_create(
        self,
        event_record: dict,
        event_id: int,
        chapter: int,
        *,
        source_session: str | None = None,
    ) -> tuple[int | None, str]:
        record = event_record or {}
        reference = str(record.get("landmark_reference") or record.get("identity_reference") or "").strip()
        identity_hint = str(record.get("landmark_identity_key") or "").strip()
        confidence = _clamp_confidence(record.get("identity_confidence"), 0.55)

        if identity_hint:
            landmark_id = self.db.get_landmark_id_by_identity(identity_hint)
            if landmark_id:
                self._attach(landmark_id, event_id, record, chapter, confidence, "identity_key")
                return landmark_id, "identity_key"

        if reference:
            candidates = self.db.find_landmarks_by_reference(reference)
            if len(candidates) == 1:
                landmark_id = candidates[0]
                self._attach(landmark_id, event_id, record, chapter, confidence, "explicit_reference")
                return landmark_id, "explicit_reference"
            if len(candidates) > 1:
                self.db.record_conflict(
                    "landmark_fragmentation",
                    chapter,
                    {"event_id": event_id, "reference": reference, "candidate_ids": candidates},
                    resolver_key="landmarks",
                    subject_type="event",
                    subject_key=event_id,
                    alternatives=[{"landmark_id": candidate_id} for candidate_id in candidates],
                )
                self.db.record_landmark_resolution_evidence(
                    event_id,
                    None,
                    chapter,
                    decision="deferred",
                    identity_confidence=confidence,
                    merge_confidence=0.0,
                    supporting_evidence=reference,
                    contradicting_evidence="ambiguous_landmark_reference",
                    signals={"reference": reference, "candidate_count": len(candidates)},
                )
                reference = ""

        structural = self.db.find_structural_landmark_candidates(record)
        if len(structural) == 1 and structural[0][1] >= 0.85:
            landmark_id, score = structural[0]
            self._attach(landmark_id, event_id, record, chapter, score, "structural_match")
            return landmark_id, "structural_match"
        if structural:
            if len(structural) > 1:
                self.db.record_conflict(
                    "landmark_fragmentation",
                    chapter,
                    {"event_id": event_id, "summary": record.get("summary", ""), "candidates": structural[:5]},
                    resolver_key="landmarks",
                    subject_type="event",
                    subject_key=event_id,
                    alternatives=[{"landmark_id": item[0], "score": item[1]} for item in structural[:5]],
                )
            self.db.record_landmark_resolution_evidence(
                event_id,
                structural[0][0],
                chapter,
                decision="candidate",
                identity_confidence=confidence,
                merge_confidence=structural[0][1],
                supporting_evidence=str(record.get("summary") or ""),
                contradicting_evidence="insufficient_structural_evidence",
                signals={"candidate_count": len(structural)},
            )

        lifecycle = str(record.get("lifecycle") or "candidate")
        if lifecycle not in LANDMARK_LIFECYCLES:
            lifecycle = "candidate"
        if record.get("landmark_name") or record.get("landmark_reference") or record.get("landmark_type") not in {"", "event", "incident"}:
            lifecycle = "landmark" if lifecycle == "candidate" else lifecycle
        landmark_id = self.db.create_event_landmark(
            lifecycle=lifecycle,
            landmark_type=record.get("landmark_type") or "event",
            event_state=record.get("event_state") or "unknown",
            reliability=record.get("event_reliability") or "unknown",
            reader_visibility=record.get("reader_visibility") or "partially_known",
            geographic_scope=record.get("geographic_scope") or record.get("event_scope") or "unknown",
            historical_start_text=record.get("historical_start_text") or "",
            historical_end_text=record.get("historical_end_text") or "",
            historical_start_sort=record.get("historical_start_sort"),
            historical_end_sort=record.get("historical_end_sort"),
            duration_text=record.get("duration_text") or "",
            narrative_first_chapter=chapter,
            reader_known_since_chapter=record.get("reader_known_since_chapter") or chapter,
            story_discovery_time_text=record.get("story_discovery_time_text") or "",
            story_discovery_confidence=_clamp_confidence(record.get("story_discovery_confidence"), 0.0),
            boundary_confidence=_clamp_confidence(record.get("boundary_confidence"), 0.5),
            identity_confidence=confidence,
            merge_confidence=0.0,
            source_session=source_session,
        )
        self._attach(landmark_id, event_id, record, chapter, confidence, "created")
        return landmark_id, "created"

    def _attach(
        self,
        landmark_id: int,
        event_id: int,
        record: dict,
        chapter: int,
        confidence: float,
        decision: str,
    ) -> None:
        link_type = str(record.get("landmark_link_type") or "occurrence")
        is_context_link = link_type in {"commemoration", "historical_reference", "recurrence_instance"}
        self.db.link_event_to_landmark(
            landmark_id,
            event_id,
            link_type=link_type,
            confidence=confidence,
            evidence=str(record.get("identity_evidence") or record.get("summary") or ""),
            recurring_template_reference=str(record.get("recurrence_template_reference") or ""),
        )
        self.db.update_event_landmark_metadata(event_id, landmark_id, record)
        if is_context_link:
            self.db.record_landmark_resolution_evidence(
                event_id,
                landmark_id,
                chapter,
                decision="linked_context",
                identity_confidence=confidence,
                merge_confidence=0.0,
                supporting_evidence=str(record.get("identity_evidence") or record.get("summary") or ""),
                signals={"link_type": link_type, "reference": record.get("landmark_reference")},
            )
            self.db.refresh_event_search_terms(event_id)
            return
        default_name = str(record.get("landmark_name") or "").strip()
        if default_name:
            self.db.add_landmark_name(
                landmark_id,
                default_name,
                name_role="canonical" if record.get("name_status") == "named" else "public",
                name_source_type=str(record.get("name_source_type") or "unknown"),
                audience_type="reader",
                framing_polarity=str(record.get("framing_polarity") or "neutral"),
                literal_status=str(record.get("literal_status") or "literal"),
                first_known_chapter=record.get("reader_known_since_chapter") or chapter,
                narrative_order=chapter,
                confidence=confidence,
                evidence=str(record.get("name_evidence") or record.get("identity_evidence") or ""),
            )
        for name in record.get("landmark_names", []) or []:
            if isinstance(name, str):
                name = {"name": name}
            if not isinstance(name, dict):
                continue
            self.db.add_landmark_name(
                landmark_id,
                str(name.get("name") or name.get("label") or ""),
                name_role=str(name.get("name_role") or "public"),
                name_source_type=str(name.get("name_source_type") or "unknown"),
                audience_type=str(name.get("audience_type") or "reader"),
                source_entity_text=str(name.get("source_entity") or ""),
                faction_text=str(name.get("faction") or ""),
                framing_polarity=str(name.get("framing_polarity") or "neutral"),
                literal_status=str(name.get("literal_status") or "literal"),
                first_known_chapter=name.get("first_known_chapter") or chapter,
                narrative_order=chapter,
                confidence=_clamp_confidence(name.get("confidence"), confidence),
                evidence=str(name.get("evidence") or ""),
                status=str(name.get("status") or "accepted"),
            )
        assertions = {
            "state": record.get("event_state"),
            "reliability": record.get("event_reliability"),
            "visibility": record.get("reader_visibility"),
            "outcome": record.get("outcome"),
            "historical_memory": record.get("historical_memory"),
        }
        for assertion_type, value in assertions.items():
            if value and value != "unknown":
                self.db.add_landmark_assertion(
                    landmark_id,
                    assertion_type,
                    str(value),
                    chapter=chapter,
                    story_time_text=str(record.get("story_discovery_time_text") or ""),
                    source_event_id=event_id,
                    confidence=confidence,
                    evidence=str(record.get("summary") or ""),
                )
        for function in record.get("event_functions", []) or []:
            self.db.add_landmark_assertion(
                landmark_id,
                "function",
                str(function),
                chapter=chapter,
                source_event_id=event_id,
                confidence=confidence,
                evidence=str(record.get("summary") or ""),
            )
        for perspective in record.get("perspectives", []) or []:
            if isinstance(perspective, str):
                perspective = {"summary": perspective}
            if not isinstance(perspective, dict):
                continue
            self.db.add_landmark_perspective(
                landmark_id,
                str(perspective.get("summary") or ""),
                perspective_type=str(perspective.get("perspective_type") or "neutral"),
                source_entity_text=str(perspective.get("source_entity") or ""),
                faction_text=str(perspective.get("faction") or ""),
                chapter=chapter,
                reader_visibility=str(perspective.get("reader_visibility") or record.get("reader_visibility") or "partially_known"),
                reliability=str(perspective.get("reliability") or record.get("event_reliability") or "unknown"),
                confidence=_clamp_confidence(perspective.get("confidence"), confidence),
                evidence=str(perspective.get("evidence") or ""),
            )
        for dimension, score in (record.get("importance") or {}).items():
            self.db.add_landmark_importance(
                landmark_id,
                str(dimension),
                score,
                chapter=chapter,
                confidence=confidence,
                evidence=str(record.get("summary") or ""),
            )
        self.db.record_landmark_resolution_evidence(
            event_id,
            landmark_id,
            chapter,
            decision=decision,
            identity_confidence=confidence,
            merge_confidence=confidence if decision != "created" else 0.0,
            supporting_evidence=str(record.get("identity_evidence") or record.get("summary") or ""),
            signals={"landmark_type": record.get("landmark_type"), "reference": record.get("landmark_reference")},
        )
        self.db.refresh_event_search_terms(event_id)
