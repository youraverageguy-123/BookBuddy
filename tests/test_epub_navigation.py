import tempfile
import unittest
from pathlib import Path

from epub_parser import parse_epub
from epub_test_fixture import build_omnibus_navigation_fixture, build_single_part_navigation_fixture


class EpubNavigationTests(unittest.TestCase):
    def test_omnibus_uses_stable_book_ranges_and_local_numbers(self):
        with tempfile.TemporaryDirectory() as root:
            parsed = parse_epub(build_omnibus_navigation_fixture(Path(root, "omnibus.epub")))
        self.assertEqual("omnibus", parsed.navigation_mode)
        self.assertEqual(["First Tale", "Second Tale"], [book.title for book in parsed.navigation_books])
        self.assertEqual(2, len({chapter.book_name for chapter in parsed.chapters}))
        self.assertEqual("[Two Tales 01] • First Tale by Test Author", next(chapter.book_name for chapter in parsed.chapters if chapter.title == "Unlisted Interlude"))
        for nav_book in parsed.navigation_books:
            numbered = [entry for entry in nav_book.entries if entry.title.startswith(("1:", "Chapter 1:"))]
            self.assertEqual("1", numbered[0].display_number)
            self.assertIsNotNone(numbered[0].chapter_index)
            self.assertEqual(["Cover", "Title Page", "Copyright", "Contents"], [entry.title for entry in nav_book.entries[:4]])
            publisher_note = next(entry for entry in nav_book.entries if entry.title == "Publisher Note")
            self.assertIsNone(publisher_note.chapter_index)
        untitled = next(entry for entry in parsed.navigation_books[0].entries if entry.title == "A New Road")
        self.assertEqual("3", untitled.display_number)

    def test_parts_in_a_single_novel_are_not_detected_as_books(self):
        with tempfile.TemporaryDirectory() as root:
            parsed = parse_epub(build_single_part_navigation_fixture(Path(root, "single.epub")))
        self.assertEqual("single", parsed.navigation_mode)
        self.assertEqual(1, len(parsed.navigation_books))
        self.assertEqual("One Novel", parsed.navigation_books[0].title)
        self.assertEqual(["Part I", "Chapter 1: Beginning", "Part II", "Chapter 2: Continuing"], [entry.title for entry in parsed.navigation_books[0].entries])


if __name__ == "__main__":
    unittest.main()
