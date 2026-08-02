"""Build a small redistributable EPUB fixture for image-pipeline tests."""

from __future__ import annotations

import base64
from pathlib import Path

from ebooklib import epub


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def build_image_fixture(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image_chapter = """<html><head><title>Images</title></head><body>
<h1>Images</h1>
<p>This fixture chapter contains enough ordinary narrative text to pass the
production content-item heuristic. The travelers study the old road, compare
the river crossings, mark the eastern gate, and discuss which route is safest.
Their conversation continues while the illustrations remain independent source
evidence. Nothing in this paragraph establishes an identity, relationship, or
canonical location from an image alone. The remaining words keep this document
representative of a short but valid reading-order chapter.</p>
<figure><img src="images/shared.png" alt="Map of Eastwatch"/><figcaption>Eastwatch map</figcaption></figure>
<img src="images/shared.png" alt="Repeated map"/>
<img src="images/ornament.png" alt="chapter ornament"/>
<img src="images/missing.png" alt="Missing member"/>
</body></html>"""
    empty_chapter = """<html><head><title>No Images</title></head><body>
<h1>No Images</h1><p>This chapter intentionally contains no images, but it
still contains enough narrative prose to enter the normal chapter lifecycle.
The party leaves before sunrise, follows the quiet road beyond the village,
rests beside the river, and reaches the next settlement near dusk. They speak
about weather, provisions, distant hills, and the work awaiting them tomorrow.
This ordinary passage verifies that adding image evidence does not change or
break chapters whose source documents contain text only.</p>
</body></html>"""

    book = epub.EpubBook()
    book.set_identifier("bookbuddy-image-fixture")
    book.set_title("BookBuddy Image Fixture")
    book.set_language("en")
    book.add_author("BookBuddy Tests")
    chapter_images = epub.EpubHtml(
        uid="chapter-images", file_name="chapter-images.xhtml", title="Images", content=image_chapter
    )
    chapter_empty = epub.EpubHtml(
        uid="chapter-empty", file_name="chapter-empty.xhtml", title="No Images", content=empty_chapter
    )
    shared = epub.EpubItem(
        uid="shared", file_name="images/shared.png", media_type="image/png", content=_PNG
    )
    ornament = epub.EpubItem(
        uid="ornament", file_name="images/ornament.png", media_type="image/png", content=_PNG
    )
    for item in (chapter_images, chapter_empty, shared, ornament, epub.EpubNcx()):
        book.add_item(item)
    book.toc = (chapter_images, chapter_empty)
    book.spine = [chapter_images, chapter_empty]
    epub.write_epub(str(target), book, {})
    return target


def _navigation_document(uid: str, file_name: str, title: str, short: bool = False) -> epub.EpubHtml:
    prose = "Short publisher note." if short else (
        "This fixture document contains enough ordinary reading text to enter the production spine parser. "
        "Its sentences describe a quiet journey, a distant city, changing weather, careful plans, old roads, "
        "trusted companions, and the choices awaiting them after sunrise. The wording is deliberately neutral "
        "and repeated only to make this redistributable EPUB structurally representative for navigation tests. "
        "Readers continue through the landscape while each page remains independently addressable from the table "
        "of contents and from the publication spine without establishing any application-specific title behavior."
    )
    return epub.EpubHtml(uid=uid, file_name=file_name, title=title, content=f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>{prose}</p></body></html>")


def build_omnibus_navigation_fixture(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("bookbuddy-navigation-omnibus")
    book.set_title("Two Tales Omnibus")
    book.set_language("en")
    book.add_author("Test Author")

    def constituent(prefix: str, label: str, first_title: str):
        cover = _navigation_document(f"{prefix}-cover", f"{prefix}/cover.xhtml", "Cover")
        title = _navigation_document(f"{prefix}-title", f"{prefix}/title.xhtml", "Title Page")
        copyright_page = _navigation_document(f"{prefix}-copyright", f"{prefix}/copyright.xhtml", "Copyright")
        contents = _navigation_document(f"{prefix}-contents", f"{prefix}/contents.xhtml", "Contents")
        part = _navigation_document(f"{prefix}-part", f"{prefix}/part-1.xhtml", "Part I")
        first = _navigation_document(f"{prefix}-chapter-1", f"{prefix}/chapter-1.xhtml", first_title)
        second = _navigation_document(f"{prefix}-chapter-2", f"{prefix}/chapter-2.xhtml", "2: The Return")
        titled = _navigation_document(f"{prefix}-chapter-3", f"{prefix}/chapter-3.xhtml", "A New Road")
        micro = _navigation_document(f"{prefix}-micro", f"{prefix}/micro.xhtml", "Publisher Note", short=True)
        root = epub.Section(label, href=cover.file_name)
        toc = (root, (cover, title, copyright_page, contents, (epub.Section("Part I", href=part.file_name), (first, second, titled)), micro))
        return [cover, title, copyright_page, contents, part, first, second, titled, micro], toc

    first_items, first_toc = constituent("one", "[Two Tales 01] • First Tale by Test Author", "1: Departure")
    second_items, second_toc = constituent("two", "[Two Tales 02] • Second Tale by Test Author", "Chapter 1: Arrival")
    unlisted = _navigation_document("one-unlisted", "one/unlisted.xhtml", "Unlisted Interlude")
    for item in (*first_items, unlisted, *second_items, epub.EpubNcx(), epub.EpubNav()):
        book.add_item(item)
    book.toc = (first_toc, second_toc)
    book.spine = ["nav", *first_items, unlisted, *second_items]
    epub.write_epub(str(target), book, {})
    return target


def build_single_part_navigation_fixture(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("bookbuddy-navigation-single")
    book.set_title("One Novel")
    book.set_language("en")
    book.add_author("Test Author")
    first_part = _navigation_document("part-one", "text/part-one.xhtml", "Part I")
    first_chapter = _navigation_document("chapter-one", "text/chapter-one.xhtml", "Chapter 1: Beginning")
    second_part = _navigation_document("part-two", "text/part-two.xhtml", "Part II")
    second_chapter = _navigation_document("chapter-two", "text/chapter-two.xhtml", "Chapter 2: Continuing")
    for item in (first_part, first_chapter, second_part, second_chapter, epub.EpubNcx(), epub.EpubNav()):
        book.add_item(item)
    book.toc = (
        (epub.Section("Part I", href=first_part.file_name), (first_chapter,)),
        (epub.Section("Part II", href=second_part.file_name), (second_chapter,)),
    )
    book.spine = ["nav", first_part, first_chapter, second_part, second_chapter]
    epub.write_epub(str(target), book, {})
    return target
