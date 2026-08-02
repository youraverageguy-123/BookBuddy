from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
import os
import shutil
import re
import asyncio
import hashlib
import json
import logging
import importlib.util
import secrets
import threading
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Literal
from epub_parser import parse_epub, ParsedBook
from continuity_manager import (
    find_series_matches,
    inherit_series_graph,
    latest_session_for_book,
    write_continuity_metadata,
)
from explanation_service import ExplanationService
from session_manager import sanitize_session_component
from snapshot_manager import EvidenceStore, ReaderSnapshotBuilder, SnapshotStore
from config import AppConfig, GRAPH_SCHEMA_VERSION, load_config
from dictionary_subsystem.models import HighlightRequest
from dictionary_subsystem.service import HighlightResolver
from bootstrap import AppServices, bootstrap_application
from ai.models import AIServiceUnavailable, GenerationRequest
from ai.gemini_provider import GeminiProvider
from ai_credentials import EncryptedCredentialStore, CredentialStorageUnavailable
from storage_security import copy_limited, resolve_under_root, validate_epub_archive
from reader_plugins import reader_plugin_registry
from log_manager import close_file_logging, configure_file_logging

LIBRARY_DIR = ""
ai_manager = None
session_manager = None
dictionary_provider = None
pronunciation_provider = None
reader_knowledge_store = None
context_resolver = None
task_supervisor = None
task_manager = None
reader_search = None
database_maintenance = None
resource_manager = None
database_registry = None
parser_service = None
replay_service = None
reader_analysis = None
app_config = None

_IMPORT_LOCKS_GUARD = threading.Lock()
_IMPORT_LOCKS: dict[str, threading.RLock] = {}
_SOURCE_IDENTITY_GUARD = threading.Lock()
_SOURCE_IDENTITY_CACHE: dict[str, tuple[int, int, str]] = {}


def _bind_services(services: AppServices) -> None:
    global LIBRARY_DIR, ai_manager, session_manager, dictionary_provider
    global pronunciation_provider, reader_knowledge_store, context_resolver, task_supervisor
    global database_registry, parser_service, replay_service, reader_analysis, app_config, task_manager, reader_search, database_maintenance, resource_manager
    LIBRARY_DIR = str(services.config.paths.library_dir)
    ai_manager = services.ai_manager
    session_manager = services.session_manager
    dictionary_provider = services.dictionary_provider
    pronunciation_provider = services.pronunciation_provider
    reader_knowledge_store = services.reader_knowledge_store
    context_resolver = services.context_resolver
    task_supervisor = services.task_supervisor
    task_manager = services.task_manager
    reader_search = services.search
    database_maintenance = services.maintenance
    resource_manager = services.resources
    database_registry = services.databases
    parser_service = services.parser_service
    replay_service = services.replay_service
    reader_analysis = services.reader_analysis
    app_config = services.config


def _safe_library_path(*parts: str) -> str:
    try:
        return str(resolve_under_root(LIBRARY_DIR, *parts))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid library path.") from exc


def _safe_db_dir(book_name: str, session_name: str) -> str:
    return _safe_library_path(book_name, session_name, "database")


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _sha256_file(path: str | Path) -> str:
    source = Path(path)
    stat_result = source.stat()
    cache_key = str(source.resolve())
    with _SOURCE_IDENTITY_GUARD:
        cached = _SOURCE_IDENTITY_CACHE.get(cache_key)
        if cached and cached[:2] == (stat_result.st_size, stat_result.st_mtime_ns):
            return cached[2]
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    with _SOURCE_IDENTITY_GUARD:
        _SOURCE_IDENTITY_CACHE[cache_key] = (stat_result.st_size, stat_result.st_mtime_ns, value)
    return value


@contextmanager
def _book_import_lock(book_name: str):
    with _IMPORT_LOCKS_GUARD:
        thread_lock = _IMPORT_LOCKS.setdefault(book_name, threading.RLock())
    with thread_lock:
        lock_dir = Path(LIBRARY_DIR, ".bookbuddy-locks")
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_name = hashlib.sha256(book_name.encode("utf-8")).hexdigest() + ".lock"
        with (lock_dir / lock_name).open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _verified_session_source(session_dir: str, relative_path: str, metadata: dict) -> str:
    relative = Path(str(relative_path).replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise HTTPException(status_code=409, detail="Session source identity is invalid.")
    raw_path = Path(session_dir).joinpath(*relative.parts)
    for candidate in (Path(session_dir), *raw_path.parents, raw_path):
        if candidate == Path(session_dir).parent:
            break
        if candidate.exists() and _is_reparse_point(candidate):
            raise HTTPException(status_code=409, detail="Session source may not use links or reparse points.")
    try:
        source = Path(resolve_under_root(session_dir, *relative.parts))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Session source escapes its session directory.") from exc
    if not source.is_file():
        raise HTTPException(status_code=404, detail="EPUB source is missing from the session directory.")
    expected_size = metadata.get("source_size_bytes")
    if expected_size is not None and source.stat().st_size != int(expected_size):
        raise HTTPException(status_code=409, detail="Session source size no longer matches metadata.")
    expected_hash = str(metadata.get("source_sha256") or "").lower()
    if expected_hash and _sha256_file(source) != expected_hash:
        raise HTTPException(status_code=409, detail="Session source hash no longer matches metadata.")
    return str(source)


def _adopt_legacy_session_source(book_name: str, session_name: str, session_key: str, session_dir: str) -> str:
    local_candidates = sorted(
        path for path in Path(session_dir).glob("*.epub") if path.is_file() and not _is_reparse_point(path)
    )
    book_dir = Path(_safe_library_path(book_name))
    shared_candidates = sorted(
        path for path in book_dir.glob("*.epub") if path.is_file() and not _is_reparse_point(path)
    )
    candidates = local_candidates or shared_candidates
    if not candidates:
        raise HTTPException(status_code=404, detail="EPUB file missing from session and legacy book directories.")
    source = candidates[0]
    destination = Path(session_dir, "source.epub")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with source.open("rb") as reader, temporary.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    digest = _sha256_file(destination)
    session_manager.update_session_metadata(
        session_key,
        book_name=book_name,
        session_name=session_name,
        source_epub_relpath="source.epub",
        source_sha256=digest,
        source_size_bytes=destination.stat().st_size,
        original_filename=source.name,
        source_format_version="bookbuddy_session_source_v1",
    )
    return str(destination)


def _session_epub_path(book_name: str, session_name: str) -> str:
    session_dir = _safe_library_path(book_name, session_name)
    if not os.path.isdir(session_dir):
        raise HTTPException(status_code=404, detail="Session not found in library.")
    session_key = _session_key(book_name, session_name)
    metadata = session_manager.get_session_metadata(session_key)
    relative_path = metadata.get("source_epub_relpath")
    if relative_path:
        return _verified_session_source(session_dir, str(relative_path), metadata)
    return _adopt_legacy_session_source(book_name, session_name, session_key, session_dir)


def _epub_package_metadata(path: str) -> tuple[str | None, str | None]:
    """Read only the EPUB package metadata; never parse chapter content here."""
    try:
        with zipfile.ZipFile(path) as archive:
            container = archive.read("META-INF/container.xml")
            if len(container) > 256 * 1024:
                return None, None
            root = ET.fromstring(container)
            node = root.find(".//{*}rootfile")
            package_name = node.attrib.get("full-path", "") if node is not None else ""
            normalized = package_name.replace("\\", "/")
            if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
                return None, None
            package = archive.read(package_name)
            if len(package) > 2 * 1024 * 1024:
                return None, None
            metadata = ET.fromstring(package)
            title_node = metadata.find(".//{http://purl.org/dc/elements/1.1/}title")
            author_node = metadata.find(".//{http://purl.org/dc/elements/1.1/}creator")
            title = " ".join((title_node.text or "").split()) if title_node is not None else None
            author = " ".join((author_node.text or "").split()) if author_node is not None else None
            return title or None, author or None
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return None, None


def _cached_cover_path(book_name: str, session_name: str, size: int = 640) -> str | None:
    if resource_manager is not None:
        cached = resource_manager.cover(_session_key(book_name, session_name), size)
        if cached:
            return str(cached)
    session_dir = _safe_library_path(book_name, session_name)
    if not os.path.isdir(session_dir):
        return None
    candidates = sorted(
        os.path.join(session_dir, name) for name in os.listdir(session_dir)
        if name.startswith("bookbuddy-cover.") and os.path.isfile(os.path.join(session_dir, name))
    )
    return candidates[0] if candidates else None


def _extract_cover(book_name: str, session_name: str, size: int = 640) -> tuple[str, str] | None:
    cached = _cached_cover_path(book_name, session_name, size)
    if cached:
        extension = os.path.splitext(cached)[1].lower()
        return cached, {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}.get(extension, "application/octet-stream")
    try:
        from ebooklib import ITEM_COVER, ITEM_IMAGE, epub
        book = epub.read_epub(_session_epub_path(book_name, session_name), options={"ignore_ncx": False})
        cover = next((item for item in book.get_items() if item.get_type() == ITEM_COVER), None)
        if cover is None:
            metadata = book.get_metadata("OPF", "cover")
            cover_id = metadata[0][1].get("content") if metadata else None
            cover = book.get_item_with_id(cover_id) if cover_id else None
        if cover is None:
            cover = next((item for item in book.get_items() if item.get_type() == ITEM_IMAGE and "cover" in str(item.get_name()).lower()), None)
        if cover is None:
            return None
        media_type = str(getattr(cover, "media_type", "") or "").lower()
        extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg"}
        extension = extensions.get(media_type)
        content = cover.get_content()
        if not extension or not content or len(content) > 20 * 1024 * 1024:
            return None
        resource_manager.store_cover(_session_key(book_name, session_name), content, extension)
        path = resource_manager.cover(_session_key(book_name, session_name), size)
        if path is None:
            return None
        output_type = "image/webp" if path.suffix.lower() == ".webp" else media_type
        return str(path), output_type
    except Exception:
        logging.getLogger(__name__).warning("Could not extract cover for %s", _session_key(book_name, session_name), exc_info=True)
        return None


def _first_missing_evidence(db_dir: str, target_chapter: int) -> int:
    """Resume from immutable active evidence; JSON is legacy fallback only."""
    graph_path = os.path.join(db_dir, "graph.db")
    active: set[int] | None = None
    if os.path.exists(graph_path):
        try:
            import sqlite3
            with sqlite3.connect(f"file:{__import__('pathlib').Path(graph_path).resolve().as_posix()}?mode=ro", uri=True) as conn:
                table = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chapter_evidence_revisions'"
                ).fetchone()
                if table:
                    active = {
                        int(row[0]) for row in conn.execute(
                            "SELECT chapter FROM chapter_evidence_revisions WHERE is_active = 1 AND chapter <= ?",
                            (target_chapter,),
                        )
                    }
        except sqlite3.Error:
            active = None
    for index in range(target_chapter + 1):
        if active is not None:
            if index not in active:
                return index
        elif not os.path.exists(os.path.join(db_dir, f"chapter_{index}.json")):
            return index
    return target_chapter + 1


