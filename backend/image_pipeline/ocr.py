"""Optional PaddleOCR adapter."""

from __future__ import annotations

import importlib.util
import io

from .diagnostics import diagnostic


def extract_ocr(raw_bytes: bytes | None) -> tuple[dict, list[dict]]:
    empty = {"text": "", "blocks": [], "confidence": 0.0, "engine": ""}
    if not raw_bytes:
        return empty, [diagnostic("ocr", "skipped", "no_image_bytes")]
    if not importlib.util.find_spec("paddleocr") or not importlib.util.find_spec("PIL"):
        return empty, [
            diagnostic("ocr", "degraded", "optional_dependency_unavailable", "PaddleOCR or Pillow is unavailable")
        ]
    try:
        import numpy as np
        from PIL import Image
        from paddleocr import PaddleOCR

        image = np.array(Image.open(io.BytesIO(raw_bytes)).convert("RGB"))
        engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = engine.ocr(image, cls=True) or []
        lines: list[str] = []
        blocks: list[dict] = []
        scores: list[float] = []
        for page in result:
            for item in page or []:
                bounds, pair = item[0], item[1]
                text, confidence = str(pair[0]), float(pair[1])
                lines.append(text)
                scores.append(confidence)
                blocks.append({"kind": "text", "text": text, "confidence": confidence, "bounds": bounds})
        confidence = sum(scores) / len(scores) if scores else 0.0
        return {
            "text": "\n".join(lines),
            "blocks": blocks,
            "confidence": round(confidence, 4),
            "engine": "PaddleOCR",
        }, [diagnostic("ocr", "ok", "ocr_complete", lines=len(lines))]
    except Exception as exc:
        return empty, [diagnostic("ocr", "degraded", "ocr_exception", type(exc).__name__)]
