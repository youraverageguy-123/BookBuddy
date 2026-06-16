import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment
from pathlib import Path
from dataclasses import dataclass, field
import re
import logging

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
    soup = BeautifulSoup(html_content, "html.parser")

    # Nuke HTML comments to prevent leaks
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove noise elements
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

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
        
        clean_text = "".join(c for c in text if c.isascii() and (c.isalnum() or c in " -.,'!?"))
        clean_text = " ".join(clean_text.split()) 
        
        if clean_text.strip().lower() in ["chapter", "part", "section"]:
            continue
            
        if len(clean_text) > 2:
            return clean_text
            
    return f"Chapter {fallback_index + 1}"

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
        soup       = BeautifulSoup(html_bytes, "html.parser")
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
        
        total_words = len(plain_text.split())
        link_words = sum(len(a.get_text().split()) for a in soup.find_all("a"))
        hyperlink_density = link_words / total_words if total_words > 0 else 0.0
        
        lore_keywords = ["appendix", "glossary", "dramatis", "characters", "story so far"]
        
        if hyperlink_density > 0.3 or any(w in title_lower for w in ["contents", "index", "table of contents"]):
            section_type = "FRONT_BACK_MATTER"
        elif any(w in title_lower for w in lore_keywords):
            section_type = "LORE_SUPPLEMENT"
        elif any(w in title_lower for w in ["prologue", "epilogue", "interlude", "prelude"]):
            section_type = "STORY_EVENT"
        elif (
            any(w in title_lower for w in [
                "copyright",
                "acknowledgment",
                "acknowledgements",
                "dedication",
                "title page",
                "about the author"
            ])
            or "all rights reserved" in plain_text[:1000].lower()
            or "isbn" in plain_text[:1000].lower()
        ):
            section_type = "FRONT_BACK_MATTER"

        chapter = RawChapter(
            index      = chapter_index,
            title      = extracted_title,
            book_name  = sub_book_name,
            content    = plain_text,
            html_content= html_bytes.decode(errors="ignore"),
            word_count = len(plain_text.split()),
            item_id    = item_id,
            section_type= section_type
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