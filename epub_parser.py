import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment
from pathlib import Path
from dataclasses import dataclass, field
import re
import logging
import unicodedata

from image_pipeline.adapters import extract_epub_image_descriptors
from image_pipeline.descriptor import ImageDescriptor

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────

@dataclass
class RawChapter:
    index: int
    title: str
    book_name: str
    content: str
    html_content: str
    word_count: int
    item_id: str
    section_type: str ="UNKNOWN"
    section_confidence: float = 0.5
    chapter_title_confidence: float = 0.5
    front_back_matter_reason: str = ""
    chapter_boundary_confidence: float = 0.5
    quote_safe_chunks: list[str] = field(default_factory=list)
    image_descriptors: list[ImageDescriptor] = field(default_factory=list)
    image_diagnostics: list[dict] = field(default_factory=list)

@dataclass
class ParsedBook:
    title: str
    author: str
    epub_path: str
    chapters: list = field(default_factory=list)
    total_chapters: int = 0

# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _clean_html(html_content: bytes) -> str:
    html_text = html_content.decode("utf-8", errors="replace") if isinstance(html_content, bytes) else str(html_content)
    soup = BeautifulSoup(html_text, "html.parser")

    # Nuke HTML comments to prevent leaks
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove noise elements
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    for tag in soup.find_all(["sup", "aside"]):
        class_text = " ".join(tag.get("class", [])).lower()
        role_text = str(tag.get("role", "")).lower()
        if any(marker in class_text or marker in role_text for marker in ("footnote", "note", "endnote")):
            tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"(?m)^\s*\d+\s*$", "", text)

    lines = [line.strip() for line in text.splitlines()]
    counts = {}
    for line in lines:
        if 0 < len(line) <= 80:
            counts[line] = counts.get(line, 0) + 1
    repeated_noise = {line for line, count in counts.items() if count >= 3}
    lines = [line for line in lines if line not in repeated_noise]
    text = "\n".join(lines)

    # Collapse runs of blank lines and spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    return text.strip()

def _extract_title(soup: BeautifulSoup, fallback_index: int) -> str:
    candidates = []
    
    # 1. Standard headers
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        heading = soup.find(tag)
        if heading:
            candidates.append(heading.get_text(strip=True))
            
    # 2. Class-based headers
    class_keywords = ["chapter", "title", "heading", "prologue", "epilogue", "interlude"]
    title_elements = soup.find_all(class_=lambda x: x and any(k in str(x).lower() for k in class_keywords))
    for el in title_elements:
        candidates.append(el.get_text(strip=True))

    # 3. Fallback to Document Title
    title_tag = soup.find("title")
    if title_tag:
        candidates.append(title_tag.get_text(strip=True))

    # Evaluate candidates for "sanity"
    for text in candidates:
        if not text:
            continue
        
        clean_text = "".join(c for c in unicodedata.normalize("NFKC", text) if c.isalnum() or c in " -.,'!?")
        clean_text = " ".join(clean_text.split()) 
        
        if clean_text.strip().lower() in ["chapter", "part", "section"]:
            continue
            
        if len(clean_text) > 2:
            return clean_text
            
    return f"Chapter {fallback_index + 1}"


def _title_confidence(official_title: str | None, extracted_title: str) -> float:
    if official_title:
        return 0.95
    lowered = extracted_title.lower()
    if lowered.startswith("chapter ") or any(word in lowered for word in ("prologue", "epilogue", "interlude")):
        return 0.8
    return 0.6 if extracted_title else 0.25


def _quote_safe_chunks(text: str, max_chunks: int = 8, max_chars: int = 900) -> list[str]:
    chunks = []
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = " ".join(paragraph.split())
        if len(paragraph) < 80:
            continue
        chunks.append(paragraph[:max_chars])
        if len(chunks) >= max_chunks:
            break
    return chunks

