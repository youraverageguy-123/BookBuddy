import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment
from pathlib import Path
from dataclasses import dataclass, field
from hashlib import sha1
from urllib.parse import unquote
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
    spine_href: str = ""
    section_type: str ="UNKNOWN"
    section_confidence: float = 0.5
    chapter_title_confidence: float = 0.5
    front_back_matter_reason: str = ""
    chapter_boundary_confidence: float = 0.5
    quote_safe_chunks: list[str] = field(default_factory=list)
    image_descriptors: list[ImageDescriptor] = field(default_factory=list)
    image_diagnostics: list[dict] = field(default_factory=list)

@dataclass
class NavigationEntry:
    entry_id: str
    title: str
    spine_href: str
    depth: int
    kind: str
    display_number: str | None = None
    chapter_index: int | None = None

@dataclass
class NavigationBook:
    book_id: str
    title: str
    source_title: str
    ordinal: int
    entries: list[NavigationEntry] = field(default_factory=list)
    start_chapter_index: int | None = None
    end_chapter_index: int | None = None

@dataclass
class ParsedBook:
    title: str
    author: str
    epub_path: str
    chapters: list = field(default_factory=list)
    total_chapters: int = 0
    navigation_mode: str = "single"
    navigation_books: list[NavigationBook] = field(default_factory=list)

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

def _is_content_item(text: str, item_id: str, file_name: str, min_words: int = 50, has_visual_content: bool = False) -> bool:
    """
    PRESERVATION HEURISTIC:
    Only reject items that are practically empty or undeniable legal noise.
    Keep all lore, appendices, dramatis personae, and recaps.
    """
    if len(text.split()) < min_words and not has_visual_content:
        return False
        
    text_preview = text[:1000].lower()
    if "project gutenberg" in text_preview and "license" in text_preview:
        return False
        
    if "cover" in file_name.lower() and len(text.split()) < 20:
        return False

    return True


def _normalize_href(href: str | None) -> str:
    value = unquote(str(href or "").split("#", 1)[0]).replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    return value.casefold()


def _toc_node(item, depth: int = 0, path: tuple[int, ...] = ()) -> dict | None:
    children = []
    source = item
    if isinstance(item, tuple):
        source, raw_children = item
        for index, child in enumerate(raw_children):
            node = _toc_node(child, depth + 1, (*path, index))
            if node:
                children.append(node)
    if not isinstance(source, (epub.Link, epub.Section)):
        return None
    return {
        "title": " ".join(str(getattr(source, "title", "") or "Untitled").split()),
        "href": str(getattr(source, "href", "") or "").split("#", 1)[0],
        "depth": depth,
        "path": path,
        "children": children,
    }


def _toc_tree(items) -> list[dict]:
    if isinstance(items, (epub.Link, epub.Section)):
        items = (items,)
    result = []
    for index, item in enumerate(items or ()):
        node = _toc_node(item, 0, (index,))
        if node:
            result.append(node)
    return result


def _flatten_nodes(nodes: list[dict], include_roots: bool = True) -> list[dict]:
    result = []
    for node in nodes:
        if include_roots:
            result.append(node)
        result.extend(_flatten_nodes(node["children"], include_roots=True))
    return result


def _spine_positions(node: dict, spine_lookup: dict[str, int]) -> list[int]:
    positions = []
    for current in _flatten_nodes([node]):
        position = spine_lookup.get(_normalize_href(current["href"]))
        if position is not None:
            positions.append(position)
    return sorted(set(positions))


def _href_namespace(hrefs: list[str]) -> str:
    split = [_normalize_href(href).split("/") for href in hrefs if _normalize_href(href)]
    if not split:
        return ""
    shared = []
    for parts in zip(*split):
        if len(set(parts)) != 1:
            break
        shared.append(parts[0])
    return "/".join(shared[:-1] if shared and "." in shared[-1] else shared)


def _looks_like_structural_part(title: str) -> bool:
    return bool(re.match(r"^\s*(part|section)\s+(?:\d+|[ivxlcdm]+)\b", title, re.IGNORECASE))


