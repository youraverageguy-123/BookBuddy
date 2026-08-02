"""Image evidence pipeline orchestration."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json

from config import (
    IMAGE_EVIDENCE_SCHEMA_VERSION,
    IMAGE_GEMINI_FALLBACK_ENABLED,
    IMAGE_GEMINI_FALLBACK_MODEL,
    IMAGE_GEMINI_VISION_PROMPT_VERSION,
    IMAGE_LOCAL_CONFIDENCE_THRESHOLD,
    IMAGE_PARSER_VERSION,
)

from .cache import ImageParseCache
from .classifier import ImageClassifier
from .descriptor import ImageDescriptor
from .diagnostics import diagnostic, failure_state
from .evidence_builder import build_image_evidence
from .fallback import maybe_run_fallback
from .ocr import extract_ocr
from .preprocessing import preprocess_image
from .router import ImageRouter
from .parsers.base import empty_observations


def _module_version(module_name: str) -> str:
    if not importlib.util.find_spec(module_name):
        return "unavailable"
    distribution = {"PIL": "Pillow", "cv2": "opencv-python"}.get(module_name, module_name)
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        module = importlib.import_module(module_name)
        return str(getattr(module, "__version__", "present"))


def parser_fingerprint() -> str:
    router = ImageRouter()
    contract = {
        "schema": IMAGE_EVIDENCE_SCHEMA_VERSION,
        "parser": IMAGE_PARSER_VERSION,
        "confidence_threshold": IMAGE_LOCAL_CONFIDENCE_THRESHOLD,
        "fallback_enabled": bool(IMAGE_GEMINI_FALLBACK_ENABLED),
        "fallback_model": IMAGE_GEMINI_FALLBACK_MODEL if IMAGE_GEMINI_FALLBACK_ENABLED else "disabled",
        "fallback_prompt": IMAGE_GEMINI_VISION_PROMPT_VERSION if IMAGE_GEMINI_FALLBACK_ENABLED else "disabled",
        "router": router.mapping,
        "dependencies": {
            "Pillow": _module_version("PIL"),
            "ImageHash": _module_version("imagehash"),
            "OpenCV": _module_version("cv2"),
            "PaddleOCR": _module_version("paddleocr"),
        },
    }
    serialized = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_independent_artifact(descriptor: ImageDescriptor) -> dict:
    """Build the cacheable decode/OCR artifact for a non-decorative image.

    The occurrence classifier has already selected this route before this
    function runs.  This artifact intentionally keeps only visual signals and
    source-independent parser output so identical bytes can be reused without
    leaking a previous caption, chapter, or document path into a new
    occurrence.
    """
    diagnostics: list[dict] = []
    visual = ImageClassifier().classify_visual(descriptor).to_dict()
    processed, preprocessing_diagnostics = preprocess_image(descriptor.raw_bytes)
    diagnostics.extend(preprocessing_diagnostics)
    ocr, ocr_diagnostics = extract_ocr(processed)
    diagnostics.extend(ocr_diagnostics)
    state = {"state": "none", "stage": "", "code": "", "recoverable": True}
    # The adapter has already isolated extraction/decode failures.  Preserve
    # that state in immutable evidence rather than treating a corrupt image as
    # a successful empty parse.
    if not descriptor.raw_bytes:
        state = failure_state("extraction", "no_image_bytes")
    return {
        "visual_classification": visual,
        "ocr": ocr,
        "diagnostics": diagnostics,
        "failure_state": state,
        "provenance": {
            "parser_version": IMAGE_PARSER_VERSION,
            "ocr_engine": ocr.get("engine", ""),
            "source_independent": True,
        },
    }


def _occurrence_parse(
    descriptor: ImageDescriptor,
    artifact: dict,
    classification: dict,
    occurrence_diagnostics: list[dict] | None = None,
    fallback_callable=None,
    vision_authorized: bool = False,
    vision_consent_callback=None,
) -> dict:
    diagnostics = list(occurrence_diagnostics or []) + list(artifact.get("diagnostics") or [])
    ocr = artifact.get("ocr") or {"text": "", "blocks": [], "confidence": 0.0, "engine": ""}
    category = classification["category"]
    router = ImageRouter()
    try:
        plugin_output = router.parse(category, ocr=ocr, metadata=descriptor.metadata)
        diagnostics.append(diagnostic("router", "ok", "plugin_complete", plugin=plugin_output.get("plugin", "unknown")))
    except Exception as exc:
        plugin_output = router.parse("UNKNOWN", ocr=ocr, metadata=descriptor.metadata)
        diagnostics.append(diagnostic("parser", "degraded", "plugin_exception", type(exc).__name__))

    observations = plugin_output.get("observations") or {}
    if category != "DECORATION":
        for source, text, confidence in (
            ("caption", descriptor.caption_text, 0.85),
            ("alt_text", descriptor.alt_text, 0.8),
        ):
            literal = " ".join(str(text or "").split())
            if literal:
                observations.setdefault("literal_text", []).append({
                    "observation_type": "literal_text",
                    "text": literal,
                    "source": source,
                    "confidence": confidence,
                    "requires_corroboration": False,
                })

    semantic_confidence = float(plugin_output.get("semantic_confidence", 0.0) or 0.0)
    ocr_confidence = float(ocr.get("confidence", 0.0) or 0.0)
    classification_confidence = float(classification.get("confidence", 0.0) or 0.0)
    layout_confidence = ocr_confidence if ocr.get("blocks") else 0.0
    overall = round(max(
        classification_confidence * 0.45 + ocr_confidence * 0.35 + semantic_confidence * 0.2,
        0.5 if descriptor.caption_text or descriptor.alt_text else 0.0,
    ), 4)
    fallback, fallback_diagnostics = maybe_run_fallback(
        descriptor,
        classification,
        overall,
        enabled=IMAGE_GEMINI_FALLBACK_ENABLED and vision_authorized,
        threshold=IMAGE_LOCAL_CONFIDENCE_THRESHOLD,
        fallback_callable=fallback_callable,
        authorized=vision_authorized,
        authorization_callback=vision_consent_callback,
    )
    diagnostics.extend(fallback_diagnostics)
    if fallback:
        observations.setdefault("fallback", []).append({
            "observation_type": "fallback_candidate",
            "payload": fallback,
            "requires_corroboration": True,
        })
        fallback_observations = fallback.get("observations") if isinstance(fallback, dict) else None
        if isinstance(fallback_observations, dict):
            for bucket, candidates in fallback_observations.items():
                if bucket not in observations or not isinstance(candidates, list):
                    continue
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    normalized = dict(candidate)
                    normalized["source"] = "gemini_vision"
                    normalized["requires_corroboration"] = True
                    try:
                        normalized["confidence"] = min(0.6, max(0.0, float(normalized.get("confidence", 0.0))))
                    except (TypeError, ValueError):
                        normalized["confidence"] = 0.0
                    observations[bucket].append(normalized)
    state = dict(artifact.get("failure_state") or {})
    if descriptor.extraction_error or not descriptor.raw_bytes:
        state = failure_state("extraction", descriptor.extraction_error or "no_image_bytes")
    if category == "DECORATION":
        state = {"state": "ignored", "stage": "router", "code": "decorative_asset", "recoverable": True}
    return {
        "category": category,
        "subcategory": classification.get("subcategory", "unknown"),
        "classification": classification,
        "ocr": ocr,
        "layout": {"blocks": ocr.get("blocks") or []},
        "observations": observations,
        "confidence_breakdown": {
            "ocr": round(ocr_confidence, 4),
            "classification": round(classification_confidence, 4),
            "layout": round(layout_confidence, 4),
            "semantic_parser": round(semantic_confidence, 4),
            "overall": overall,
        },
        "diagnostics": diagnostics,
        "provenance": {
            **dict(artifact.get("provenance") or {}),
            "plugin": plugin_output.get("plugin", "unknown"),
            "plugin_version": plugin_output.get("plugin_version", ""),
            "fallback_model": IMAGE_GEMINI_FALLBACK_MODEL if fallback else "",
            "fallback_model_version": fallback.get("source_model_version", "") if isinstance(fallback, dict) else "",
            "fallback_key_id": fallback.get("source_key_id", "") if isinstance(fallback, dict) else "",
            "fallback_reason": fallback.get("source_reason", "") if isinstance(fallback, dict) else "",
        },
        "failure_state": state,
    }


def parse_chapter_images(
    descriptors: list[ImageDescriptor],
    db=None,
    fallback_callable=None,
    allow_ai_vision_fallback: bool = False,
    vision_consent_callback=None,
) -> list[dict]:
    """Parse ordered image occurrences; Vision needs explicit caller consent."""
    fingerprint = parser_fingerprint()
    cache = ImageParseCache(db)
    evidence: list[dict] = []
    for descriptor in sorted(descriptors or [], key=lambda item: int(item.occurrence_order)):
        artifact = None
        cache_status = "not_cacheable"
        occurrence_diagnostics: list[dict] = []
        occurrence_diagnostics.append(
            diagnostic(
                "extraction",
                "degraded" if descriptor.extraction_error else "ok",
                descriptor.extraction_error or "descriptor_ready",
            )
        )
        occurrence_diagnostics.append(
            diagnostic(
                "hashing",
                "ok" if descriptor.image_hash else "degraded",
                "exact_hash_ready" if descriptor.image_hash else "exact_hash_unavailable",
            )
        )
        # Classification must choose the route before preprocessing or OCR.
        # Context is occurrence-specific, so it never becomes part of the
        # source-independent exact-image cache artifact.
        try:
            classification = ImageClassifier().classify(descriptor).to_dict()
            occurrence_diagnostics.append(
                diagnostic("classification", "ok", "classification_complete")
            )
        except Exception as exc:
            classification = {
                "category": "UNKNOWN",
                "subcategory": "unknown",
                "confidence": 0.0,
                "reason": "classification_exception",
            }
            occurrence_diagnostics.append(
                diagnostic("classification", "degraded", "classification_exception", type(exc).__name__)
            )
        if classification["category"] == "DECORATION":
            artifact = {
                "visual_classification": classification,
                "ocr": {"text": "", "blocks": [], "confidence": 0.0, "engine": ""},
                "diagnostics": [diagnostic("router", "ignored", "decorative_asset")],
                "failure_state": {
                    "state": "ignored",
                    "stage": "router",
                    "code": "decorative_asset",
                    "recoverable": True,
                },
                "provenance": {
                    "parser_version": IMAGE_PARSER_VERSION,
                    "source_independent": False,
                    "ocr_skipped": True,
                },
            }
            cache_status = "skipped_decoration"
        elif descriptor.image_hash:
            try:
                artifact = cache.get(descriptor.image_hash, fingerprint)
                cache_status = "exact_hash_hit" if artifact is not None else "exact_hash_miss"
                occurrence_diagnostics.append(
                    diagnostic("cache", "ok", cache_status)
                )
            except Exception as exc:
                cache_status = "cache_read_failed"
                artifact = None
                occurrence_diagnostics.append(
                    diagnostic("cache", "degraded", "cache_read_exception", type(exc).__name__)
                )
        else:
            occurrence_diagnostics.append(
                diagnostic("cache", "skipped", "exact_hash_unavailable")
            )
        if artifact is None:
            try:
                artifact = _source_independent_artifact(descriptor)
            except Exception as exc:
                artifact = {
                    "visual_classification": {"category": "UNKNOWN", "subcategory": "unknown", "confidence": 0.0, "reason": "pipeline_exception"},
                    "ocr": {"text": "", "blocks": [], "confidence": 0.0, "engine": ""},
                    "diagnostics": [diagnostic("parser", "failed", "pipeline_exception", type(exc).__name__)],
                    "failure_state": failure_state("parser", "pipeline_exception"),
                    "provenance": {"parser_version": IMAGE_PARSER_VERSION, "source_independent": True},
                }
            if descriptor.image_hash:
                try:
                    cache.put(descriptor.image_hash, fingerprint, artifact)
                    occurrence_diagnostics.append(
                        diagnostic("cache", "ok", "cache_write_complete")
                    )
                except Exception as exc:
                    occurrence_diagnostics.append(
                        diagnostic("cache", "degraded", "cache_write_exception", type(exc).__name__)
                    )
        try:
            occurrence = _occurrence_parse(
                descriptor,
                artifact,
                classification,
                occurrence_diagnostics=occurrence_diagnostics,
                fallback_callable=fallback_callable if allow_ai_vision_fallback else None,
                vision_authorized=allow_ai_vision_fallback,
                vision_consent_callback=vision_consent_callback,
            )
        except Exception as exc:
            occurrence = {
                "category": "UNKNOWN", "subcategory": "unknown",
                "classification": {"category": "UNKNOWN", "subcategory": "unknown", "confidence": 0.0, "reason": "occurrence_exception"},
                "ocr": {"text": "", "blocks": [], "confidence": 0.0, "engine": ""},
                "layout": {"blocks": []}, "observations": empty_observations(),
                "confidence_breakdown": {"ocr": 0.0, "classification": 0.0, "layout": 0.0, "semantic_parser": 0.0, "overall": 0.0},
                "diagnostics": [diagnostic("evidence", "failed", "occurrence_exception", type(exc).__name__)],
                "provenance": {"parser_version": IMAGE_PARSER_VERSION},
                "failure_state": failure_state("evidence", "occurrence_exception"),
            }
        built = build_image_evidence(descriptor, occurrence, fingerprint, cache_status)
        built.setdefault("diagnostics", []).append(
            diagnostic("evidence", "ok", "evidence_built")
        )
        evidence.append(built)
    return evidence
