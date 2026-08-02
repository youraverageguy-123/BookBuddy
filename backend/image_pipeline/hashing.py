"""Exact and optional perceptual hashes for image evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import io


def exact_hash(raw_bytes: bytes | None) -> str:
    return hashlib.sha256(raw_bytes or b"").hexdigest() if raw_bytes is not None else ""


def perceptual_hash(raw_bytes: bytes | None) -> tuple[str, str]:
    """Return a near-duplicate hint without making it a cache identity."""
    if not raw_bytes:
        return "", "no_image_bytes"
    if not importlib.util.find_spec("imagehash") or not importlib.util.find_spec("PIL"):
        return "", "ImageHash_or_Pillow_unavailable"
    try:
        import imagehash
        from PIL import Image

        with Image.open(io.BytesIO(raw_bytes)) as image:
            return str(imagehash.phash(image.convert("RGB"))), ""
    except Exception as exc:  # Decode failures must not stop the chapter.
        return "", f"perceptual_hash_failed:{type(exc).__name__}"
