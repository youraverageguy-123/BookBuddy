from pathlib import Path
import tempfile
import textwrap
import unittest

from fastapi.testclient import TestClient

from app import create_app
from config import load_config
import pdf_parser

try:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
except ImportError:  # pragma: no cover - optional dependency
    PdfWriter = None


def build_pdf(path: Path, pages: list[str], outline: list[tuple[str, int]] | None = None,
              title: str = "The Paper Lantern", author: str = "BookBuddy Tests") -> Path:
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        lines = textwrap.wrap(text, 80) or [""]
        escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET").encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    for entry_title, page_index in outline or []:
        writer.add_outline_item(entry_title, page_index)
    writer.add_metadata({"/Title": title, "/Author": author})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


PAGES = [
    "Preface. This short note explains how the lantern maker came to the valley.",
    "Mira carried the paper lantern across the bridge and into the sleeping town.",
    "The lantern flickered as Mira reached the square, where Oren waited by the well.",
    "Years later Oren told the story of the lantern to anyone who would listen.",
]


@unittest.skipIf(PdfWriter is None, "pypdf is not installed")
class PdfParserTests(unittest.TestCase):
    def test_outline_becomes_chapters_with_page_ranges(self):
        with tempfile.TemporaryDirectory() as root:
            source = build_pdf(Path(root, "book.pdf"), PAGES, outline=[("The Bridge", 1), ("The Telling", 3)])
            book = pdf_parser.parse_pdf(str(source))
        self.assertEqual("The Paper Lantern", book.title)
        self.assertEqual("BookBuddy Tests", book.author)
        self.assertEqual(["Front matter", "The Bridge", "The Telling"], [chapter.title for chapter in book.chapters])
        self.assertEqual(["page-1", "page-2", "page-4"], [chapter.spine_href for chapter in book.chapters])
        self.assertIn("Oren waited by the well", book.chapters[1].content)
        self.assertNotIn("Years later", book.chapters[1].content)
        self.assertEqual(
            [{"index": 0, "start_page": 1, "end_page": 1}, {"index": 1, "start_page": 2, "end_page": 3}, {"index": 2, "start_page": 4, "end_page": 4}],
            pdf_parser.page_ranges(book),
        )
        self.assertEqual(3, book.total_chapters)

    def test_pdf_without_outline_is_split_into_page_groups(self):
        with tempfile.TemporaryDirectory() as root:
            source = build_pdf(Path(root, "plain.pdf"), ["Page text number %d is here." % index for index in range(30)])
            book = pdf_parser.parse_pdf(str(source))
        self.assertEqual(3, book.total_chapters)
        self.assertEqual("Pages 1–12", book.chapters[0].title)
        self.assertEqual("page-25", book.chapters[2].spine_href)

    def test_validation_rejects_files_that_are_not_pdfs(self):
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root, "fake.pdf")
            fake.write_bytes(b"this is not a pdf at all")
            with self.assertRaises(ValueError):
                pdf_parser.validate_pdf_file(fake)