class HighlightBody(BaseModel):
    chapter_index: int = Field(ge=0)
    selected_text: str = Field(min_length=1, max_length=160)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    context_text: str | None = Field(default=None, max_length=4000)
    sentence_text: str | None = Field(default=None, max_length=4000)
    previous_sentence: str | None = Field(default=None, max_length=4000)
    next_sentence: str | None = Field(default=None, max_length=4000)
    paragraph_text: str | None = Field(default=None, max_length=4000)
    sentence_selection_start: int | None = Field(default=None, ge=0)
    sentence_selection_end: int | None = Field(default=None, ge=0)
    language: str = Field(default="en", min_length=2, max_length=16)
    allow_ai_fallback: bool = False
    knowledge_as_of_chapter: int | None = Field(default=None, ge=-1)
    explain_function_words: bool = False


class SelectionExplainBody(BaseModel):
    chapter_index: int = Field(ge=0)
    selected_text: str = Field(min_length=1, max_length=160)
    context_text: str = Field(min_length=1, max_length=4000)
    knowledge_as_of_chapter: int = Field(ge=-1)


class SelectionTranslationBody(BaseModel):
    selected_text: str = Field(min_length=1, max_length=2000)
    target_language: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z][A-Za-z ()-]*$")


class ReaderProfileBody(BaseModel):
    user_id: str


class ReaderFlagBody(ReaderProfileBody):
    value: bool = True


class ReaderBookStateBody(BaseModel):
    favorite: bool | None = None
    want_to_read: bool | None = None
    last_opened_at: float | None = Field(default=None, ge=0)
    last_cfi: str | None = Field(default=None, max_length=2000)
    current_chapter: int | None = Field(default=None, ge=0)
    chapter_progress: float | None = Field(default=None, ge=0, le=1)
    book_progress: float | None = Field(default=None, ge=0, le=1)
    added_at: float | None = Field(default=None, ge=0)
    finished_at: float | None = Field(default=None, ge=0)


class ReaderChapterProgressBody(BaseModel):
    last_cfi: str = Field(default="", max_length=2000)
    current_progress: float = Field(default=0, ge=0, le=1)
    contiguous_progress: float = Field(default=0, ge=0, le=1)
    threshold_started: bool = False
    naturally_completed: bool = False
    committed: bool = False
    retry_required: bool = False


class ReaderStateImportBody(BaseModel):
    books: list[dict] = Field(default_factory=list, max_length=10000)
    chapters: list[dict] = Field(default_factory=list, max_length=100000)


