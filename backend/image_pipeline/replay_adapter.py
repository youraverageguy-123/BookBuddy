"""Conservative image-evidence adapter for deterministic graph replay."""

from __future__ import annotations

import hashlib
import json


def _clamp_confidence(value, ceiling: float = 0.6) -> float:
    try:
        return max(0.0, min(float(ceiling), float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _observation_key(chapter: int, evidence: dict) -> str:
    descriptor = evidence.get("descriptor") or {}
    payload = {
        "chapter": int(chapter),
        "image_hash": descriptor.get("image_hash", ""),
        "member_path": descriptor.get("member_path", ""),
        "occurrence_order": descriptor.get("occurrence_order", 0),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def ingest_image_evidence(payload: dict, chapter: int, db) -> dict:
    """Adapt stored observations without creating or resolving canonical truth.

    Literal occurrences are reviewable mention evidence. Location labels may
    link to an already-resolved location but never create one. Language labels
    enter the existing source-aware language evidence path. All other visual
    claims remain only in immutable chapter evidence.
    """
    summary = {
        "images": 0,
        "literal_mentions": 0,
        "linked_locations": 0,
        "reference_locations": 0,
        "language_observations": 0,
        "canonical_mutations": 0,
    }
    source_section_type = payload.get("_section_type") or "CHAPTER"
    for evidence in payload.get("image_evidence") or []:
        if not isinstance(evidence, dict):
            continue
        summary["images"] += 1
        descriptor = evidence.get("descriptor") or {}
        scene_scope = f"chapter:{int(chapter)}:epub_image:{descriptor.get('occurrence_order', 0)}"
        observations = evidence.get("observations") or {}

        for literal in observations.get("literal_text") or []:
            text = " ".join(str(literal.get("text", "")).split()) if isinstance(literal, dict) else ""
            if not text:
                continue
            db.add_mention_occurrence(
                text,
                int(chapter),
                confidence=_clamp_confidence(literal.get("confidence"), 0.6),
                source_quote=text,
                scene_scope=scene_scope,
                mention_source_type="epub_image",
                source_section_type=source_section_type,
            )
            summary["literal_mentions"] += 1

        for location in observations.get("locations") or []:
            if not isinstance(location, dict):
                continue
            surface = " ".join(str(location.get("surface_text", "")).split())
            if not surface:
                continue
            confidence = _clamp_confidence(location.get("confidence"), 0.55)
            resolution = db.resolve_entity_reference(surface, "LOCATION", int(chapter))
            linked_entity_id = resolution.get("entity_id") if resolution.get("state") == "resolved" else None
            db.add_mention_occurrence(
                surface,
                int(chapter),
                entity_type_guess="LOCATION",
                confidence=confidence,
                source_quote=surface,
                linked_entity_id=linked_entity_id,
                scene_scope=scene_scope,
                mention_source_type="epub_image",
                source_section_type=source_section_type,
            )
            if linked_entity_id:
                summary["linked_locations"] += 1
            else:
                db.record_reference_mention(
                    surface,
                    int(chapter),
                    entity_type_guess="LOCATION",
                    context_text=surface,
                    scene_scope=scene_scope,
                    source_section_type=source_section_type,
                    source_quote=surface,
                    evidence_roles=["epub_image", "visual_only"],
                )
                summary["reference_locations"] += 1

        for language in observations.get("language") or []:
            if not isinstance(language, dict):
                continue
            surface = " ".join(str(language.get("surface_text", "")).split())
            if not surface:
                continue
            db.record_language_observation(
                surface,
                chapter_idx=int(chapter),
                language=language.get("language", "unknown"),
                writing_system=language.get("writing_system", "unknown"),
                translation_status=language.get("translation_status", "unknown"),
                decoder_source="epub_image",
                confidence=_clamp_confidence(language.get("confidence"), 0.5),
                source_section_type=source_section_type,
                source_quote=surface,
            )
            summary["language_observations"] += 1

        db.record_resolver_decision(
            "image_evidence",
            "image_occurrence",
            _observation_key(chapter, evidence),
            int(chapter),
            "evidence_only",
            confidence=_clamp_confidence(
                (evidence.get("confidence_breakdown") or {}).get("overall"), 0.6
            ),
            supporting_evidence=[{
                "source": "epub_image",
                "image_hash": descriptor.get("image_hash", ""),
                "occurrence_order": descriptor.get("occurrence_order", 0),
                "category": evidence.get("category", "UNKNOWN"),
            }],
            rejected_alternatives=[
                "active_identity_creation", "alias_resolution", "life_status_mutation",
                "canonical_landmark_creation", "social_relationship_creation",
            ],
            visibility="engine",
            metadata={"adapter": "epub_image", "canonical_mutations": 0},
        )
    return summary
