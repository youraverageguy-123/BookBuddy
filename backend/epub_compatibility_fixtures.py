"""Generated, redistributable EPUB compatibility fixtures for pre-v1 gates."""
from __future__ import annotations

import base64
from pathlib import Path
from ebooklib import epub

_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
_PROSE = " ".join((
    "The reader follows a quiet road beyond the village while the morning light moves across the hills.",
    "This generated passage contains ordinary narrative language, stable punctuation, and enough words for the production chapter heuristic.",
    "It exists only to verify import, spine order, title recovery, search text, and cleanup without relying on a copyrighted title.",
) * 3)


def _book(name: str, language: str = "en") -> epub.EpubBook:
    book = epub.EpubBook()
    book.set_identifier(f"bookbuddy-{name}")
    book.set_title(f"BookBuddy {name.replace('-', ' ').title()} Fixture")
    book.set_language(language)
    book.add_author("BookBuddy Tests")
    return book


def build_compatibility_fixtures(root: str | Path) -> dict[str, Path]:
    target = Path(root); target.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}

    variants = {
        "reflowable_epub3": ("en", f"<h1>Chapter One</h1><p>{_PROSE}</p><table><tr><th>A</th><td>B</td></tr></table><ol><li>One</li></ol>"),
        "poetry_heavy_css": ("en", f"<style>p.drop::first-letter{{float:left;font-size:3em}} .small{{font-variant:small-caps}} table{{width:100%}}</style><h1>Poetry</h1><p class='drop'>{_PROSE}</p><pre>First line\n  Indented line\nLast line</pre>"),
        "rtl": ("ar", f"<html dir='rtl'><body><h1>RTL</h1><p>{_PROSE}</p></body></html>"),
        "missing_toc": ("en", f"<h1>Recovered From Spine</h1><p>{_PROSE}</p>"),
        "broken_html_css": ("en", f"<style>p{{color:var(--missing); broken-rule</style><h1>Recovered Markup<p>{_PROSE}<b>still readable"),
    }
    for name, (language, body) in variants.items():
        book = _book(name, language)
        chapter = epub.EpubHtml(uid="chapter", file_name="chapter.xhtml", title=name, content=f"<html><body>{body}</body></html>")
        book.add_item(chapter); book.add_item(epub.EpubNcx()); book.spine = [chapter]
        if name != "missing_toc": book.toc = (chapter,)
        path = target / f"{name}.epub"; epub.write_epub(str(path), book, {}); results[name] = path

    fixed = _book("fixed-layout")
    fixed.add_metadata("OPF", "meta", "pre-paginated", {"property": "rendition:layout"})
    image = epub.EpubItem(uid="page-image", file_name="images/page.png", media_type="image/png", content=_PNG)
    page = epub.EpubHtml(uid="page", file_name="page.xhtml", title="Visual Page", content="<html><body><img src='images/page.png' alt='Generated visual page'/></body></html>")
    fixed.add_item(image); fixed.add_item(page); fixed.add_item(epub.EpubNcx()); fixed.toc = (page,); fixed.spine = [page]
    fixed_path = target / "fixed_layout.epub"; epub.write_epub(str(fixed_path), fixed, {}); results["fixed_layout"] = fixed_path
    return results
