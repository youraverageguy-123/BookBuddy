"""EPUB-specific image occurrence extraction.

This module is deliberately the only part of the pipeline that understands
ebooklib and XHTML paths. Parser modules receive ImageDescriptor instances.
"""

from __future__ import annotations

import importlib.util
import io
import mimetypes
import posixpath
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from .descriptor import ImageDescriptor
from .hashing import exact_hash, perceptual_hash


def _normal_path(path: str) -> str:
    value = unquote(str(path or "").split("#", 1)[0]).replace("\\", "/")
    return posixpath.normpath(value).lstrip("./")


def _resolve_member_path(document_path: str, source: str) -> str:
    # Do not normalize the source before it is joined to the XHTML member.
    # Normalizing "../images/map.png" first discards its parent traversal and
    # incorrectly makes it relative to the document's directory.
    source = unquote(str(source or "").split("#", 1)[0]).replace("\\", "/")
    if not source or source.startswith("data:"):
        return source
    return _normal_path(posixpath.join(posixpath.dirname(_normal_path(document_path)), source))


def _caption_for(image_tag) -> str:
    figure = image_tag.find_parent("figure")
    if figure:
        caption = figure.find("figcaption")
        if caption:
            return " ".join(caption.get_text(" ", strip=True).split())
    for sibling in (image_tag.find_previous_sibling(), image_tag.find_next_sibling()):
        if sibling and getattr(sibling, "name", "") in {"p", "figcaption", "caption"}:
            text = " ".join(sibling.get_text(" ", strip=True).split())
            if text:
                return text
    return ""


def _metadata(raw_bytes: bytes, mime_type: str) -> tuple[dict, str]:
    data = {"byte_size": len(raw_bytes or b""), "mime_type": mime_type or "application/octet-stream"}
    if not raw_bytes:
        return data, "empty_image_member"
    if not importlib.util.find_spec("PIL"):
        return data, "Pillow_unavailable"
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw_bytes)) as image:
            data.update({
                "width": int(image.width),
                "height": int(image.height),
                "format": image.format or "",
                "color_mode": image.mode or "",
                "dpi": list(image.info.get("dpi", ())) if image.info.get("dpi") else [],
                "transparency": bool(image.info.get("transparency") is not None),
                "animation": bool(getattr(image, "is_animated", False)),
            })
        return data, ""
    except Exception as exc:
        return data, f"image_metadata_failed:{type(exc).__name__}"


def extract_epub_image_descriptors(book, document_item, chapter_index: int, epub_path: str = "") -> list[ImageDescriptor]:
    """Extract all image occurrences from one EPUB document in XHTML order."""
    html_bytes = document_item.get_content()
    html_text = html_bytes.decode("utf-8", errors="replace") if isinstance(html_bytes, bytes) else str(html_bytes)
    soup = BeautifulSoup(html_text, "html.parser")
    document_path = document_item.get_name()
    member_items = {_normal_path(item.get_name()): item for item in book.get_items() if getattr(item, "get_name", None)}
    descriptors: list[ImageDescriptor] = []

    for occurrence_order, tag in enumerate(soup.find_all(["img", "image"]), start=1):
        source = tag.get("src") or tag.get("href") or tag.get("xlink:href") or ""
        member_path = _resolve_member_path(document_path, source)
        raw_bytes = b""
        mime_type = tag.get("type") or mimetypes.guess_type(member_path)[0] or "application/octet-stream"
        error = ""
        member = member_items.get(member_path)
        if not source:
            error = "image_source_missing"
        elif source.startswith("data:"):
            error = "data_uri_not_supported"
        elif member is None:
            error = "image_member_not_found"
        else:
            try:
                raw_bytes = member.get_content() or b""
                mime_type = getattr(member, "media_type", None) or mime_type
            except Exception as exc:
                error = f"image_member_read_failed:{type(exc).__name__}"
        metadata, metadata_error = _metadata(raw_bytes, mime_type)
        if metadata_error and not error:
            error = metadata_error
        perceptual, hash_error = perceptual_hash(raw_bytes)
        if hash_error and not error:
            error = hash_error
        descriptors.append(ImageDescriptor(
            source_locator=epub_path,
            member_path=member_path,
            chapter_index=chapter_index,
            document_item_id=str(getattr(document_item, "id", "") or ""),
            occurrence_order=occurrence_order,
            caption_text=_caption_for(tag),
            alt_text=" ".join(str(tag.get("alt", "")).split()),
            mime_type=mime_type,
            image_hash=exact_hash(raw_bytes) if raw_bytes else "",
            perceptual_hash=perceptual,
            metadata=metadata,
            raw_bytes=raw_bytes or None,
            extraction_error=error,
        ))
    return descriptors