@unittest.skipIf(PdfWriter is None, "pypdf is not installed")
class PdfApiTests(unittest.TestCase):
    def config(self, root):
        return load_config(root, {
            "BOOKBUDDY_LIBRARY_DIR": "library", "BOOKBUDDY_CACHE_DIR": "cache", "BOOKBUDDY_LOG_DIR": "logs",
            "BOOKBUDDY_CONFIG_DIR": "config",
        })

    def test_pdf_upload_metadata_stream_reload_and_search(self):
        with tempfile.TemporaryDirectory() as root:
            source = build_pdf(Path(root, "book.pdf"), PAGES, outline=[("The Bridge", 1), ("The Telling", 3)])
            config = self.config(root)
            with TestClient(create_app(config)) as client:
                rejected = client.post("/upload", files={"file": ("bad.pdf", b"not a pdf", "application/pdf")})
                self.assertEqual(400, rejected.status_code, rejected.text)
                wrong_type = client.post("/upload", files={"file": ("book.txt", b"hello", "text/plain")})
                self.assertEqual(400, wrong_type.status_code)

                uploaded = client.post(
                    "/upload", files={"file": (source.name, source.read_bytes(), "application/pdf")},
                    data={"session_name": "Reading"},
                )
                self.assertEqual(200, uploaded.status_code, uploaded.text)
                identity = uploaded.json()
                self.assertEqual("The_Paper_Lantern", identity["book_name"])
                self.assertEqual(3, identity["total_chapters"])
                base = f"/reader/{identity['book_name']}/{identity['session_name']}"
                session_dir = Path(root, "library", identity["book_name"], identity["session_name"])
                self.assertTrue((session_dir / "source.pdf").is_file())

                metadata = client.get(f"/book/{identity['book_name']}/{identity['session_name']}").json()
                self.assertEqual("pdf", metadata["format"])
                self.assertEqual(4, metadata["page_count"])
                self.assertEqual({"index": 1, "start_page": 2, "end_page": 3}, metadata["page_ranges"][1])
                # The frontend schema requires 1-based book ordinals and known entry kinds.
                navigation_book = metadata["navigation"]["books"][0]
                self.assertGreaterEqual(navigation_book["ordinal"], 1)
                self.assertEqual(["front_matter", "chapter", "chapter"], [entry["kind"] for entry in navigation_book["entries"]])
                self.assertEqual("page-2", navigation_book["entries"][1]["spine_href"])

                streamed = client.get(f"{base}/epub")
                self.assertEqual(200, streamed.status_code)
                self.assertEqual("application/pdf", streamed.headers["content-type"])
                self.assertTrue(streamed.content.startswith(b"%PDF-"))

                sessions = client.get("/sessions").json()["sessions"]
                self.assertEqual("BookBuddy Tests", sessions[0]["author"])
                self.assertEqual("ok", sessions[0].get("integrity", {}).get("status", "ok"))
                self.assertEqual(404, client.get(f"{base}/cover?size=320").status_code)

                # The reader renders page one and stores it as the cover.
                png = b"\x89PNG\r\n\x1a\n" + b"generated-cover-bytes"
                self.assertEqual(415, client.put(f"{base}/cover", content=b"<svg onload=alert(1)>").status_code)
                self.assertEqual(413, client.put(f"{base}/cover", content=b"\x89PNG\r\n\x1a\n" + b"0" * (4 * 1024 * 1024)).status_code)
                self.assertEqual(404, client.put("/reader/Missing/Nope/cover", content=png).status_code)
                stored = client.put(f"{base}/cover", content=png, headers={"Content-Type": "image/png"})
                self.assertEqual(201, stored.status_code, stored.text)
                self.assertEqual(200, client.get(f"{base}/cover?size=320").status_code)

            # A fresh process must be able to reopen the stored PDF.
            with TestClient(create_app(config)) as client:
                loaded = client.post(f"/load/{identity['book_name']}/{identity['session_name']}")
                self.assertEqual(200, loaded.status_code, loaded.text)
                self.assertEqual(3, loaded.json()["total_chapters"])
                metadata = client.get(f"/book/{identity['book_name']}/{identity['session_name']}").json()
                self.assertEqual("pdf", metadata["format"])

    def test_epub_metadata_reports_its_format(self):
        from epub_test_fixture import build_image_fixture
        with tempfile.TemporaryDirectory() as root:
            fixture = build_image_fixture(Path(root, "fixture.epub"))
            with TestClient(create_app(self.config(root))) as client:
                identity = client.post("/upload", files={"file": (fixture.name, fixture.read_bytes(), "application/epub+zip")}).json()
                metadata = client.get(f"/book/{identity['book_name']}/{identity['session_name']}").json()
                self.assertEqual("epub", metadata["format"])
                self.assertEqual([], metadata["page_ranges"])
                refused = client.put(
                    f"/reader/{identity['book_name']}/{identity['session_name']}/cover", content=b"\x89PNG\r\n\x1a\nimage",
                )
                self.assertEqual(409, refused.status_code)


if __name__ == "__main__":
    unittest.main()
