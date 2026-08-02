from __future__ import annotations

from pathlib import Path

from storage_security import validate_epub_archive


DEFAULT_MAX_MEMBERS = 20_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 250.0


def discover_epub(library_dir: str | Path, minimum_chapters: int = 1) -> tuple[Path, object]:
    from epub_parser import parse_epub
    import logging

    candidates = []
    errors = []
    parser_logger = logging.getLogger("epub_parser")
    previous_level = parser_logger.level
    parser_logger.setLevel(logging.WARNING)
    try:
        for path in sorted(Path(library_dir).rglob("*.epub")):
            try:
                validate_epub_archive(path)
                parsed = parse_epub(str(path))
                if len(parsed.chapters) >= minimum_chapters:
                    candidates.append((len(parsed.chapters), path.stat().st_size, path, parsed))
            except Exception as exc:
                errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    finally:
        parser_logger.setLevel(previous_level)
    if not candidates:
        raise RuntimeError(f"No valid EPUB with at least {minimum_chapters} chapters was found; errors={errors[:5]}")
    _chapters, _size, path, parsed = max(candidates, key=lambda item: (item[0], item[1], str(item[2])))
    return path.resolve(), parsed


def select_canary_chapters(chapters: list, limit: int = 5) -> list[int]:
    substantive = [item for item in chapters if getattr(item, "word_count", 0) >= 50]
    pool = substantive or list(chapters)
    if not pool:
        return []
    choices = [
        pool[0],
        pool[len(pool) // 2],
        max(pool, key=lambda item: (getattr(item, "word_count", 0), -getattr(item, "index", 0))),
        max(pool, key=lambda item: (len(getattr(item, "image_descriptors", []) or []), getattr(item, "word_count", 0))),
        pool[-1],
    ]
    result = []
    for chapter in choices:
        index = int(getattr(chapter, "index"))
        if index not in result:
            result.append(index)
    return result[:limit]