class ReaderCollectionBody(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    sort_order: int | None = Field(default=None, ge=0)


class ReaderCollectionMemberBody(BaseModel):
    session_key: str = Field(min_length=3, max_length=240)
    present: bool = True


class ReaderBookmarkBody(BaseModel):
    chapter_index: int = Field(ge=0)
    cfi: str = Field(min_length=1, max_length=2000)
    excerpt: str = Field(default="", max_length=500)
    name: str = Field(default="", max_length=120)


class ReaderBookmarkUpdateBody(BaseModel):
    name: str = Field(default="", max_length=120)


class ReaderAnnotationBody(BaseModel):
    chapter_index: int = Field(ge=0)
    cfi_range: str = Field(min_length=1, max_length=4000)
    quote: str = Field(default="", max_length=2000)
    annotation_type: str = Field(pattern="^(highlight|underline|note)$")
    color: str = Field(default="gold", max_length=24)
    note_text: str = Field(default="", max_length=20000)


class ReaderAnnotationUpdateBody(BaseModel):
    annotation_type: str | None = Field(default=None, pattern="^(highlight|underline|note)$")
    color: str | None = Field(default=None, max_length=24)
    note_text: str | None = Field(default=None, max_length=20000)


class ReaderSessionBody(BaseModel):
    started_at: float = Field(ge=0)
    ended_at: float = Field(ge=0)
    active_seconds: float = Field(ge=0)
    start_progress: float = Field(default=0, ge=0, le=1)
    end_progress: float = Field(default=0, ge=0, le=1)


class ReaderEntityResponse(BaseModel):
    contract_version: str
    as_of_chapter: int
    entity: dict
    aliases: list[dict]
    relationships: list[dict]
    events: list[dict]
    status: dict
    importance: dict
    portrait: dict
    dictionary: dict


class AISettingsBody(BaseModel):
    api_keys: list[str] = Field(default_factory=list, max_length=10)
    vision_api_keys: list[str] = Field(default_factory=list, max_length=10)

_route_registry = FastAPI(title="BookBuddy Route Registry")
app = _route_registry

@app.get("/")
def read_root(): 
    return {"status": "online"}


@app.get("/health")
def health():
    pronunciation_index = app_config.paths.pronunciation_corpus_index
    return {
        "schema_version": "bookbuddy_health_v1",
        "status": "ready",
        "version": app_config.contracts.bookbuddy_version,
        "storage": {
            "library": "available" if os.path.isdir(LIBRARY_DIR) and os.access(LIBRARY_DIR, os.W_OK) else "unavailable",
        },
        "capabilities": {
            "chapter_analysis": ai_manager.is_available("text"),
            "dictionary": importlib.util.find_spec("wn") is not None,
            "contextual_dictionary": context_resolver is not None,
            "pronunciation": importlib.util.find_spec("cmudict") is not None,
            "recorded_audio": bool(pronunciation_index and pronunciation_index.is_file()),
            "vision": ai_manager.is_available("vision"),
            "translation": ai_manager.is_available("text"),
        },
    }


def _credential_store() -> EncryptedCredentialStore:
    return EncryptedCredentialStore(app_config.paths.config_dir / "ai-credentials.bin")


def _ai_settings_payload() -> dict:
    config = ai_manager.config
    store = _credential_store()
    return {
        "schema_version": "bookbuddy_ai_settings_v1",
        "configured": bool(config.api_keys),
        "vision_configured": bool(config.vision_api_keys),
        "key_count": len(config.api_keys),
        "vision_key_count": len(config.vision_api_keys),
        "source": config.credential_source,
        "storage_protection": "windows-user-encrypted" if store.available else "unavailable",
        "capabilities": {
            "text": ai_manager.is_available("text"),
            "vision": ai_manager.is_available("vision"),
        },
    }


def _clean_submitted_keys(values: list[str], label: str) -> list[str]:
    cleaned = []
    for value in values:
        secret = value.strip()
        if not secret:
            continue
        if len(secret) < 16 or len(secret) > 512 or any(character.isspace() for character in secret):
            raise HTTPException(status_code=422, detail=f"{label} contains an invalid API key.")
        if secret not in cleaned:
            cleaned.append(secret)
    return cleaned


@app.get("/settings/ai")
def ai_settings():
    """Return status and counts only; secrets are never returned."""
    return _ai_settings_payload()


@app.put("/settings/ai")
def update_ai_settings(body: AISettingsBody):
    global app_config
    api_keys = _clean_submitted_keys(body.api_keys, "AI keys")
    vision_keys = _clean_submitted_keys(body.vision_api_keys, "Vision keys")
    if not api_keys and not vision_keys:
        raise HTTPException(status_code=422, detail="Enter at least one API key, or keep using BookBuddy offline.")
    try:
        _credential_store().write(api_keys, vision_keys)
    except CredentialStorageUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not save encrypted AI credentials.") from exc
    new_ai = replace(
        ai_manager.config,
        api_keys=tuple((f"USER_KEY_{index}", value) for index, value in enumerate(api_keys, 1)),
        vision_api_keys=tuple((f"USER_VISION_KEY_{index}", value) for index, value in enumerate(vision_keys, 1)),
        credential_source="encrypted",
    )
    ai_manager.reconfigure(new_ai, GeminiProvider(new_ai))
    app_config = replace(app_config, ai=new_ai)
    return _ai_settings_payload()


@app.get("/tasks")
def list_background_tasks(state: str | None = Query(default=None, max_length=24), session_key: str | None = Query(default=None, max_length=240)):
    return {"schema_version": "bookbuddy_tasks_v1", "tasks": task_manager.list(state=state, session_key=session_key)}


@app.get("/plugins")
def list_reader_plugins():
    return {"schema_version": "bookbuddy_reader_plugins_v1", "plugins": reader_plugin_registry.list()}


@app.get("/maintenance/status")
def database_maintenance_status():
    return {"schema_version":"bookbuddy_database_maintenance_v1","databases":database_maintenance.status()}


@app.post("/maintenance/{database_name}")
def run_database_maintenance(database_name:str, vacuum:bool=False):
    try:return {"schema_version":"bookbuddy_database_maintenance_v1","result":database_maintenance.maintain(database_name,allow_vacuum=vacuum)}
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc


@app.get("/resources/status")
def resource_status():
    return {"schema_version": "bookbuddy_resources_v1", "resources": resource_manager.diagnostics()}


@app.post("/resources/{namespace}/prune")
def prune_resource_cache(namespace: str):
    try:
        return {"schema_version": "bookbuddy_resources_v1", "result": resource_manager.prune(namespace)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/cancel")
def cancel_background_task(task_id: str):
    try:
        return {"schema_version": "bookbuddy_task_v1", "task": task_supervisor.request_cancel(task_id=task_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/retry")
async def retry_background_task(task_id: str):
    try:
        return {"schema_version": "bookbuddy_task_v1", "task": task_supervisor.retry(task_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.get("/library")
def list_library():
    """Returns a nested hierarchy: { "Book_Name": ["Session_1", "Session_2"] }"""
    library_tree = {}
    deleted_keys = {
        item.get("session_key")
        for item in session_manager.list_sessions(include_deleted=True, validate=False)
        if item.get("is_deleted")
    }
    if os.path.exists(LIBRARY_DIR):
        for book in os.listdir(LIBRARY_DIR):
            if book.startswith("."):
                continue
            book_path = os.path.join(LIBRARY_DIR, book)
            if os.path.isdir(book_path):
                book_sessions = [
                    s for s in os.listdir(book_path)
                    if os.path.isdir(os.path.join(book_path, s))
                    and not s.startswith(".")
                    and f"{book}::{s}" not in deleted_keys
                ]
                library_tree[book] = book_sessions
    return {"library": library_tree}

def _session_key(book_name: str, session_name: str) -> str:
    return f"{book_name}::{session_name}"

def _disk_sessions() -> list[dict]:
    sessions = []
    if not os.path.exists(LIBRARY_DIR):
        return sessions
    for book in os.listdir(LIBRARY_DIR):
        if book.startswith("."):
            continue
        book_path = os.path.join(LIBRARY_DIR, book)
        if not os.path.isdir(book_path):
            continue
        for session in os.listdir(book_path):
            if session.startswith("."):
                continue
            session_path = os.path.join(book_path, session)
            if os.path.isdir(session_path):
                sessions.append({
                    "session_key": _session_key(book, session),
                    "book_name": book,
                    "session_name": session,
                    "session_dir": session_path,
                })
    return sessions


def _require_reader_session(book_name: str, session_name: str) -> str:
    session_key = _session_key(book_name, session_name)
    metadata = session_manager.get_session_metadata(session_key)
    if not metadata and not os.path.isdir(_safe_library_path(book_name, session_name)):
        raise HTTPException(status_code=404, detail="Reader session not found.")
    return session_key

@app.get("/sessions")
def list_sessions(include_deleted: bool = False):
    metadata_sessions = session_manager.list_sessions(include_deleted=include_deleted, validate=True)
    seen = {item["session_key"] for item in metadata_sessions}
    for disk_session in _disk_sessions():
        if disk_session["session_key"] in seen:
            continue
        session_manager.register_disk_session(
            disk_session["session_key"],
            disk_session["book_name"],
            disk_session["session_name"],
            disk_session["session_dir"],
        )
        disk_session["integrity"] = {
            "status": "missing_metadata",
            "issues": ["session exists on disk but not in session metadata"],
        }
        metadata_sessions.append(disk_session)
    public_sessions = []
    for item in metadata_sessions:
        public = {key: value for key, value in item.items() if key not in {"session_dir"}}
        public.setdefault("book_name", str(public.get("session_key", "")).split("::", 1)[0])
        public.setdefault("session_name", str(public.get("session_key", "")).split("::", 1)[-1])
        public.setdefault("book_title", public.get("book_name", "").replace("_", " "))
        if not public.get("author") or public.get("author") == "Unknown":
            try:
                epub_path = _session_epub_path(public["book_name"], public["session_name"])
                package_title, package_author = _epub_package_metadata(epub_path)
                public["book_title"] = package_title or public["book_title"]
                public["author"] = package_author or "Unknown"
                public["imported_at"] = public.get("imported_at") or os.path.getmtime(epub_path)
                session_manager.update_session_metadata(public["session_key"], book_title=public["book_title"], author=public["author"], imported_at=public["imported_at"])
            except HTTPException:
                public["author"] = "Unknown"
        public.setdefault("imported_at", public.get("loaded_at") or public.get("discovered_on_disk_at") or public.get("updated_at"))
        public["cover_available"] = bool(_cached_cover_path(public["book_name"], public["session_name"]))
        public["analysis"] = session_manager.get_task(public["session_key"], {"status": "idle", "progress": 0.0})
        public["reader_analysis"] = reader_analysis.status(public["session_key"])
        public_sessions.append(public)
    return {"schema_version": "bookbuddy_sessions_v1", "sessions": public_sessions}

@app.get("/session/{book_name}/{session_name}/integrity")
def check_session_integrity(book_name: str, session_name: str):
    session_key = _session_key(book_name, session_name)
    metadata = session_manager.get_session_metadata(session_key)
    if not metadata:
        session_dir = _safe_library_path(book_name, session_name)
        if os.path.isdir(session_dir):
            return {
                "session_key": session_key,
                "integrity": {
                    "status": "missing_metadata",
                    "issues": ["session exists on disk but not in session metadata"],
                },
            }
        raise HTTPException(status_code=404, detail="Session metadata not found.")
    return {"session_key": session_key, "integrity": session_manager.validate_session_integrity(session_key)}

@app.post("/session/{book_name}/{session_name}/rename")
def rename_session(book_name: str, session_name: str, label: str = Form(...)):
    session_key = _session_key(book_name, session_name)
    try:
        return {"session": session_manager.rename_session(session_key, label)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Session metadata not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/session/{book_name}/{session_name}/delete")
def soft_delete_session(book_name: str, session_name: str):
    session_key = _session_key(book_name, session_name)
    try:
        return {"session": session_manager.soft_delete_session(session_key)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Session metadata not found.")

@app.post("/session/{book_name}/{session_name}/restore")
def restore_session(book_name: str, session_name: str):
    session_key = _session_key(book_name, session_name)
    try:
        return {"session": session_manager.restore_session(session_key)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Session metadata not found.")

@app.delete("/session/{book_name}/{session_name}")
def hard_delete_session(book_name: str, session_name: str, dry_run: bool = True):
    session_key = _session_key(book_name, session_name)
    try:
        return session_manager.hard_delete_session(session_key, LIBRARY_DIR, dry_run=dry_run)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session metadata not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/sessions/purge-deleted")
def purge_deleted_sessions(older_than_seconds: float = 0, dry_run: bool = True):
    return session_manager.purge_deleted_sessions(
        LIBRARY_DIR,
        older_than_seconds=older_than_seconds,
        dry_run=dry_run,
    )

@app.post("/load/{book_name}/{session_name}")
def load_existing_book(book_name: str, session_name: str):
    session_dir = _safe_library_path(book_name, session_name)
    
    if not os.path.exists(session_dir):
        raise HTTPException(status_code=404, detail="Session not found in library.")
    
    try:
        parsed_book = parse_epub(_session_epub_path(book_name, session_name))
        session_key = f"{book_name}::{session_name}"
        
        session_manager.set_book(session_key, parsed_book, session_dir=session_dir)
        session_manager.update_session_metadata(session_key, total_chapters=parsed_book.total_chapters, total_words=sum(chapter.word_count for chapter in parsed_book.chapters))
        if not reader_search.status(session_key).get("ready"):
            supervisor_key = f"search::{session_key}"
            search_factory = lambda: _index_book_background(supervisor_key, session_key, parsed_book)
            search_task = search_factory()
            try:
                task_supervisor.submit(supervisor_key, search_task, task_type="search_index", retry_factory=search_factory)
            except RuntimeError:
                search_task.close()
        continuity_path = os.path.join(session_dir, "continuity.json")
        if not os.path.exists(continuity_path):
            write_continuity_metadata(session_dir, book_name, session_type="resumed")
            
        return {
            "message": f"Mounted {session_name} into memory.",
            "total_chapters": parsed_book.total_chapters,
            "session_type": "resumed",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/series-matches")
def get_series_matches(title: str, author: str = ""):
    return {"matches": find_series_matches(LIBRARY_DIR, title, author)}


async def _index_book_background(supervisor_key: str, session_key: str, book: ParsedBook) -> None:
    task_supervisor.cancellation_checkpoint(supervisor_key, "before_search_index")
    await asyncio.to_thread(reader_search.index_book, session_key, book)
    task_supervisor.cancellation_checkpoint(supervisor_key, "after_search_index")


def _existing_import(book_name: str, requested_session: str, source_sha256: str) -> dict | None:
    for metadata in session_manager.list_sessions(include_deleted=False, validate=False):
        if metadata.get("book_name") != book_name:
            continue
        logical_session = metadata.get("requested_session_name") or metadata.get("session_name")
        if logical_session != requested_session or metadata.get("source_sha256") != source_sha256:
            continue
        existing_session = str(metadata.get("session_name") or "")
        if existing_session and os.path.isdir(_safe_library_path(book_name, existing_session)):
            return metadata
    return None


def _allocate_import_session(book_name: str, requested_session: str, source_sha256: str) -> str:
    base_key = _session_key(book_name, requested_session)
    if not session_manager.get_session_metadata(base_key) and not os.path.lexists(_safe_library_path(book_name, requested_session)):
        return requested_session
    for prefix_length in range(8, len(source_sha256) + 1):
        stem_length = max(1, 80 - prefix_length - 2)
        candidate = f"{requested_session[:stem_length]}--{source_sha256[:prefix_length]}"
        candidate_key = _session_key(book_name, candidate)
        metadata = session_manager.get_session_metadata(candidate_key)
        if metadata.get("source_sha256") == source_sha256 and not metadata.get("is_deleted"):
            return candidate
        if not metadata and not os.path.lexists(_safe_library_path(book_name, candidate)):
            return candidate
    raise HTTPException(status_code=409, detail="Could not allocate a collision-safe session identity.")


def _remove_orphan_import_staging(book_dir: Path) -> None:
    for candidate in book_dir.glob(".*.staging-*"):
        if candidate.is_dir() and not _is_reparse_point(candidate):
            shutil.rmtree(candidate)


@app.post("/upload")
async def upload_epub(
    file: UploadFile = File(...),
    session_name: str = Form("Default_Session"),
    series_parent_book: str | None = Form(None),
    series_parent_session: str | None = Form(None),
):
    original_filename = Path((file.filename or "").replace("\\", "/")).name
    if not original_filename.lower().endswith('.epub'):
        raise HTTPException(status_code=400, detail="Invalid extension.")
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    temp_path = _safe_library_path(f".upload-{uuid.uuid4().hex}.epub")
    try:
        copy_limited(file.file, __import__("pathlib").Path(temp_path), app_config.security.upload_max_bytes)
        validate_epub_archive(
            temp_path,
            max_members=app_config.security.epub_max_members,
            max_uncompressed_bytes=app_config.security.epub_max_uncompressed_bytes,
            max_compression_ratio=app_config.security.epub_max_compression_ratio,
        )
    except ValueError as exc:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    staging_session_dir: Path | None = None
    promoted_session_dir: Path | None = None
    try:
        source_sha256 = _sha256_file(temp_path)
        source_size = os.path.getsize(temp_path)
        parsed_book = parse_epub(temp_path)
        safe_title = sanitize_session_component(parsed_book.title, fallback="Book")
        requested_session = sanitize_session_component(session_name, fallback="Default_Session")

        with _book_import_lock(safe_title):
            book_dir = Path(_safe_library_path(safe_title))
            book_dir.mkdir(parents=True, exist_ok=True)
            _remove_orphan_import_staging(book_dir)
            existing = _existing_import(safe_title, requested_session, source_sha256)
            if existing is not None:
                existing_session = str(existing["session_name"])
                existing_dir = _safe_library_path(safe_title, existing_session)
                session_manager.set_book(_session_key(safe_title, existing_session), parsed_book, session_dir=existing_dir)
                os.remove(temp_path)
                return {
                    "book_name": safe_title,
                    "session_name": existing_session,
                    "total_chapters": parsed_book.total_chapters,
                    "series_matches": find_series_matches(
                        LIBRARY_DIR,
                        parsed_book.title,
                        parsed_book.author,
                        exclude_book_name=safe_title,
                    ),
                    "inherited_graph": bool(existing.get("inherited_graph", False)),
                }

            safe_session = _allocate_import_session(safe_title, requested_session, source_sha256)
            session_key = _session_key(safe_title, safe_session)
            session_dir = Path(_safe_library_path(safe_title, safe_session))
            staging_dir = book_dir / f".{safe_session}.staging-{uuid.uuid4().hex}"
            staging_session_dir = staging_dir
            staging_dir.mkdir(parents=False, exist_ok=False)
            (staging_dir / "database").mkdir()
            shutil.move(temp_path, staging_dir / "source.epub")

            inherited_graph = False
            resolved_parent_session = series_parent_session
            if series_parent_book:
                resolved_parent_session = series_parent_session or latest_session_for_book(LIBRARY_DIR, series_parent_book)
                if not resolved_parent_session:
                    raise HTTPException(status_code=404, detail="Series parent session not found.")
                _safe_library_path(series_parent_book, resolved_parent_session)
                inherited_graph = inherit_series_graph(
                    LIBRARY_DIR,
                    series_parent_book,
                    resolved_parent_session,
                    str(staging_dir),
                    target_book=safe_title,
                    target_session=safe_session,
                )

            write_continuity_metadata(
                str(staging_dir),
                safe_title,
                series_parent_book,
                resolved_parent_session,
                inherited_graph,
                "inherited-series" if inherited_graph else "standalone",
            )
            if session_dir.exists():
                raise HTTPException(status_code=409, detail="Session identity became occupied during import.")
            os.replace(staging_dir, session_dir)
            staging_session_dir = None
            promoted_session_dir = session_dir
            session_manager.register_imported_book(
                session_key,
                parsed_book,
                str(session_dir),
                {
                    "book_name": safe_title,
                    "session_name": safe_session,
                    "requested_session_name": requested_session,
                    "label": session_name.strip() or safe_session,
                    "session_name_quality": "sanitized",
                    "author": parsed_book.author,
                    "imported_at": time.time(),
                    "total_words": sum(chapter.word_count for chapter in parsed_book.chapters),
                    "source_epub_relpath": "source.epub",
                    "source_sha256": source_sha256,
                    "source_size_bytes": source_size,
                    "original_filename": original_filename,
                    "source_format_version": "bookbuddy_session_source_v1",
                    "import_revision": 1,
                    "inherited_graph": inherited_graph,
                },
            )
            promoted_session_dir = None

        series_matches = find_series_matches(
            LIBRARY_DIR,
            parsed_book.title,
            parsed_book.author,
            exclude_book_name=safe_title,
        )
        supervisor_key = f"search::{session_key}"
        search_factory = lambda: _index_book_background(supervisor_key, session_key, parsed_book)
        task_supervisor.submit(supervisor_key, search_factory(), task_type="search_index", retry_factory=search_factory)
        
        return {
            "book_name": safe_title,
            "session_name": safe_session,
            "total_chapters": parsed_book.total_chapters,
            "series_matches": series_matches,
            "inherited_graph": inherited_graph,
        }
    except HTTPException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if staging_session_dir is not None and staging_session_dir.is_dir() and not _is_reparse_point(staging_session_dir):
            shutil.rmtree(staging_session_dir)
        if promoted_session_dir is not None and promoted_session_dir.is_dir() and not _is_reparse_point(promoted_session_dir):
            shutil.rmtree(promoted_session_dir)
        raise
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if staging_session_dir is not None and staging_session_dir.is_dir() and not _is_reparse_point(staging_session_dir):
            shutil.rmtree(staging_session_dir)
        if promoted_session_dir is not None and promoted_session_dir.is_dir() and not _is_reparse_point(promoted_session_dir):
            shutil.rmtree(promoted_session_dir)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/book/{book_name}/{session_name}")
def get_book_metadata(book_name: str, session_name: str):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    
    if not book: raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    chapters = [
        {
            "index": ch.index,
            "title": ch.title,
            "item_id": ch.item_id,
            "spine_href": getattr(ch, "spine_href", ""),
            "section_type": ch.section_type,
            "word_count": int(getattr(ch, "word_count", 0) or 0),
            "book_name": str(getattr(ch, "book_name", "") or book.title),
        }
        for ch in book.chapters
    ]
    navigation_books = [
        {
            "book_id": nav_book.book_id,
            "title": nav_book.title,
            "source_title": nav_book.source_title,
            "ordinal": nav_book.ordinal,
            "start_chapter_index": nav_book.start_chapter_index,
            "end_chapter_index": nav_book.end_chapter_index,
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "spine_href": entry.spine_href,
                    "depth": entry.depth,
                    "kind": entry.kind,
                    "display_number": entry.display_number,
                    "chapter_index": entry.chapter_index,
                }
                for entry in nav_book.entries
            ],
        }
        for nav_book in getattr(book, "navigation_books", [])
    ]
    return {
        "schema_version": "bookbuddy_book_v1",
        "title": book.title,
        "author": book.author,
        "total_chapters": book.total_chapters,
        "word_count": sum(item["word_count"] for item in chapters),
        "chapters": chapters,
        "table_of_contents": [{"index": item["index"], "title": item["title"], "book_name": item["book_name"]} for item in chapters],
        "navigation": {
            "schema_version": "bookbuddy_navigation_v1",
            "mode": getattr(book, "navigation_mode", "single"),
            "books": navigation_books,
        },
    }


@app.get("/reader/{book_name}/{session_name}/epub")
def stream_reader_epub(book_name: str, session_name: str):
    path = _session_epub_path(book_name, session_name)
    return FileResponse(path, media_type="application/epub+zip", filename=os.path.basename(path), content_disposition_type="inline")


@app.get("/reader/{book_name}/{session_name}/cover")
def stream_reader_cover(request: Request, book_name: str, session_name: str, size: int = Query(default=320)):
    # Query parameters arrive as strings. Pydantic v2 intentionally does not coerce
    # integer Literals, which made every real `?size=320` request fail with 422.
    if size not in {160, 320, 640}:
        raise HTTPException(status_code=422, detail="size must be 160, 320, or 640")
    _require_reader_session(book_name, session_name)
    result = _extract_cover(book_name, session_name, size)
    if not result:
        raise HTTPException(status_code=404, detail="Book cover not found.")
    path, media_type = result
    digest = resource_manager.cover_hash(_session_key(book_name, session_name)) if resource_manager is not None else None
    etag = f'"{digest}-{size}"' if digest else None
    if etag and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=86400"})
    headers = {"Cache-Control": "private, max-age=86400"}
    if etag:
        headers["ETag"] = etag
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path), content_disposition_type="inline", headers=headers)


@app.get("/reader/{book_name}/{session_name}/search/status")
def reader_search_status(book_name: str, session_name: str):
    session_key = _require_reader_session(book_name, session_name)
    status = reader_search.status(session_key)
    index_schema_version = status.pop("schema_version", 0)
    return {"schema_version": "bookbuddy_reader_search_status_v1", "index_schema_version": index_schema_version, **status}


@app.get("/reader/{book_name}/{session_name}/search")
def search_reader_text(book_name: str, session_name: str, q: str = Query(min_length=1, max_length=200), limit: int = Query(default=50, ge=1, le=100), max_chapter: int | None = Query(default=None, ge=0), chapter: int | None = Query(default=None, ge=0)):
    session_key = _require_reader_session(book_name, session_name)
    try:
        result = reader_search.search(session_key, q, limit=limit, max_chapter=max_chapter, chapter=chapter)
        return {"schema_version": "bookbuddy_reader_search_v1", **result}
    except LookupError as exc:
        raise HTTPException(status_code=409, detail={"code":"search_index_not_ready","message":str(exc)}) from exc


@app.post("/reader/{book_name}/{session_name}/search/rebuild", status_code=202)
def rebuild_reader_search(book_name: str, session_name: str):
    session_key = _require_reader_session(book_name, session_name)
    book = session_manager.get_book(session_key)
    if not book: raise HTTPException(status_code=409, detail="Load the book before rebuilding search.")
    search_factory = lambda: asyncio.to_thread(reader_search.index_book, session_key, book)
    task_supervisor.submit(f"search::{session_key}", search_factory(), task_type="search_index", retry_factory=search_factory)
    return {"schema_version":"bookbuddy_reader_search_rebuild_v1","queued":True,"session_key":session_key}

@app.get("/chapter/{book_name}/{session_name}/{chapter_index}")
def get_chapter_data(book_name: str, session_name: str, chapter_index: int):
    db_dir = _safe_db_dir(book_name, session_name)
    chapter_file = os.path.join(db_dir, f"chapter_{chapter_index}.json")
    graph_path = os.path.join(db_dir, "graph.db")

    if os.path.exists(graph_path):
        db = database_registry.open(db_dir)
        try:
            active_payload = EvidenceStore.active_payload(db, chapter_index)
            if active_payload is not None:
                return active_payload
        finally:
            db.close()

    if os.path.exists(chapter_file):
        with open(chapter_file, "r", encoding="utf-8") as f:
            return json.load(f)
            
    raise HTTPException(status_code=404, detail="Chapter not analyzed yet. Call /analyze first.")


@app.post("/reader/{book_name}/{session_name}/highlight")
def resolve_reader_highlight(book_name: str, session_name: str, body: HighlightBody):
    session_key = _session_key(book_name, session_name)
    book: ParsedBook = session_manager.get_book(session_key)
    if not book:
        raise HTTPException(status_code=404, detail="Session is not loaded. Call /load first.")
    if body.chapter_index >= len(book.chapters):
        raise HTTPException(status_code=422, detail="chapter_index is out of range")
    db_dir = _safe_db_dir(book_name, session_name)
    graph_path = os.path.join(db_dir, "graph.db")
    db = database_registry.open(db_dir) if os.path.exists(graph_path) else None
    try:
        resolver = HighlightResolver(
            db,
            dictionary=dictionary_provider,
            pronunciation=pronunciation_provider,
            context=context_resolver,
        )
        request = HighlightRequest(**body.model_dump())
        return resolver.resolve(request, book.chapters[body.chapter_index].content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        if db is not None:
            db.close()


@app.post("/reader/{book_name}/{session_name}/explain-selection")
def explain_reader_selection(book_name: str, session_name: str, body: SelectionExplainBody):
    session_key = _require_reader_session(book_name, session_name)
    book: ParsedBook = session_manager.get_book(session_key)
    if not book:
        raise HTTPException(status_code=404, detail="Session is not loaded. Call /load first.")
    if body.chapter_index >= len(book.chapters) or body.knowledge_as_of_chapter > body.chapter_index - 1:
        raise HTTPException(status_code=422, detail="Invalid spoiler-safe chapter boundary.")
    if not ai_manager.is_available("text"):
        raise HTTPException(status_code=503, detail={"code": "ai_service_unavailable", "capability": "selection_explanation"})
    prompt = (
        "Explain the selected words using only the sentence supplied below. Do not infer, reveal, or mention events "
        "outside this text. Answer in two concise paragraphs: meaning here, then why the wording matters.\n\n"
        f"Selected text: {body.selected_text}\nContext: {body.context_text}"
    )
    try:
        result = ai_manager.generate(GenerationRequest(role="dictionary", prompt=prompt, temperature=0.0, safety_profile="reader", metadata={"chapter_index": body.chapter_index, "knowledge_as_of_chapter": body.knowledge_as_of_chapter}))
    except AIServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail={"code": "ai_service_unavailable", "capability": "selection_explanation"}) from exc
    return {"schema_version": "bookbuddy_selection_explanation_v1", "explanation": result.text, "provider": result.provider}


@app.post("/reader/{book_name}/{session_name}/translate-selection")
def translate_reader_selection(book_name: str, session_name: str, body: SelectionTranslationBody):
    _require_reader_session(book_name, session_name)
    if not ai_manager.is_available("text"):
        raise HTTPException(status_code=503, detail={"code": "ai_service_unavailable", "capability": "translation"})
    prompt = (
        f"Translate the text below into {body.target_language}. Preserve tone, names, punctuation, and paragraph breaks. "
        "Return only the translation. Do not add explanations or infer any story context.\n\n"
        f"Text:\n{body.selected_text}"
    )
    try:
        result = ai_manager.generate(GenerationRequest(role="translation", prompt=prompt, temperature=0.0, safety_profile="reader", metadata={"target_language": body.target_language}))
    except AIServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail={"code": "ai_service_unavailable", "capability": "translation"}) from exc
    translation = result.text.strip()
    if not translation:
        raise HTTPException(status_code=502, detail={"code": "invalid_ai_response", "capability": "translation"})
    return {"schema_version": "bookbuddy_selection_translation_v1", "translation": translation, "target_language": body.target_language, "provider": result.provider}


@app.get("/dictionary/pronunciation/audio/{audio_id}")
def stream_pronunciation_audio(audio_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", audio_id):
        raise HTTPException(status_code=404, detail="Audio not found.")
    path = pronunciation_provider.audio_path(audio_id)
    if not path:
        raise HTTPException(status_code=404, detail="Audio not found.")
    media_types = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
    media_type = media_types.get(path.suffix.lower())
    if not media_type:
        raise HTTPException(status_code=415, detail="Unsupported audio type.")
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/reader/profile")
def create_reader_profile():
    return {"user_id": reader_knowledge_store.create_profile()}


def _reader_state_error(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def _split_session_key(session_key: str) -> tuple[str, str]:
    if "::" not in session_key:
        raise HTTPException(status_code=422, detail="Invalid session key.")
    book_name, session_name = session_key.split("::", 1)
    _require_reader_session(book_name, session_name)
    return book_name, session_name


@app.get("/reader/{user_id}/library-state")
def get_reader_library_state(user_id: str):
    try:
        state = reader_knowledge_store.library_state(user_id)
    except Exception as exc:
        return _reader_state_error(exc)
    known = {item["session_key"] for item in session_manager.list_sessions(include_deleted=False, validate=False)}
    state["books"] = [item for item in state["books"] if item["session_key"] in known]
    state["chapters"] = [item for item in state["chapters"] if item["session_key"] in known]
    state["bookmarks"] = [item for item in state["bookmarks"] if item["session_key"] in known]
    for collection in state["collections"]:
        collection["session_keys"] = [key for key in collection["session_keys"] if key in known]
    for key in state["smart_collections"]:
        state["smart_collections"][key] = [item for item in state["smart_collections"][key] if item in known]
    return state


@app.put("/reader/{user_id}/books/{book_name}/{session_name}")
def put_reader_book_state(user_id: str, book_name: str, session_name: str, body: ReaderBookStateBody):
    session_key = _require_reader_session(book_name, session_name)
    try:
        return {"schema_version": "bookbuddy_reader_book_state_v1", "book": reader_knowledge_store.upsert_book_state(user_id, session_key, body.model_dump(exclude_none=True))}
    except Exception as exc:
        return _reader_state_error(exc)


@app.put("/reader/{user_id}/books/{book_name}/{session_name}/chapters/{chapter_index}")
def put_reader_chapter_progress(user_id: str, book_name: str, session_name: str, chapter_index: int, body: ReaderChapterProgressBody):
    session_key = _require_reader_session(book_name, session_name)
    metadata = session_manager.get_session_metadata(session_key)
    total = metadata.get("total_chapters")
    if chapter_index < 0 or (isinstance(total, int) and chapter_index >= total):
        raise HTTPException(status_code=422, detail="chapter_index is out of range")
    try:
        return {"schema_version": "bookbuddy_reader_chapter_progress_v1", "chapter": reader_knowledge_store.upsert_chapter_progress(user_id, session_key, chapter_index, body.model_dump())}
    except Exception as exc:
        return _reader_state_error(exc)


@app.post("/reader/{user_id}/state/import")
def import_reader_state(user_id: str, body: ReaderStateImportBody):
    try:
        known = {item["session_key"] for item in session_manager.list_sessions(include_deleted=False, validate=False)}
        books = [item for item in body.books if str(item.get("session_key", "")) in known]
        chapters = [item for item in body.chapters if str(item.get("session_key", "")) in known and int(item.get("chapter_index", -1)) >= 0]
        return reader_knowledge_store.import_legacy_state(user_id, books, chapters)
    except HTTPException:
        raise
    except Exception as exc:
        return _reader_state_error(exc)


@app.post("/reader/{user_id}/collections")
def create_reader_collection(user_id: str, body: ReaderCollectionBody):
    try:
        return {"schema_version": "bookbuddy_reader_collection_v1", "collection": reader_knowledge_store.create_collection(user_id, body.name or "")}
    except Exception as exc:
        return _reader_state_error(exc)


@app.put("/reader/{user_id}/collections/{collection_id}")
def update_reader_collection(user_id: str, collection_id: str, body: ReaderCollectionBody):
    try:
        return {"schema_version": "bookbuddy_reader_collection_v1", "collection": reader_knowledge_store.update_collection(user_id, collection_id, body.name, body.sort_order)}
    except Exception as exc:
        return _reader_state_error(exc)


@app.delete("/reader/{user_id}/collections/{collection_id}")
def delete_reader_collection(user_id: str, collection_id: str):
    try:
        reader_knowledge_store.delete_collection(user_id, collection_id)
        return {"schema_version": "bookbuddy_reader_collection_v1", "deleted": True}
    except Exception as exc:
        return _reader_state_error(exc)


@app.put("/reader/{user_id}/collections/{collection_id}/member")
def put_reader_collection_member(user_id: str, collection_id: str, body: ReaderCollectionMemberBody):
    _split_session_key(body.session_key)
    try:
        return {"schema_version": "bookbuddy_reader_collection_v1", "collection": reader_knowledge_store.set_collection_member(user_id, collection_id, body.session_key, body.present)}
    except Exception as exc:
        return _reader_state_error(exc)


@app.get("/reader/{user_id}/bookmarks")
def get_reader_bookmarks(user_id: str):
    try:
        return {"schema_version": "bookbuddy_reader_bookmarks_v1", "bookmarks": reader_knowledge_store.library_state(user_id)["bookmarks"]}
    except Exception as exc:
        return _reader_state_error(exc)


@app.post("/reader/{user_id}/books/{book_name}/{session_name}/bookmarks")
def create_reader_bookmark(user_id: str, book_name: str, session_name: str, body: ReaderBookmarkBody):
    session_key = _require_reader_session(book_name, session_name)
    metadata = session_manager.get_session_metadata(session_key)
    total = metadata.get("total_chapters")
    if isinstance(total, int) and body.chapter_index >= total:
        raise HTTPException(status_code=422, detail="chapter_index is out of range")
    try:
        bookmark = reader_knowledge_store.create_bookmark(user_id, session_key, body.chapter_index, body.cfi, body.excerpt, body.name)
        return {"schema_version": "bookbuddy_reader_bookmark_v1", "bookmark": bookmark}
    except Exception as exc:
        return _reader_state_error(exc)


@app.delete("/reader/{user_id}/bookmarks/{bookmark_id}")
def delete_reader_bookmark(user_id: str, bookmark_id: str):
    try:
        reader_knowledge_store.delete_bookmark(user_id, bookmark_id)
        return {"schema_version": "bookbuddy_reader_bookmark_v1", "deleted": True}
    except Exception as exc:
        return _reader_state_error(exc)


@app.patch("/reader/{user_id}/bookmarks/{bookmark_id}")
def update_reader_bookmark(user_id: str, bookmark_id: str, body: ReaderBookmarkUpdateBody):
    try:
        return {"schema_version": "bookbuddy_reader_bookmark_v1", "bookmark": reader_knowledge_store.update_bookmark(user_id, bookmark_id, body.name)}
    except Exception as exc:
        return _reader_state_error(exc)


@app.get("/reader/{user_id}/annotations")
def list_reader_annotations(user_id: str, session_key: str | None = Query(default=None, max_length=240), query: str = Query(default="", max_length=200)):
    try:
        return {"schema_version": "bookbuddy_reader_annotations_v1", "annotations": reader_knowledge_store.list_annotations(user_id, session_key, query)}
    except Exception as exc:
        return _reader_state_error(exc)


@app.post("/reader/{user_id}/books/{book_name}/{session_name}/annotations")
def create_reader_annotation(user_id: str, book_name: str, session_name: str, body: ReaderAnnotationBody):
    session_key = _require_reader_session(book_name, session_name)
    try:
        annotation = reader_knowledge_store.create_annotation(user_id, session_key, body.chapter_index, body.cfi_range, body.quote, body.annotation_type, body.color, body.note_text)
        return {"schema_version": "bookbuddy_reader_annotation_v1", "annotation": annotation}
    except Exception as exc:
        return _reader_state_error(exc)


@app.patch("/reader/{user_id}/annotations/{annotation_id}")
def update_reader_annotation(user_id: str, annotation_id: str, body: ReaderAnnotationUpdateBody):
    try:
        return {"schema_version": "bookbuddy_reader_annotation_v1", "annotation": reader_knowledge_store.update_annotation(user_id, annotation_id, body.model_dump(exclude_none=True))}
    except Exception as exc:
        return _reader_state_error(exc)


@app.delete("/reader/{user_id}/annotations/{annotation_id}")
def delete_reader_annotation(user_id: str, annotation_id: str):
    try:
        reader_knowledge_store.delete_annotation(user_id, annotation_id)
        return {"schema_version": "bookbuddy_reader_annotation_v1", "deleted": True}
    except Exception as exc:
        return _reader_state_error(exc)


@app.get("/reader/{user_id}/books/{book_name}/{session_name}/annotations/export")
def export_reader_annotations(user_id: str, book_name: str, session_name: str):
    session_key = _require_reader_session(book_name, session_name)
    annotations = reader_knowledge_store.list_annotations(user_id, session_key)
    title, author = _epub_package_metadata(_session_epub_path(book_name, session_name))
    lines = [f"# {title or book_name}", "", f"Author: {author or 'Unknown'}", ""]
    for item in sorted(annotations, key=lambda value: (value["chapter_index"], value["created_at"])):
        lines.extend([f"## Chapter {item['chapter_index'] + 1}", "", f"> {item['quote']}", "", item["note_text"] or f"_{item['annotation_type']}_", "", f"Location: `{item['cfi_range']}`", ""])
    return StreamingResponse(iter(["\n".join(lines).encode("utf-8")]), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="bookbuddy-notes.md"'})


@app.post("/reader/{user_id}/books/{book_name}/{session_name}/reading-sessions")
def record_reader_session(user_id: str, book_name: str, session_name: str, body: ReaderSessionBody):
    session_key = _require_reader_session(book_name, session_name)
    try:
        session = reader_knowledge_store.record_reading_session(user_id, session_key, body.started_at, body.ended_at, body.active_seconds, body.start_progress, body.end_progress)
        return {"schema_version": "bookbuddy_reading_session_v1", "session": session}
    except Exception as exc:
        return _reader_state_error(exc)


@app.get("/reader/{user_id}/statistics")
def get_reader_statistics(user_id: str):
    try:
        return {"schema_version": "bookbuddy_reader_statistics_v1", "statistics": reader_knowledge_store.reading_statistics(user_id)}
    except Exception as exc:
        return _reader_state_error(exc)


@app.get("/reader/{user_id}/statistics/export")
def export_reader_statistics(user_id: str):
    try:
        payload = {
            "schema_version": "bookbuddy_reader_telemetry_export_v1",
            "statistics": reader_knowledge_store.reading_statistics(user_id),
            "sessions": reader_knowledge_store.export_reading_sessions(user_id),
        }
        return StreamingResponse(
            iter([json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")]),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="bookbuddy-reading-data.json"'},
        )
    except Exception as exc:
        return _reader_state_error(exc)


@app.delete("/reader/{user_id}/statistics")
def reset_reader_statistics(user_id: str):
    try:
        return {
            "schema_version": "bookbuddy_reader_statistics_reset_v1",
            "deleted_sessions": reader_knowledge_store.reset_reading_sessions(user_id),
        }
    except Exception as exc:
        return _reader_state_error(exc)


def _validate_knowledge_object(book_name: str, session_name: str, object_kind: str, object_id: int):
    if object_kind not in {"entity", "terminology"}:
        raise HTTPException(status_code=422, detail="object_kind must be entity or terminology")
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = database_registry.open(db_dir)
    try:
        table = "entities" if object_kind == "entity" else "terminology_objects"
        if not db._get_connection().execute(f"SELECT 1 FROM {table} WHERE id = ?", (object_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Knowledge object not found.")
    finally:
        db.close()


@app.post("/reader/{book_name}/{session_name}/knowledge/{object_kind}/{object_id}/view")
def record_knowledge_view(book_name: str, session_name: str, object_kind: str, object_id: int, body: ReaderProfileBody):
    _validate_knowledge_object(book_name, session_name, object_kind, object_id)
    try:
        return reader_knowledge_store.record_view(body.user_id, object_kind, object_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/reader/{book_name}/{session_name}/knowledge/{object_kind}/{object_id}/mark-known")
def mark_knowledge_known(book_name: str, session_name: str, object_kind: str, object_id: int, body: ReaderFlagBody):
    _validate_knowledge_object(book_name, session_name, object_kind, object_id)
    try:
        return reader_knowledge_store.set_flag(body.user_id, object_kind, object_id, "marked_known", body.value)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/reader/{book_name}/{session_name}/knowledge/{object_kind}/{object_id}/ignore")
def ignore_knowledge_object(book_name: str, session_name: str, object_kind: str, object_id: int, body: ReaderFlagBody):
    _validate_knowledge_object(book_name, session_name, object_kind, object_id)
    try:
        return reader_knowledge_store.set_flag(body.user_id, object_kind, object_id, "ignored", body.value)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/export-graph/{book_name}/{session_name}")
def export_graph(book_name: str, session_name: str):
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = database_registry.open(db_dir)
    try:
        return db.export_graph_state()
    finally:
        db.close()


@app.get("/chapter-snapshot/{book_name}/{session_name}/{chapter_index}")
def get_chapter_snapshot(book_name: str, session_name: str, chapter_index: int, revision: int | None = None):
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = database_registry.open(db_dir)
    try:
        snapshot = SnapshotStore.get(db, chapter_index, revision)
    finally:
        db.close()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Reader snapshot not available for this chapter.")
    return snapshot


@app.get("/chapter-snapshot/{book_name}/{session_name}/{chapter_index}/history")
def get_chapter_snapshot_history(book_name: str, session_name: str, chapter_index: int):
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = database_registry.open(db_dir)
    try:
        history = SnapshotStore.history(db, chapter_index)
    finally:
        db.close()
    if not history:
        raise HTTPException(status_code=404, detail="Reader snapshot history not available for this chapter.")
    return {"chapter": chapter_index, "history": history}


@app.get(
    "/reader/{book_name}/{session_name}/entity/{entity_id}",
    response_model=ReaderEntityResponse,
)
def get_reader_entity(
    book_name: str,
    session_name: str,
    entity_id: int,
    as_of_chapter: int = Query(..., ge=0),
):
    """Return one reader-safe aggregate without exposing database rows."""
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = database_registry.open(db_dir)
    try:
        result = ReaderSnapshotBuilder(db).build_entity(entity_id, as_of_chapter)
        from dictionary_subsystem.terminology import GlossaryResolver
        try:
            result["dictionary"] = GlossaryResolver(db).lookup(
                result["entity"]["canonical_name"], as_of_chapter
            ).to_dict()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Reader entity glossary unavailable",
                extra={"entity_id": entity_id, "error_class": type(exc).__name__},
            )
            result["dictionary"] = {
                "status": "unavailable",
                "diagnostics": [{"code": "glossary_resolution_failed"}],
            }
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()


@app.get("/debug/{book_name}/{session_name}/explain/{kind}/{subject}")
def explain_engine_state(
    book_name: str,
    session_name: str,
    kind: str,
    subject: str,
    chapter: int | None = None,
    revision: int | None = None,
):
    """Internal engine-debug route; reader clients must use chapter snapshots."""
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = database_registry.open(db_dir)
    try:
        return ExplanationService(db).explain(kind, subject, chapter=chapter, revision=revision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        db.close()

# ─── BACKGROUND QUEUE ENGINE ───

async def background_analysis_task(
    book_name: str,
    session_name: str,
    target_chapter: int,
    allow_ai_vision_fallback: bool = False,
):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    db_dir = _safe_db_dir(book_name, session_name)
    
    start_chapter = _first_missing_evidence(db_dir, target_chapter)
        
    total_to_process = (target_chapter - start_chapter) + 1

    task_supervisor.cancellation_checkpoint(session_key, "before_initialization")

    session_manager.set_task(session_key, {
        "status": "processing",
        "target_chapter": target_chapter,
        "current_chapter": start_chapter,
        "progress": 0.0 if total_to_process > 0 else 100.0,
        "cancel_requested": False,
        "gemini_vision_fallback_authorized": bool(allow_ai_vision_fallback),
        "log": f"Resuming from Chapter {start_chapter}..." if start_chapter > 0 and total_to_process > 0 else ("Booting analysis..." if total_to_process > 0 else "Already up to date.")
    })

    db = None
    task_supervisor.cancellation_checkpoint(session_key, "before_session_lock")
    async with session_manager.get_lock(session_key):
        try:
            task_supervisor.cancellation_checkpoint(session_key, "after_session_lock")
            if total_to_process > 0:
                db = database_registry.open(db_dir)
                previous_events_cache = {}
                for i in range(start_chapter, target_chapter + 1):
                    task_supervisor.cancellation_checkpoint(session_key, "before_chapter_extraction")

                    session_manager.update_task(
                        session_key,
                        current_chapter=i,
                        progress=round(((i - start_chapter) / total_to_process) * 100, 1),
                        log=f"Processing Chapter {i}..."
                    )
                    
                    # Extraction appends immutable evidence. Derived graph work is replayed
                    # in staging below, after every requested chapter is available.
                    await asyncio.to_thread(
                        parser_service.process_chapter,
                        i,
                        book,
                        db_dir,
                        db,
                        previous_events_cache,
                        False,
                        False,
                        "new_chapter",
                        allow_ai_vision_fallback,
                    )
                    task_supervisor.cancellation_checkpoint(session_key, "after_chapter_extraction")
                    session_manager.update_task(
                        session_key,
                        last_analyzed_chapter=i,
                    )

            if db is not None:
                db.close()
                db = None
            session_manager.update_task(session_key, log="Replaying immutable chapter evidence...")
            task_supervisor.cancellation_checkpoint(session_key, "before_replay")
            replay_result = await asyncio.to_thread(replay_service.coordinator(db_dir).replay, "new_chapter")
            task_supervisor.cancellation_checkpoint(session_key, "after_replay")
            task_supervisor.cancellation_checkpoint(session_key, "before_completion")
            session_manager.update_task(
                session_key,
                last_successful_graph_version=GRAPH_SCHEMA_VERSION,
                replay_result=replay_result,
            )
            
            session_manager.update_task(
                session_key,
                status="completed",
                progress=100.0,
                log="Analysis successfully completed."
            )
            
        except Exception as e:
            session_manager.update_task(session_key, status="error", log=f"Crash: {str(e)}")
            raise
        finally:
            if db is not None:
                db.close()


async def background_rebuild_task(
    book_name: str,
    session_name: str,
    reason: str = "manual_rebuild",
    mode: str = "normal",
):
    session_key = f"{book_name}::{session_name}"
    db_dir = _safe_db_dir(book_name, session_name)
    task_supervisor.cancellation_checkpoint(session_key, "before_replay_lock")
    async with session_manager.get_lock(session_key):
        try:
            task_supervisor.cancellation_checkpoint(session_key, "after_replay_lock")
            session_manager.set_task(session_key, {
                "status": "processing",
                "progress": 0.0,
                "log": "Replaying immutable chapter evidence...",
                "cancel_requested": False,
            })
            task_supervisor.cancellation_checkpoint(session_key, "before_replay")
            result = await asyncio.to_thread(replay_service.coordinator(db_dir).run, mode=mode, reason=reason)
            task_supervisor.cancellation_checkpoint(session_key, "after_replay")
            session_manager.update_task(
                session_key,
                status="completed",
                progress=100.0,
                log="Graph replay completed.",
                last_successful_graph_version=GRAPH_SCHEMA_VERSION,
                replay_result=result,
            )
        except Exception as exc:
            session_manager.update_task(session_key, status="error", log=f"Replay crash: {exc}")
            raise


async def background_reextract_task(
    book_name: str,
    session_name: str,
    chapter_index: int,
    reason: str = "explicit_reextract",
    allow_ai_vision_fallback: bool = False,
):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    db_dir = _safe_db_dir(book_name, session_name)
    if not book:
        session_manager.update_task(session_key, status="error", log="Session is not loaded.")
        return
    task_supervisor.cancellation_checkpoint(session_key, "before_reextract_lock")
    async with session_manager.get_lock(session_key):
        task_supervisor.cancellation_checkpoint(session_key, "after_reextract_lock")
        db = database_registry.open(db_dir)
        try:
            session_manager.set_task(session_key, {
                "status": "processing",
                "target_chapter": chapter_index,
                "current_chapter": chapter_index,
                "progress": 0.0,
                "log": f"Re-extracting Chapter {chapter_index}...",
                "cancel_requested": False,
            })
            task_supervisor.cancellation_checkpoint(session_key, "before_chapter_extraction")
            await asyncio.to_thread(
                parser_service.process_chapter,
                chapter_index,
                book,
                db_dir,
                db,
                {},
                False,
                True,
                reason,
                allow_ai_vision_fallback,
            )
            task_supervisor.cancellation_checkpoint(session_key, "after_chapter_extraction")
        except Exception as exc:
            session_manager.update_task(session_key, status="error", log=f"Re-extraction crash: {exc}")
            raise
        finally:
            db.close()
        try:
            session_manager.update_task(session_key, log="Replaying revised chapter evidence...")
            task_supervisor.cancellation_checkpoint(session_key, "before_replay")
            result = await asyncio.to_thread(replay_service.coordinator(db_dir).replay, reason)
            task_supervisor.cancellation_checkpoint(session_key, "after_replay")
            session_manager.update_task(
                session_key,
                status="completed",
                progress=100.0,
                log="Re-extraction and graph replay completed.",
                last_analyzed_chapter=chapter_index,
                last_successful_graph_version=GRAPH_SCHEMA_VERSION,
                replay_result=result,
            )
        except Exception as exc:
            session_manager.update_task(session_key, status="error", log=f"Re-extraction replay crash: {exc}")
            raise

@app.post("/analyze/{book_name}/{session_name}/{chapter_index}", status_code=202)
async def trigger_analysis(
    book_name: str,
    session_name: str,
    chapter_index: int,
    use_gemini_vision: bool = Query(
        default=False,
        description=(
            "Authorize conditional Gemini Vision fallback after local image tools are insufficient. "
            "This consumes only GEMINI_VISION_API_KEY* quota."
        ),
    ),
):
    session_key = f"{book_name}::{session_name}"
    allow_ai_vision_fallback = bool(use_gemini_vision)
    book: ParsedBook = session_manager.get_book(session_key)
    
    if not book: 
        raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    if chapter_index < 0 or chapter_index >= book.total_chapters: 
        raise HTTPException(status_code=404, detail="Chapter out of bounds.")
    
    task_state = session_manager.get_task(session_key)
    if task_state.get("status") == "processing":
        return {"message": "Analysis is already actively running.", "session_key": session_key}

    db_dir = _safe_db_dir(book_name, session_name)
    needs_generation = _first_missing_evidence(db_dir, chapter_index) <= chapter_index
    if needs_generation and not ai_manager.is_available("text"):
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_service_unavailable", "capability": "chapter_analysis"},
        )
    analysis_factory = lambda: background_analysis_task(book_name, session_name, chapter_index, allow_ai_vision_fallback)
    task_supervisor.submit(session_key, analysis_factory(), retry_factory=analysis_factory)
    return {
        "message": "Analysis queued and initiated.",
        "session_key": session_key,
        "gemini_vision_fallback_authorized": bool(use_gemini_vision),
    }


@app.post("/rebuild/{book_name}/{session_name}", status_code=202)
async def trigger_rebuild(
    book_name: str,
    session_name: str,
    reason: str = "manual_rebuild",
    mode: str = "normal",
):
    db_dir = _safe_db_dir(book_name, session_name)
    if not os.path.isdir(db_dir):
        raise HTTPException(status_code=404, detail="Session database not found.")
    session_key = f"{book_name}::{session_name}"
    if session_manager.get_task(session_key).get("status") == "processing":
        raise HTTPException(status_code=409, detail="Analysis is already actively running.")
    if not str(reason or "").strip():
        raise HTTPException(status_code=400, detail="Rebuild reason must not be empty.")
    if mode not in {"normal", "full", "verify"}:
        raise HTTPException(status_code=400, detail="Replay mode must be normal, full, or verify.")
    rebuild_factory = lambda: background_rebuild_task(book_name, session_name, reason, mode)
    task_supervisor.submit(session_key, rebuild_factory(), task_type="replay", retry_factory=rebuild_factory)
    return {"message": "Graph replay queued.", "session_key": session_key, "mode": mode}


@app.post("/reanalyze/{book_name}/{session_name}/{chapter_index}", status_code=202)
async def trigger_reanalysis(
    book_name: str,
    session_name: str,
    chapter_index: int,
    reason: str = "explicit_reextract",
    use_gemini_vision: bool = Query(
        default=False,
        description=(
            "Authorize conditional Gemini Vision fallback after local image tools are insufficient. "
            "This consumes only GEMINI_VISION_API_KEY* quota."
        ),
    ),
):
    session_key = f"{book_name}::{session_name}"
    allow_ai_vision_fallback = bool(use_gemini_vision)
    book: ParsedBook = session_manager.get_book(session_key)
    if not book:
        raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    if chapter_index < 0 or chapter_index >= book.total_chapters:
        raise HTTPException(status_code=404, detail="Chapter out of bounds.")
    if session_manager.get_task(session_key).get("status") == "processing":
        raise HTTPException(status_code=409, detail="Analysis is already actively running.")
    if not str(reason or "").strip():
        raise HTTPException(status_code=400, detail="Re-extraction reason must not be empty.")
    if not ai_manager.is_available("text"):
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_service_unavailable", "capability": "chapter_analysis"},
        )
    reextract_factory = lambda: background_reextract_task(book_name, session_name, chapter_index, reason, allow_ai_vision_fallback)
    task_supervisor.submit(session_key, reextract_factory(), retry_factory=reextract_factory)
    return {
        "message": "Chapter re-extraction queued.",
        "session_key": session_key,
        "gemini_vision_fallback_authorized": bool(use_gemini_vision),
    }

@app.post("/cancel/{book_name}/{session_name}", status_code=202)
async def cancel_analysis(book_name: str, session_name: str):
    session_key = f"{book_name}::{session_name}"
    try:
        task = task_supervisor.request_cancel(session_key=session_key)
    except LookupError:
        raise HTTPException(status_code=409, detail="No active analysis is running for this session.")
    return {"schema_version": "bookbuddy_task_v1", "task": task}

@app.get("/stream-status/{book_name}/{session_name}")
async def stream_analysis_status(book_name: str, session_name: str):
    session_key = f"{book_name}::{session_name}"
    
    async def event_generator():
        while True:
            task_state = session_manager.get_task(session_key, {"status": "idle", "progress": 0.0, "log": "Awaiting commands."})
            yield f"data: {json.dumps(task_state)}\n\n"
            
            if task_state["status"] in ["completed", "cancelled", "error"]:
                break
                
            await asyncio.sleep(1)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _reader_analysis_context(book_name: str, session_name: str, chapter_index: int):
    session_key = _session_key(book_name, session_name)
    book: ParsedBook = session_manager.get_book(session_key)
    if not book:
        raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    if chapter_index < 0 or chapter_index >= book.total_chapters:
        raise HTTPException(status_code=404, detail="Chapter out of bounds.")
    return session_key, book, _safe_db_dir(book_name, session_name)


@app.post("/reader/{book_name}/{session_name}/analysis/{chapter_index}/stage", status_code=202)
async def stage_reader_chapter(book_name: str, session_name: str, chapter_index: int):
    session_key, book, db_dir = _reader_analysis_context(book_name, session_name, chapter_index)
    chapter = book.chapters[chapter_index]
    if chapter.section_type != "FRONT_BACK_MATTER" and not ai_manager.is_available("text"):
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_service_unavailable", "capability": "chapter_analysis"},
        )
    return {
        "schema_version": "reader_analysis_job_v1",
        "job": await reader_analysis.stage(session_key, chapter_index, book, db_dir),
    }


@app.post("/reader/{book_name}/{session_name}/analysis/{chapter_index}/complete", status_code=202)
async def complete_reader_chapter(book_name: str, session_name: str, chapter_index: int):
    session_key, book, db_dir = _reader_analysis_context(book_name, session_name, chapter_index)
    chapter = book.chapters[chapter_index]
    if chapter.section_type != "FRONT_BACK_MATTER" and not ai_manager.is_available("text"):
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_service_unavailable", "capability": "chapter_analysis"},
        )
    return {
        "schema_version": "reader_analysis_job_v1",
        "job": await reader_analysis.complete(session_key, chapter_index, book, db_dir),
    }


@app.delete("/reader/{book_name}/{session_name}/analysis/{chapter_index}/stage")
async def discard_reader_chapter(book_name: str, session_name: str, chapter_index: int):
    session_key, _, _ = _reader_analysis_context(book_name, session_name, chapter_index)
    return {
        "schema_version": "reader_analysis_job_v1",
        "job": await reader_analysis.cancel(session_key, chapter_index),
    }


@app.get("/reader/{book_name}/{session_name}/analysis/status")
def reader_analysis_status(book_name: str, session_name: str):
    session_key = _session_key(book_name, session_name)
    if not session_manager.get_session_metadata(session_key) and not session_manager.get_book(session_key):
        raise HTTPException(status_code=404, detail="Session not found.")
    return reader_analysis.status(session_key)


_APPLICATION_ROUTES = tuple(
    route
    for route in _route_registry.router.routes
    if getattr(route, "name", "") not in {"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"}
)


def create_app(config: AppConfig | None = None, services: AppServices | None = None) -> FastAPI:
    """Create an ASGI application whose services are initialized by lifespan."""
    middleware_config = config or (services.config if services is not None else load_config())

    @asynccontextmanager
    async def lifespan(api: FastAPI):
        active_config = config or (services.config if services is not None else load_config())
        logging.basicConfig(
            level=getattr(logging, active_config.server.log_level, logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _, file_handler, owns_file_handler = configure_file_logging(
            active_config.paths.log_dir,
            getattr(logging, active_config.server.log_level, logging.INFO),
        )
        logger = logging.getLogger("bookbuddy.startup")
        logger.info("Starting BookBuddy Backend")
        logger.info("Loading configuration")
        active_services = services or bootstrap_application(active_config)
        _bind_services(active_services)
        api.state.services = active_services
        logger.info("Registering routes")
        logger.info("Backend ready")
        try:
            yield
        finally:
            try:
                logger.info("Stopping BookBuddy Backend")
                await active_services.shutdown()
                logger.info("Backend stopped")
            finally:
                close_file_logging(file_handler, owned=owns_file_handler)

    api = FastAPI(title="BookBuddy API", lifespan=lifespan)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(middleware_config.security.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_token = os.environ.get("BOOKBUDDY_API_TOKEN", "").strip()
    if api_token:
        @api.middleware("http")
        async def require_api_token(request: Request, call_next):
            if request.method == "OPTIONS":
                return await call_next(request)
            supplied = request.headers.get("authorization", "")
            expected = f"Bearer {api_token}"
            if not secrets.compare_digest(supplied, expected):
                return JSONResponse(status_code=401, content={"detail": "Invalid BookBuddy API token."})
            return await call_next(request)
    api.router.routes.extend(_APPLICATION_ROUTES)
    return api


app = create_app()
