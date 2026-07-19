"""Parser plugin contract."""

from __future__ import annotations


OBSERVATION_BUCKETS = (
    "literal_text", "entities", "locations", "relationships", "symbols",
    "language", "translations", "layout", "timeline",
)


def empty_observations() -> dict[str, list]:
    return {key: [] for key in OBSERVATION_BUCKETS}


class ImageParserPlugin:
    name = "unknown"
    version = "1"

    def parse(self, *, ocr: dict, metadata: dict) -> dict:
        return {
            "plugin": self.name,
            "plugin_version": self.version,
            "observations": empty_observations(),
            "semantic_confidence": 0.0,
        }


def ocr_lines(ocr: dict) -> list[str]:
    return [" ".join(line.split()) for line in str(ocr.get("text", "")).splitlines() if line.strip()]
