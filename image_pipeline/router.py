"""Category-to-plugin router."""

from __future__ import annotations

from .parsers import (
    DiagramParser,
    FamilyTreeParser,
    GlyphParser,
    HandwrittenParser,
    MapParser,
    PortraitParser,
    SymbolParser,
    TableParser,
    TimelineParser,
    UnknownParser,
)


class ImageRouter:
    def __init__(self):
        unknown = UnknownParser()
        diagram = DiagramParser()
        symbol = SymbolParser()
        self._routes = {
            "UNKNOWN": unknown,
            "DECORATION": unknown,
            "PORTRAIT": PortraitParser(),
            "MAP": MapParser(),
            "FAMILY_TREE": FamilyTreeParser(),
            "TABLE": TableParser(),
            "DIAGRAM": diagram,
            "TIMELINE": TimelineParser(),
            "SYMBOL": symbol,
            "HERALDRY": symbol,
            "HANDWRITTEN": HandwrittenParser(),
            "PAGE_SCAN": HandwrittenParser(),
            "FICTIONAL_ALPHABET": GlyphParser(),
            "MIXED": diagram,
        }

    def plugin_for(self, category: str):
        return self._routes.get(str(category or "UNKNOWN").upper(), self._routes["UNKNOWN"])

    def parse(self, category: str, *, ocr: dict, metadata: dict) -> dict:
        return self.plugin_for(category).parse(ocr=ocr, metadata=metadata)

    @property
    def mapping(self) -> dict[str, str]:
        return {category: plugin.name for category, plugin in self._routes.items()}
