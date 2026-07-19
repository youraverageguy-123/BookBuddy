"""Evidence-only image parsing shared by EPUB and future document adapters."""

from .descriptor import ImageDescriptor
from .evidence_builder import build_image_evidence
from .parser import parse_chapter_images, parser_fingerprint
from .router import ImageRouter

__all__ = [
    "ImageDescriptor", "ImageRouter", "build_image_evidence",
    "parse_chapter_images", "parser_fingerprint",
]
