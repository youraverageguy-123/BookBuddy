"""Cheap image classification before OCR and semantic plugins."""

from __future__ import annotations

from dataclasses import dataclass

from .descriptor import ImageDescriptor


IMAGE_CATEGORIES = {
    "UNKNOWN", "DECORATION", "PORTRAIT", "MAP", "FAMILY_TREE", "TABLE",
    "DIAGRAM", "TIMELINE", "SYMBOL", "HERALDRY", "HANDWRITTEN", "PAGE_SCAN",
    "FICTIONAL_ALPHABET", "MIXED",
}


@dataclass(frozen=True)
class Classification:
    category: str
    subcategory: str
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 4),
            "reason": self.reason,
        }


_CONTEXT_PATTERNS = (
    ("FAMILY_TREE", "family_tree", ("family tree", "genealogy", "lineage", "pedigree")),
    ("MAP", "battle_map", ("battle map", "battlefield map")),
    ("MAP", "map", ("map", "atlas", "route", "territory")),
    ("TIMELINE", "timeline", ("timeline", "chronology")),
    ("TABLE", "chart", ("chart", "table")),
    ("DIAGRAM", "diagram", ("diagram", "flowchart", "schematic")),
    ("HERALDRY", "heraldry", ("coat of arms", "heraldry", "crest", "sigil")),
    ("FICTIONAL_ALPHABET", "glyph", ("glyph", "rune", "alphabet", "cipher")),
    ("HANDWRITTEN", "handwritten", ("handwritten", "handwriting", "manuscript")),
    ("PORTRAIT", "character_sheet", ("character sheet",)),
    ("PORTRAIT", "portrait", ("portrait",)),
    ("DECORATION", "chapter_ornament", ("ornament", "divider", "flourish")),
    ("MIXED", "captioned_illustration", ("illustration", "plate")),
)


class ImageClassifier:
    def classify_visual(self, descriptor: ImageDescriptor) -> Classification:
        metadata = descriptor.metadata or {}
        width = int(metadata.get("width", 0) or 0)
        height = int(metadata.get("height", 0) or 0)
        byte_size = int(metadata.get("byte_size", 0) or 0)
        if width and height and max(width, height) <= 160:
            return Classification("DECORATION", "small_asset", 0.72, "small_visual_asset")
        if width and height and width <= 120 and height >= width * 3:
            return Classification("DECORATION", "vertical_ornament", 0.62, "extreme_vertical_aspect")
        if width and height and height >= width * 1.35 and byte_size >= 4096:
            return Classification("PORTRAIT", "portrait", 0.42, "portrait_aspect_candidate")
        if width and height and width >= height * 1.8 and byte_size >= 4096:
            return Classification("DIAGRAM", "wide_visual", 0.38, "wide_visual_candidate")
        return Classification("UNKNOWN", "unknown", 0.2, "insufficient_visual_signal")

    def classify(self, descriptor: ImageDescriptor, visual: Classification | None = None) -> Classification:
        visual = visual or self.classify_visual(descriptor)
        source_text = " ".join(
            (descriptor.member_path, descriptor.caption_text, descriptor.alt_text)
        ).lower()
        for category, subcategory, needles in _CONTEXT_PATTERNS:
            if any(needle in source_text for needle in needles):
                return Classification(category, subcategory, 0.82, "epub_occurrence_context")
        return visual
