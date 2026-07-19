"""Isolated conservative parser plugins.

Every output is a candidate observation. No plugin resolves identity or writes
to graph state.
"""

from __future__ import annotations

from .base import ImageParserPlugin, empty_observations, ocr_lines


class UnknownParser(ImageParserPlugin):
    name = "unknown"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        observations = empty_observations()
        for line in ocr_lines(ocr):
            observations["literal_text"].append({
                "observation_type": "literal_text",
                "text": line,
                "source": "ocr",
                "confidence": float(ocr.get("confidence", 0.0)),
                "requires_corroboration": True,
            })
        return {"plugin": self.name, "plugin_version": self.version, "observations": observations, "semantic_confidence": 0.0}


class MapParser(UnknownParser):
    name = "map"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        for line in ocr_lines(ocr):
            result["observations"]["locations"].append({
                "observation_type": "location_label",
                "surface_text": line,
                "confidence": min(0.55, float(ocr.get("confidence", 0.0))),
                "requires_corroboration": True,
            })
        result["semantic_confidence"] = 0.35 if ocr_lines(ocr) else 0.0
        return result


class PortraitParser(UnknownParser):
    name = "portrait"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        result["observations"]["entities"].append({
            "observation_type": "unidentified_portrait",
            "identity": None,
            "confidence": 0.25,
            "requires_corroboration": True,
        })
        return result


class FamilyTreeParser(UnknownParser):
    name = "family_tree"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        lines = ocr_lines(ocr)
        if lines:
            result["observations"]["relationships"].append({
                "observation_type": "visual_relationship_structure",
                "node_labels": lines,
                "relationship_type": "unknown",
                "confidence": min(0.45, float(ocr.get("confidence", 0.0))),
                "requires_corroboration": True,
            })
        return result


class DiagramParser(UnknownParser):
    name = "diagram"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        result["observations"]["layout"].append({
            "observation_type": "diagram_layout",
            "text_block_count": len(ocr.get("blocks") or []),
            "requires_corroboration": True,
        })
        return result


class TableParser(DiagramParser):
    name = "table"


class SymbolParser(UnknownParser):
    name = "symbol"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        result["observations"]["symbols"].append({
            "observation_type": "unresolved_symbol",
            "confidence": 0.25,
            "requires_corroboration": True,
        })
        return result


class GlyphParser(UnknownParser):
    name = "glyph"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        for line in ocr_lines(ocr):
            result["observations"]["language"].append({
                "observation_type": "unresolved_writing_system",
                "surface_text": line,
                "writing_system": "unknown",
                "translation_status": "unresolved",
                "confidence": min(0.45, float(ocr.get("confidence", 0.0))),
                "requires_corroboration": True,
            })
        return result


class TimelineParser(UnknownParser):
    name = "timeline"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        result = super().parse(ocr=ocr, metadata=metadata)
        result["observations"]["timeline"].extend({
            "observation_type": "timeline_label",
            "text": line,
            "confidence": min(0.5, float(ocr.get("confidence", 0.0))),
            "requires_corroboration": True,
        } for line in ocr_lines(ocr))
        return result


class HandwrittenParser(UnknownParser):
    name = "handwritten"
