"""Build versioned occurrence evidence from source-independent parse artifacts."""

from __future__ import annotations

import copy

from config import IMAGE_EVIDENCE_SCHEMA_VERSION

from .descriptor import ImageDescriptor
from .parsers.base import empty_observations


def build_image_evidence(
    descriptor: ImageDescriptor,
    parse_output: dict,
    parser_fingerprint: str,
    cache_status: str,
) -> dict:
    evidence = copy.deepcopy(parse_output or {})
    observations = empty_observations()
    supplied_observations = evidence.get("observations") or {}
    for bucket in observations:
        candidates = supplied_observations.get(bucket) or []
        observations[bucket] = list(candidates) if isinstance(candidates, list) else []
    for bucket, candidates in supplied_observations.items():
        if bucket not in observations and isinstance(candidates, list):
            observations[bucket] = list(candidates)
    evidence["observations"] = observations
    evidence.setdefault("category", "UNKNOWN")
    evidence.setdefault("subcategory", "unknown")
    evidence.setdefault("ocr", {"text": "", "blocks": [], "confidence": 0.0, "engine": ""})
    evidence.setdefault("layout", {"blocks": []})
    evidence.setdefault("confidence_breakdown", {
        "ocr": 0.0,
        "classification": 0.0,
        "layout": 0.0,
        "semantic_parser": 0.0,
        "overall": 0.0,
    })
    evidence.setdefault("diagnostics", [])
    evidence.setdefault("provenance", {})
    evidence.setdefault("failure_state", {
        "state": "none", "stage": "", "code": "", "recoverable": True,
    })
    evidence.update({
        "image_evidence_schema_version": IMAGE_EVIDENCE_SCHEMA_VERSION,
        "descriptor": descriptor.to_dict(),
        "image_hash": descriptor.image_hash,
        "image_kind": evidence.get("category", "UNKNOWN"),
        "image_subkind": evidence.get("subcategory", "unknown"),
        "chapter_index": int(descriptor.chapter_index),
        "page_index": None,
        "source_type": "epub_image",
        "ocr_text": str((evidence.get("ocr") or {}).get("text", "")),
        "caption_text": descriptor.caption_text,
        "layout_blocks": list((evidence.get("layout") or {}).get("blocks") or []),
        "detected_entities": list((evidence.get("observations") or {}).get("entities") or []),
        "detected_locations": list((evidence.get("observations") or {}).get("locations") or []),
        "detected_relationships": list((evidence.get("observations") or {}).get("relationships") or []),
        "detected_symbols": list((evidence.get("observations") or {}).get("symbols") or []),
        "detected_language": "unknown",
        "translation_candidates": list((evidence.get("observations") or {}).get("translations") or []),
        "confidence": float((evidence.get("confidence_breakdown") or {}).get("overall", 0.0)),
        "parser_version": (evidence.get("provenance") or {}).get("parser_version", ""),
        "source_model": (evidence.get("provenance") or {}).get("fallback_model", ""),
        "source_model_version": (evidence.get("provenance") or {}).get("fallback_model_version", ""),
        "source_reason": (evidence.get("provenance") or {}).get("fallback_reason", ""),
        "parser_fingerprint": parser_fingerprint,
        "cache_status": cache_status,
    })
    return evidence