def _is_content_item(text: str, item_id: str, file_name: str, min_words: int = 50) -> bool:
    """
    PRESERVATION HEURISTIC:
    Only reject items that are practically empty or undeniable legal noise.
    Keep all lore, appendices, dramatis personae, and recaps.
    """
    if len(text.split()) < min_words:
        return False
        
    text_preview = text[:1000].lower()
    if "project gutenberg" in text_preview and "license" in text_preview:
        return False
        
    if "cover" in file_name.lower() and len(text.split()) < 20:
        return False

    return True

# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def parse_epub(epub_path: str) -> ParsedBook:
    path = Path(epub_path)

    if not path.exists():
        raise FileNotFoundError(f"EPUB not found: {epub_path}")
    if path.suffix.lower() != ".epub":
        raise ValueError(f"Not an EPUB file: {epub_path}")

    logger.info(f"Loading: {path.name}")
    book = epub.read_epub(str(path))

    # ── Metadata ──────────────────────────────
    title_meta  = book.get_metadata("DC", "title")
    author_meta = book.get_metadata("DC", "creator")

    book_title  = title_meta[0][0]  if title_meta  else path.stem
    book_author = author_meta[0][0] if author_meta else "Unknown"

    logger.info(f"'{book_title}' by {book_author}")
    
    # ── Map TOC Titles & Book Boundaries ──────
    toc_map = {}
    
    def _build_toc_map(items, current_book=""):
        for item in items:
            if isinstance(item, epub.Link):
                base_href = item.href.split('#')[0]
                toc_map[base_href] = {"book": current_book, "title": item.title}
            elif isinstance(item, epub.Section):
                base_href = item.href.split('#')[0] if item.href else ""
                if base_href:
                    toc_map[base_href] = {"book": current_book, "title": item.title}
            elif isinstance(item, tuple):
                section, children = item
                section_title = section.title if hasattr(section, 'title') else current_book
                
                if hasattr(section, 'href') and section.href:
                    base_href = section.href.split('#')[0]
                    toc_map[base_href] = {"book": current_book, "title": section_title}
                    
                _build_toc_map(children, current_book=section_title)

    _build_toc_map(book.toc, current_book=book_title)
    
    # ── Walk spine in reading order ───────────
    spine_ids = [item_id for item_id, _ in book.spine]

    parsed = ParsedBook(
        title=book_title,
        author=book_author,
        epub_path=str(path),
    )

    chapter_index = 0

    for item_id in spine_ids:
        item = book.get_item_with_id(item_id)

        if item is None:
            logger.warning(f"Spine references missing item id: {item_id}")
            continue

        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        html_bytes = item.get_content()
        html_text = html_bytes.decode("utf-8", errors="replace") if isinstance(html_bytes, bytes) else str(html_bytes)
        soup       = BeautifulSoup(html_text, "html.parser")
        plain_text = _clean_html(html_bytes)
        logger.debug(plain_text[:200])

        file_name = item.get_name()

        if not _is_content_item(plain_text, item_id, file_name):
            logger.debug(f"Skipping non-story item: {item_id}")
            continue

        toc_info = toc_map.get(file_name, {})
        official_title = toc_info.get("title")
        sub_book_name = toc_info.get("book", book_title)

        extracted_title = official_title if official_title else _extract_title(soup, chapter_index)
        
        # ── CLASSIFICATION PIPELINE ──
        title_lower = extracted_title.lower()
        section_type = "CHAPTER"
        section_confidence = 0.65
        front_back_matter_reason = ""
        chapter_boundary_confidence = 0.7
        
        total_words = len(plain_text.split())
        link_words = sum(len(a.get_text().split()) for a in soup.find_all("a"))
        hyperlink_density = link_words / total_words if total_words > 0 else 0.0
        
        lore_keywords = ["appendix", "glossary", "dramatis", "characters", "story so far", "cast of characters", "who's who"]
        paratext_keywords = [
            "copyright", "acknowledgment", "acknowledgements", "dedication",
            "title page", "about the author", "footnote", "endnote", "notes",
            "bibliography", "works cited", "index"
        ]
        
        if hyperlink_density > 0.3 or any(w in title_lower for w in ["contents", "index", "table of contents"]):
            section_type = "FRONT_BACK_MATTER"
            section_confidence = 0.9
            front_back_matter_reason = "high hyperlink density or contents/index title"
            chapter_boundary_confidence = 0.5
        elif any(w in title_lower for w in lore_keywords):
            section_type = "LORE_SUPPLEMENT"
            section_confidence = 0.8
        elif any(w in title_lower for w in ["prologue", "epilogue", "interlude", "prelude"]):
            section_type = "STORY_EVENT"
            section_confidence = 0.85
            chapter_boundary_confidence = 0.85
        elif (
            any(w in title_lower for w in [
                *paratext_keywords
            ])
            or "all rights reserved" in plain_text[:1000].lower()
            or "isbn" in plain_text[:1000].lower()
        ):
            section_type = "FRONT_BACK_MATTER"
            section_confidence = 0.9
            front_back_matter_reason = "publishing metadata keyword"
            chapter_boundary_confidence = 0.45

        try:
            image_descriptors = extract_epub_image_descriptors(book, item, chapter_index, str(path))
            image_diagnostics = []
        except Exception as exc:
            # Image extraction is evidence-only and must never discard chapter text.
            logger.warning("Image extraction degraded for %s: %s", item_id, type(exc).__name__)
            image_descriptors = []
            image_diagnostics = [{
                "stage": "extraction",
                "status": "degraded",
                "code": "chapter_image_extraction_exception",
                "detail": type(exc).__name__,
                "recoverable": True,
            }]

        chapter = RawChapter(
            index      = chapter_index,
            title      = extracted_title,
            book_name  = sub_book_name,
            content    = plain_text,
            html_content= html_bytes.decode(errors="ignore"),
            word_count = len(plain_text.split()),
            item_id    = item_id,
            section_type= section_type,
            section_confidence= section_confidence,
            chapter_title_confidence= _title_confidence(official_title, extracted_title),
            front_back_matter_reason= front_back_matter_reason,
            chapter_boundary_confidence= chapter_boundary_confidence,
            quote_safe_chunks= _quote_safe_chunks(plain_text),
            image_descriptors=image_descriptors,
            image_diagnostics=image_diagnostics,
        )

        parsed.chapters.append(chapter)
        logger.info(
            f"  [{chapter_index + 1:03d}] "
            f"{chapter.title[:55]:<55} "
            f"{chapter.word_count:>6} words"
        )
        chapter_index += 1

    parsed.total_chapters = len(parsed.chapters)
    logger.info(f"Done — {parsed.total_chapters} chapters extracted")

    return parsed

# ─────────────────────────────────────────────
# Quick CLI test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python epub_parser.py <path_to_epub>")
        sys.exit(1)

    result = parse_epub(sys.argv[1])

    print(f"\n{'═' * 55}")
    print(f"  Title   : {result.title}")
    print(f"  Author  : {result.author}")
    print(f"  Chapters: {result.total_chapters}")
    print(f"{'═' * 55}")

    current_book_display = None
        
    for ch in result.chapters:
        if ch.book_name != current_book_display:
            print(f"\n▼ [{ch.book_name.upper()}]")
            current_book_display = ch.book_name
                
        print(f"    [{ch.index + 1:03d}] {ch.title[:35]:<35} | {ch.section_type:<18} | {ch.word_count:>6} words")

    if result.chapters:
        first_story_ch = next(
            (ch for ch in result.chapters if ch.section_type in ["CHAPTER", "STORY_EVENT"]), 
            result.chapters[0]
        )
        
        preview = first_story_ch.content[:500]
        print(f"\n── First story preview: {first_story_ch.title} ──\n{preview}\n...")
