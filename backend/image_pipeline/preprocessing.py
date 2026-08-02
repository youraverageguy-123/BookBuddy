"""Optional local image preprocessing with graceful degradation."""

from __future__ import annotations

import importlib.util
import io

from .diagnostics import diagnostic


def preprocess_image(raw_bytes: bytes | None) -> tuple[bytes | None, list[dict]]:
    diagnostics: list[dict] = []
    if not raw_bytes:
        return None, [diagnostic("preprocessing", "skipped", "no_image_bytes")]
    if not importlib.util.find_spec("cv2") or not importlib.util.find_spec("PIL"):
        return raw_bytes, [
            diagnostic("preprocessing", "degraded", "optional_dependency_unavailable", "OpenCV or Pillow is unavailable")
        ]
    try:
        import cv2
        import numpy as np
        from PIL import Image

        with Image.open(io.BytesIO(raw_bytes)) as image:
            rgb = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, 9, 7, 21)
        processed = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            9,
        )
        output = io.BytesIO()
        Image.fromarray(processed).save(output, format="PNG")
        diagnostics.append(diagnostic("preprocessing", "ok", "local_threshold_complete"))
        return output.getvalue(), diagnostics
    except Exception as exc:
        diagnostics.append(
            diagnostic("preprocessing", "degraded", "preprocessing_exception", type(exc).__name__)
        )
        return raw_bytes, diagnostics
