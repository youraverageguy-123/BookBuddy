"""Interactive client for exercising the production BookBuddy analyzer.

Run the FastAPI backend separately, then use this script to upload an EPUB,
queue analysis through the public HTTP API, follow progress, and inspect the
SQLite graph produced by that same server workflow.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import http.client
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Callable
from urllib.parse import quote, urlsplit
import uuid


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_ANALYZER_CONTRACT = "compact_schema_adapter_v2"


class CLIError(RuntimeError):
    """A user-facing analyzer client failure."""


class APIClient:
    """Small standard-library HTTP client, including streamed EPUB uploads."""

    def __init__(self, base_url: str, token: str = "", timeout: float = 120.0):
        parsed = urlsplit(base_url.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise CLIError("Backend URL must start with http:// or https://.")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise CLIError("Backend URL must not contain a path, query, or fragment.")
        self.scheme = parsed.scheme
        self.host = parsed.hostname
        self.port = parsed.port
        self.token = token.strip()
        self.timeout = timeout

    def _connection(self) -> http.client.HTTPConnection:
        connection_type = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return connection_type(self.host, self.port, timeout=self.timeout)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "BookBuddy-Analyzer-CLI/1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        headers.update(extra or {})
        return headers

    @staticmethod
    def _decode_response(response: http.client.HTTPResponse) -> Any:
        body = response.read()
        text = body.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"detail": text or response.reason}
        if response.status >= 400:
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            raise CLIError(f"Backend returned HTTP {response.status}: {detail}")
        return payload

    def request(self, method: str, path: str) -> Any:
        connection = self._connection()
        try:
            connection.request(method, path, headers=self._headers())
            return self._decode_response(connection.getresponse())
        except OSError as exc:
            raise CLIError(f"Could not reach the backend: {exc}") from exc
        finally:
            connection.close()

    def upload_epub(self, epub_path: Path, session_name: str) -> dict[str, Any]:
        boundary = f"----BookBuddyAnalyzerCLI{uuid.uuid4().hex}"
        safe_filename = epub_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        content_type = mimetypes.guess_type(epub_path.name)[0] or "application/epub+zip"
        prefix = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="session_name"\r\n\r\n'
            f"{session_name}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
        content_length = len(prefix) + epub_path.stat().st_size + len(suffix)
        connection = self._connection()
        try:
            connection.putrequest("POST", "/upload")
            for name, value in self._headers({
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(content_length),
            }).items():
                connection.putheader(name, value)
            connection.endheaders()
            connection.send(prefix)
            with epub_path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    connection.send(chunk)
            connection.send(suffix)
            payload = self._decode_response(connection.getresponse())
        except OSError as exc:
            raise CLIError(f"EPUB upload failed: {exc}") from exc
        finally:
            connection.close()
        if not isinstance(payload, dict):
            raise CLIError("The backend returned an invalid upload response.")
        return payload


def require_compatible_backend(health: Any) -> None:
    contract = (
        health.get("contracts", {}).get("chapter_analysis_transport")
        if isinstance(health, dict)
        else None
    )
    if contract != REQUIRED_ANALYZER_CONTRACT:
        raise CLIError(
            "The running backend is stale or incompatible. Stop its Uvicorn process, "
            "restart it from this checkout, then rerun analyzer_cli.py."
        )


def _prompt_epub() -> Path:
    while True:
        raw = input("EPUB path ([q] quit): ").strip().strip('"\'')
        if raw.lower() == "q":
            raise KeyboardInterrupt
        candidate = Path(raw).expanduser()
        if candidate.is_file() and candidate.suffix.lower() == ".epub":
            return candidate.resolve()
        print("Enter the path to an existing .epub file.")


def _prompt_chapter(total_chapters: int) -> int:
    while True:
        raw = input(f"Analyze through chapter index [0-{total_chapters - 1}]: ").strip()
        if raw.isdigit() and 0 <= int(raw) < total_chapters:
            return int(raw)
        print("Enter a chapter index from the displayed range.")


def _print_chapters(chapters: list[dict[str, Any]]) -> None:
    print("\nChapters (analysis includes every missing chapter through the chosen index):")
    for chapter in chapters:
        index = chapter.get("index", "?")
        section_type = chapter.get("section_type", "")
        title = str(chapter.get("title") or "Untitled").replace("\n", " ")
        print(f"  [{index:>3}] {title}  ({section_type})")


def _session_analysis(payload: Any, session_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
    for session in sessions:
        if session.get("session_key") == session_key:
            analysis = session.get("analysis") or {}
            return session, analysis if isinstance(analysis, dict) else {}
    return {}, {}


def wait_for_analysis(
    client: APIClient,
    session_key: str,
    target_chapter: int,
    poll_interval: float,
    output: Callable[[str], None] = print,
) -> dict[str, Any]:
    last_display: tuple[Any, ...] | None = None
    while True:
        session, analysis = _session_analysis(client.request("GET", "/sessions"), session_key)
        status = str(analysis.get("status", "queued"))
        progress = analysis.get("progress", 0)
        current = analysis.get("current_chapter", "-")
        message = str(analysis.get("log", "Waiting for analyzer to start."))
        display = (status, progress, current, message)
        if display != last_display:
            output(f"[{status}] {progress}% | chapter {current} | {message}")
            last_display = display

        last_analyzed = analysis.get("last_analyzed_chapter", session.get("last_analyzed_chapter", -1))
        try:
            reached_target = int(last_analyzed) >= target_chapter
        except (TypeError, ValueError):
            reached_target = False
        if status == "completed" and reached_target:
            return analysis
        if status in {"cancelled", "error"}:
            raise CLIError(f"Analysis ended with status '{status}': {message}")
        time.sleep(max(0.1, poll_interval))


def inspect_database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CLIError(f"Analysis completed, but graph.db was not found at: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            counts = {}
            for table in ("entities", "events", "relationships", "chapter_evidence_revisions"):
                if table in tables:
                    counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error as exc:
        raise CLIError(f"Could not inspect graph.db: {exc}") from exc
    return {"quick_check": quick_check, "tables": tables, "counts": counts, "size": path.stat().st_size}


def _default_library_dir() -> Path:
    try:
        from config import load_config

        return load_config().paths.library_dir
    except Exception:
        return PROJECT_ROOT / "library"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Running BookBuddy backend URL")
    parser.add_argument("--epub", type=Path, help="EPUB to upload; prompted when omitted")
    parser.add_argument("--session", help="Session label; prompted when omitted")
    parser.add_argument("--chapter", type=int, help="Target chapter index; prompted when omitted")
    parser.add_argument("--vision", action="store_true", help="Authorize conditional Gemini Vision fallback")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Progress polling interval in seconds")
    parser.add_argument("--library-dir", type=Path, help="Override the local library directory used to find graph.db")
    parser.add_argument("--api-token", default=os.environ.get("BOOKBUDDY_API_TOKEN", ""), help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = APIClient(args.base_url, args.api_token)
    print(f"Connecting to BookBuddy backend at {args.base_url.rstrip('/')} ...")
    health = client.request("GET", "/health")
    if health.get("status") != "ready":
        raise CLIError(f"Backend is not ready: {health}")
    require_compatible_backend(health)
    if not health.get("capabilities", {}).get("chapter_analysis"):
        raise CLIError("Backend is ready, but chapter analysis is unavailable. Check Gemini credentials and dependencies.")

    epub_path = (args.epub.expanduser().resolve() if args.epub else _prompt_epub())
    if not epub_path.is_file() or epub_path.suffix.lower() != ".epub":
        raise CLIError(f"EPUB does not exist or has the wrong extension: {epub_path}")
    session_name = args.session if args.session is not None else input("Session name [terminal_test]: ").strip()
    session_name = session_name or "terminal_test"

    print(f"Uploading {epub_path.name} ...")
    upload = client.upload_epub(epub_path, session_name)
    book_name = str(upload["book_name"])
    safe_session = str(upload["session_name"])
    session_key = f"{book_name}::{safe_session}"
    book_url, session_url = quote(book_name, safe=""), quote(safe_session, safe="")
    metadata = client.request("GET", f"/book/{book_url}/{session_url}")
    chapters = metadata.get("chapters", [])
    if not chapters:
        raise CLIError("The EPUB was imported, but the backend reported no chapters.")
    _print_chapters(chapters)
    target_chapter = args.chapter if args.chapter is not None else _prompt_chapter(len(chapters))
    if target_chapter < 0 or target_chapter >= len(chapters):
        raise CLIError(f"Chapter index must be between 0 and {len(chapters) - 1}.")

    vision_query = "true" if args.vision else "false"
    print(f"\nQueuing production analysis through chapter {target_chapter} ...")
    client.request("POST", f"/analyze/{book_url}/{session_url}/{target_chapter}?use_gemini_vision={vision_query}")
    wait_for_analysis(client, session_key, target_chapter, args.poll_interval)

    library_dir = args.library_dir.resolve() if args.library_dir else _default_library_dir()
    database_path = library_dir / book_name / safe_session / "database" / "graph.db"
    report = inspect_database(database_path)
    print("\nANALYSIS COMPLETE")
    print(f"Database: {database_path}")
    print(f"Size: {report['size']:,} bytes")
    print(f"SQLite quick_check: {report['quick_check']}")
    print(f"Tables: {len(report['tables'])}")
    if report["counts"]:
        print("Key row counts: " + ", ".join(f"{name}={count}" for name, count in report["counts"].items()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped following progress. Any queued backend analysis may still be running.")
        raise SystemExit(130)
    except CLIError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
