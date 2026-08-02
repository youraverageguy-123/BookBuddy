"""Operational exact-image cache boundary."""

from __future__ import annotations


class ImageParseCache:
    def __init__(self, db=None):
        self.db = db

    @staticmethod
    def key(image_hash: str, parser_fingerprint: str) -> str:
        return f"{image_hash}:{parser_fingerprint}" if image_hash and parser_fingerprint else ""

    def get(self, image_hash: str, parser_fingerprint: str) -> dict | None:
        if self.db is None or not self.key(image_hash, parser_fingerprint):
            return None
        return self.db.get_image_parse_cache(image_hash, parser_fingerprint)

    def put(self, image_hash: str, parser_fingerprint: str, artifact: dict) -> None:
        if self.db is None or not self.key(image_hash, parser_fingerprint):
            return
        self.db.put_image_parse_cache(image_hash, parser_fingerprint, artifact)