def _detect_omnibus_roots(tree: list[dict], spine_lookup: dict[str, int]) -> list[dict]:
    candidates = [node for node in tree if node["children"]]
    if len(candidates) < 2 or all(_looks_like_structural_part(node["title"]) for node in candidates):
        return []
    ranges = []
    namespaces = []
    repeated_matter = 0
    for node in candidates:
        positions = _spine_positions(node, spine_lookup)
        if len(positions) < 3:
            return []
        ranges.append((positions[0], positions[-1]))
        descendants = _flatten_nodes(node["children"])
        namespaces.append(_href_namespace([item["href"] for item in descendants]))
        titles = " ".join(item["title"].casefold() for item in descendants)
        signals = sum(marker in titles for marker in ("cover", "title page", "copyright", "contents"))
        repeated_matter += signals >= 2
    if any(ranges[index][0] <= ranges[index - 1][1] for index in range(1, len(ranges))):
        return []
    distinct_namespaces = bool(all(namespaces)) and len(set(namespaces)) == len(namespaces)
    repeated_book_matter = repeated_matter >= max(2, (len(candidates) + 1) // 2)
    return candidates if distinct_namespaces or repeated_book_matter else []


def _clean_book_title(source_title: str) -> str:
    title = " ".join(source_title.split())
    title = re.sub(r"^\[[^\]]*(?:\d+|[ivxlcdm]+)[^\]]*\]\s*[•·|:\-]*\s*", "", title, flags=re.IGNORECASE)
    if "•" in title:
        left, right = (part.strip() for part in title.split("•", 1))
        if right and (not left or re.search(r"(?:\d+|[ivxlcdm]+)\b", left, re.IGNORECASE)):
            title = right
    title = re.sub(r"\s+by\s+[\wÀ-ž'’., -]{2,80}$", "", title, flags=re.IGNORECASE).strip(" -•·|")
    return title or source_title


def _entry_kind(title: str, has_children: bool, depth: int) -> str:
    lowered = title.casefold().strip()
    if re.match(r"^(part|section|volume)\s+(?:\d+|[ivxlcdm]+)\b", lowered):
        return "part"
    if any(marker in lowered for marker in ("cover", "title page", "copyright", "contents", "table of contents", "dedication", "map", "chart", "dramatis", "story so far", "glossary")):
        return "front_matter"
    if any(marker in lowered for marker in ("acknowledg", "about the author", "other books", "also by", "excerpt from", "what.s next")):
        return "back_matter"
    if re.match(r"^(?:chapter\s+)?(?:\d+|[ivxlcdm]+)\s*(?::|[.\-–—]|$)", title, re.IGNORECASE):
        return "chapter"
    if any(marker in lowered for marker in ("prologue", "epilogue", "interlude", "prelude")):
        return "story"
    if has_children:
        return "part"
    return "chapter" if depth >= 2 else "other"


def _explicit_display_number(title: str) -> str | None:
    match = re.match(r"^\s*(?:chapter\s+)?(\d+|[ivxlcdm]+)\s*(?::|[.\-–—]|$)", title, re.IGNORECASE)
    return match.group(1) if match else None


def _stable_navigation_id(prefix: str, ordinal: int, href: str) -> str:
    digest = sha1(f"{ordinal}:{_normalize_href(href)}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{ordinal}-{digest}"


def _navigation_entry(node: dict, ordinal: int, base_depth: int, story_ordinal: int) -> tuple[NavigationEntry, int]:
    kind = _entry_kind(node["title"], bool(node["children"]), int(node["depth"]))
    display_number = _explicit_display_number(node["title"])
    if kind == "chapter":
        story_ordinal += 1
        display_number = display_number or str(story_ordinal)
    return NavigationEntry(
        entry_id=_stable_navigation_id("entry", ordinal, node["href"]),
        title=node["title"],
        spine_href=node["href"],
        depth=max(0, int(node["depth"]) - base_depth),
        kind=kind,
        display_number=display_number,
    ), story_ordinal

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
    
    def _build_toc_map(items, current_book="", depth=0):
        if isinstance(items, (epub.Link, epub.Section)):
            items = (items,)
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
                    
                # Only the top-level section denotes a constituent book in an
                # omnibus. Nested sections such as Part I must stay inside it.
                _build_toc_map(children, current_book=section_title if depth == 0 else current_book, depth=depth + 1)

    _build_toc_map(book.toc, current_book=book_title)
    
    # ── Walk spine in reading order ───────────
    spine_ids = [item_id for item_id, _ in book.spine]

    spine_items = []
    for item_id in spine_ids:
        item = book.get_item_with_id(item_id)
        if item is None:
            logger.warning(f"Spine references missing item id: {item_id}")
        elif item.get_type() == ebooklib.ITEM_DOCUMENT:
            spine_items.append((item_id, item))
    spine_lookup = {_normalize_href(item.get_name()): index for index, (_, item) in enumerate(spine_items)}
    toc_tree = _toc_tree(book.toc)
    toc_nodes = _flatten_nodes(toc_tree)
    navigation_toc_map = {_normalize_href(node["href"]): node["title"] for node in toc_nodes if node["href"]}
    omnibus_roots = _detect_omnibus_roots(toc_tree, spine_lookup)

    navigation_books = []
    ownership_starts = []
    if omnibus_roots:
        for ordinal, root in enumerate(omnibus_roots, start=1):
            positions = _spine_positions(root, spine_lookup)
            source_title = root["title"]
            nav_book = NavigationBook(
                book_id=_stable_navigation_id("book", ordinal, root["href"]),
                title=_clean_book_title(source_title),
                source_title=source_title,
                ordinal=ordinal,
            )
            story_ordinal = 0
            for entry_ordinal, node in enumerate(_flatten_nodes(root["children"]), start=1):
                entry, story_ordinal = _navigation_entry(node, entry_ordinal, 1, story_ordinal)
                nav_book.entries.append(entry)
            navigation_books.append(nav_book)
            ownership_starts.append((positions[0], nav_book))
    else:
        nav_book = NavigationBook(
            book_id=_stable_navigation_id("book", 1, toc_tree[0]["href"] if toc_tree else ""),
            title=book_title,
            source_title=book_title,
            ordinal=1,
        )
        story_ordinal = 0
        for entry_ordinal, node in enumerate(toc_nodes, start=1):
            entry, story_ordinal = _navigation_entry(node, entry_ordinal, 0, story_ordinal)
            nav_book.entries.append(entry)
        navigation_books.append(nav_book)
        ownership_starts.append((0, nav_book))

    parsed = ParsedBook(
        title=book_title,
        author=book_author,
        epub_path=str(path),
        navigation_mode="omnibus" if omnibus_roots else "single",
        navigation_books=navigation_books,
    )

    chapter_index = 0

    chapter_book_ids = {}
    for spine_position, (item_id, item) in enumerate(spine_items):

        html_bytes = item.get_content()
        html_text = html_bytes.decode("utf-8", errors="replace") if isinstance(html_bytes, bytes) else str(html_bytes)
        soup       = BeautifulSoup(html_text, "html.parser")
        plain_text = _clean_html(html_bytes)
        logger.debug(plain_text[:200])

        file_name = item.get_name()

        has_visual_content = soup.find(["img", "svg", "video", "canvas"]) is not None
        if not _is_content_item(plain_text, item_id, file_name, has_visual_content=has_visual_content):
            logger.debug(f"Skipping non-story item: {item_id}")
            continue

        official_title = navigation_toc_map.get(_normalize_href(file_name))
        owner = ownership_starts[0][1]
        for start_position, candidate in ownership_starts:
            if start_position > spine_position:
                break
            owner = candidate
        sub_book_name = owner.source_title if parsed.navigation_mode == "omnibus" else book_title

        extracted_title = official_title if official_title else _extract_title(soup, chapter_index)
        
        # ── CLASSIFICATION PIPELINE ──
        title_lower = extracted_title.lower()
        section_type = "CHAPTER"
        section_confidence = 0.65
        front_back_matter_reason = ""
        chapter_boundary_confidence = 0.7
        if has_visual_content and len(plain_text.split()) < 50:
            section_type = "VISUAL_PAGE"
            section_confidence = 0.9
            chapter_boundary_confidence = 0.8
        
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
            spine_href = file_name,
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
        chapter_book_ids[chapter_index] = owner.book_id
        logger.info(
            f"  [{chapter_index + 1:03d}] "
            f"{chapter.title[:55]:<55} "
            f"{chapter.word_count:>6} words"
        )
        chapter_index += 1

    chapter_by_href = {_normalize_href(chapter.spine_href): chapter.index for chapter in parsed.chapters}
    for nav_book in parsed.navigation_books:
        owned = [chapter.index for chapter in parsed.chapters if chapter_book_ids.get(chapter.index) == nav_book.book_id]
        nav_book.start_chapter_index = min(owned) if owned else None
        nav_book.end_chapter_index = max(owned) if owned else None
        for entry in nav_book.entries:
            entry.chapter_index = chapter_by_href.get(_normalize_href(entry.spine_href))

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
