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
    image_chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Images</title></head><body>
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
    empty_chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>No Images</title></head><body>
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
