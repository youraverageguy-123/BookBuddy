from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from analyzer_cli import (
    APIClient,
    CLIError,
    _session_analysis,
    inspect_database,
    require_compatible_backend,
    wait_for_analysis,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def request(self, method, path):
        assert (method, path) == ("GET", "/sessions")
        return next(self.responses)


class FakeHTTPResponse:
    status = 200
    reason = "OK"

    def read(self):
        return b'{"book_name":"Book","session_name":"test","total_chapters":1}'


class FakeHTTPConnection:
    def __init__(self):
        self.headers = {}
        self.body = bytearray()
        self.closed = False

    def putrequest(self, method, path):
        self.request_line = (method, path)

    def putheader(self, name, value):
        self.headers[name] = value

    def endheaders(self):
        pass

    def send(self, content):
        self.body.extend(content)

    def getresponse(self):
        return FakeHTTPResponse()

    def close(self):
        self.closed = True


class AnalyzerCLITests(unittest.TestCase):
    def test_stale_backend_is_rejected_before_upload_or_analysis(self):
        with self.assertRaisesRegex(CLIError, "running backend is stale"):
            require_compatible_backend({"status": "ready", "contracts": {}})
        require_compatible_backend({
            "status": "ready",
            "contracts": {"chapter_analysis_transport": "compact_schema_adapter_v2"},
        })

    def test_upload_streams_epub_to_public_upload_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            epub = Path(temporary, "sample.epub")
            epub.write_bytes(b"PK\x03\x04epub-test")
            connection = FakeHTTPConnection()
            client = APIClient("http://127.0.0.1:8000")
            with mock.patch.object(client, "_connection", return_value=connection):
                response = client.upload_epub(epub, "terminal_test")
        self.assertEqual(("POST", "/upload"), connection.request_line)
        self.assertIn("multipart/form-data", connection.headers["Content-Type"])
        self.assertIn(b'terminal_test', connection.body)
        self.assertIn(b'filename="sample.epub"', connection.body)
        self.assertIn(b"PK\x03\x04epub-test", connection.body)
        self.assertEqual("Book", response["book_name"])
        self.assertTrue(connection.closed)

    def test_session_analysis_selects_only_requested_session(self):
        session, analysis = _session_analysis(
            {"sessions": [
                {"session_key": "Other::one", "analysis": {"status": "error"}},
                {"session_key": "Book::test", "analysis": {"status": "processing", "progress": 25}},
            ]},
            "Book::test",
        )
        self.assertEqual("Book::test", session["session_key"])
        self.assertEqual("processing", analysis["status"])

    @mock.patch("analyzer_cli.time.sleep")
    def test_wait_for_analysis_requires_target_chapter(self, sleep):
        client = FakeClient([
            {"sessions": [{"session_key": "Book::test", "analysis": {
                "status": "completed", "last_analyzed_chapter": 0, "progress": 100,
            }}]},
            {"sessions": [{"session_key": "Book::test", "analysis": {
                "status": "processing", "last_analyzed_chapter": 1, "progress": 50,
            }}]},
            {"sessions": [{"session_key": "Book::test", "analysis": {
                "status": "completed", "last_analyzed_chapter": 2, "progress": 100,
            }}]},
        ])
        result = wait_for_analysis(client, "Book::test", 2, 0.1, output=lambda _: None)
        self.assertEqual("completed", result["status"])
        self.assertEqual(2, sleep.call_count)

    def test_wait_for_analysis_reports_backend_error(self):
        client = FakeClient([{"sessions": [{"session_key": "Book::test", "analysis": {
            "status": "error", "log": "provider failed",
        }}]}])
        with self.assertRaisesRegex(CLIError, "provider failed"):
            wait_for_analysis(client, "Book::test", 0, 0.1, output=lambda _: None)

    def test_inspect_database_is_read_only_and_reports_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "graph.db")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE entities (id INTEGER PRIMARY KEY)")
                connection.executemany("INSERT INTO entities DEFAULT VALUES", [(), ()])
                connection.commit()
            report = inspect_database(path)
            self.assertEqual("ok", report["quick_check"])
            self.assertEqual(2, report["counts"]["entities"])
            self.assertEqual(["entities"], report["tables"])


if __name__ == "__main__":
    unittest.main()
