"""Serializable image occurrence descriptors.

The descriptor is the adapter boundary: it contains source occurrence details
but no parser conclusions. Raw bytes are intentionally excluded from its JSON
representation so chapter evidence remains portable and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageDescriptor:
    source_locator: str
    member_path: str
    chapter_index: int
    document_item_id: str
    occurrence_order: int
    mime_type: str = "application/octet-stream"
    image_hash: str = ""
    perceptual_hash: str = ""
    caption_text: str = ""
    alt_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_bytes: bytes | None = field(default=None, repr=False, compare=False)
    extraction_error: str = ""

    def to_dict(self) -> dict:
        return {
            "source_locator": self.source_locator,
            "member_path": self.member_path,
            "chapter_index": int(self.chapter_index),
            "document_item_id": self.document_item_id,
            "occurrence_order": int(self.occurrence_order),
            "mime_type": self.mime_type,
            "image_hash": self.image_hash,
            "perceptual_hash": self.perceptual_hash,
            "caption_text": self.caption_text,
            "alt_text": self.alt_text,
            "metadata": dict(self.metadata or {}),
            "extraction_error": self.extraction_error,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "ImageDescriptor":
        return cls(
            source_locator=str(value.get("source_locator", "")),
            member_path=str(value.get("member_path", "")),
            chapter_index=int(value.get("chapter_index", 0) or 0),
            document_item_id=str(value.get("document_item_id", "")),
            occurrence_order=int(value.get("occurrence_order", 0) or 0),
            mime_type=str(value.get("mime_type", "application/octet-stream")),
            image_hash=str(value.get("image_hash", "")),
            perceptual_hash=str(value.get("perceptual_hash", "")),
            caption_text=str(value.get("caption_text", "")),
            alt_text=str(value.get("alt_text", "")),
            metadata=dict(value.get("metadata") or {}),
            extraction_error=str(value.get("extraction_error", "")),
        )
