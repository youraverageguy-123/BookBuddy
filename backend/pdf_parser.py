"""PDF import: turn a text PDF into the same ``ParsedBook`` shape EPUBs use.

Chapters come from the PDF outline (bookmarks) when it has one, otherwise from
fixed-size page ranges.  Each chapter's ``spine_href`` is ``page-<n>`` where
``n`` is its first page (1-based); the reader uses that to jump and to map the
page being read back to a chapter.

pypdf is an optional dependency, imported only when a PDF is actually opened.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re

from epub_parser import NavigationBook, NavigationEntry, ParsedBook, RawChapter, _quote_safe_chunks

logger = logging.getLogger(__name__)

PAGES_PER_FALLBACK_CHAPTER = 12
MAX_PDF_PAGES = 5000
_PDF_SIGNATURE = b"%PDF-"


class PdfSupportUnavailable(RuntimeError):
    """Raised when the optional pypdf package is not installed."""


def _reader(path: Path):
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise PdfSupportUnavailable(
            "PDF support is not installed. Run: python backend/dependency_manager.py --pdf --install"
        ) from exc
    return PdfReader(str(path))


def validate_pdf_file(path: str | Path) -> dict:
    """Cheap structural checks before a PDF is accepted into the library."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    with source.open("rb") as handle:
        head = handle.read(1024)
    if _PDF_SIGNATURE not in head:
        raise ValueError("File is not a valid PDF")
    try:
        reader = _reader(source)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")
        pages = len(reader.pages)
    except PdfSupportUnavailable:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF could not be read") from exc
    if pages < 1:
        raise ValueError("PDF has no pages")
    if pages > MAX_PDF_PAGES:
        raise ValueError(f"PDF has too many pages: {pages}")
    return {"pages": pages, "path": str(source.resolve())}


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    # Re-join words hyphenated across a line break, then unwrap single line breaks.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    paragraphs = [" ".join(block.split()) for block in re.split(r"\n\s*\n", text)]
    return "\n\n".join(block for block in paragraphs if block)


def _metadata_text(value) -> str:
    return " ".join(str(value or "").split())


def _outline_starts(reader) -> list[tuple[int, str]]:
    """Top-level outline entries as (0-based page index, title), in page order."""
    try:
        outline = reader.outline
    except Exception:
        return []
    starts: dict[int, str] = {}
    for item in outline:
        if isinstance(item, list):
            continue  # nested entries belong to the preceding top-level chapter
        try:
            page_index = reader.get_destination_page_number(item)
        except Exception:
            continue
        title = _metadata_text(getattr(item, "title", ""))
        if page_index is None or page_index < 0 or not title:
            continue
        starts.setdefault(int(page_index), title[:200])
    return sorted(starts.items())


def _chapter_ranges(page_count: int, outline: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """(first page index, last page index, title) for every chapter."""
    if len(outline) >= 2:
        ranges: list[tuple[int, int, str]] = []
        if outline[0][0] > 0:
            ranges.append((0, outline[0][0] - 1, "Front matter"))
        for position, (start, title) in enumerate(outline):
            end = outline[position + 1][0] - 1 if position + 1 < len(outline) else page_count - 1
            ranges.append((start, max(start, end), title))
        return ranges
    ranges = []
    for start in range(0, page_count, PAGES_PER_FALLBACK_CHAPTER):
        end = min(start + PAGES_PER_FALLBACK_CHAPTER, page_count) - 1
        label = f"Page {start + 1}" if start == end else f"Pages {start + 1}–{end + 1}"
        ranges.append((start, end, label))
    return ranges


def pdf_metadata_fields(path: str | Path) -> dict[str, object]:
    """Title, author, and page count; never extracts page text."""
    try:
        reader = _reader(Path(path))
        info = reader.metadata
        fields = {
            "book_title": _metadata_text(getattr(info, "title", "")) or None,
            "author": _metadata_text(getattr(info, "author", "")) or None,
            "page_count": len(reader.pages),
        }
        return {key: value for key, value in fields.items() if value not in (None, "")}
    except Exception:
        return {}


def parse_pdf(pdf_path: str) -> ParsedBook:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    reader = _reader(path)
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported")

    info = reader.metadata
    title = _metadata_text(getattr(info, "title", "")) or path.stem
    author = _metadata_text(getattr(info, "author", "")) or "Unknown"
    page_count = len(reader.pages)

    page_text: list[str] = []
    for page in reader.pages:
        try:
            page_text.append(_clean_text(page.extract_text() or ""))
        except Exception:  # one unreadable page must not lose the book
            page_text.append("")

    outline = _outline_starts(reader)
    from_outline = len(outline) >= 2
    parsed = ParsedBook(title=title, author=author, epub_path=str(path))
    entries: list[NavigationEntry] = []
    for index, (start, end, chapter_title) in enumerate(_chapter_ranges(page_count, outline)):
        content = "\n\n".join(text for text in page_text[start:end + 1] if text)
        href = f"page-{start + 1}"
        parsed.chapters.append(RawChapter(
            index=index,
            title=chapter_title,
            book_name=title,
            content=content,
            html_content="",
            word_count=len(content.split()),
            item_id=f"pdf-pages-{start + 1}-{end + 1}",
            spine_href=href,
            section_type="CHAPTER" if chapter_title != "Front matter" else "FRONT_BACK_MATTER",
            section_confidence=0.8 if from_outline else 0.4,
            chapter_title_confidence=0.9 if from_outline else 0.2,
            chapter_boundary_confidence=0.8 if from_outline else 0.2,
            quote_safe_chunks=_quote_safe_chunks(content),
        ))
        entries.append(NavigationEntry(
            entry_id=f"pdf-{index}", title=chapter_title, spine_href=href, depth=0,
            kind="front_matter" if chapter_title == "Front matter" else "chapter", chapter_index=index,
        ))
    parsed.total_chapters = len(parsed.chapters)
    parsed.navigation_books = [NavigationBook(
        # The reader contract numbers books from 1.
        book_id="pdf", title=title, source_title=title, ordinal=1, entries=entries,
        start_chapter_index=0 if entries else None, end_chapter_index=len(entries) - 1 if entries else None,
    )]
    if not any(chapter.word_count for chapter in parsed.chapters):
        logger.warning("PDF has no extractable text (scanned images?): %s", path.name)
    logger.info("PDF parsed: %s pages, %s chapters", page_count, parsed.total_chapters)
    return parsed


def page_ranges(book: ParsedBook) -> list[dict]:
    """Chapter page ranges recovered from the item ids, for the reader."""
    ranges = []
    for chapter in book.chapters:
        match = re.fullmatch(r"pdf-pages-(\d+)-(\d+)", str(getattr(chapter, "item_id", "")))
        if match:
            ranges.append({"index": chapter.index, "start_page": int(match.group(1)), "end_page": int(match.group(2))})
    return ranges
