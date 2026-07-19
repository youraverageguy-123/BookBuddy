from dependency_manager import ensure_dependencies

ensure_dependencies("BookBuddy API")

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import os
import shutil
import re
import asyncio
import json
from epub_parser import parse_epub, ParsedBook
from analysis_engine import process_single_chapter
from continuity_manager import (
    find_series_matches,
    inherit_series_graph,
    latest_session_for_book,
    write_continuity_metadata,
)
from db_manager import BookDatabase
from explanation_service import ExplanationService
from key_manager import GeminiKeyManager
from session_manager import SessionManager, sanitize_session_component
from snapshot_manager import EvidenceStore, ReplayCoordinator, SnapshotStore
from config import GRAPH_SCHEMA_VERSION

LIBRARY_DIR = "library"
os.makedirs(LIBRARY_DIR, exist_ok=True)

key_manager = GeminiKeyManager()
session_manager = SessionManager(os.path.join(LIBRARY_DIR, "session_state.json"))

app = FastAPI(title="BookBuddy API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def read_root(): 
    return {"status": "online"}

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
            book_path = os.path.join(LIBRARY_DIR, book)
            if os.path.isdir(book_path):
                book_sessions = [
                    s for s in os.listdir(book_path)
                    if os.path.isdir(os.path.join(book_path, s))
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
        book_path = os.path.join(LIBRARY_DIR, book)
        if not os.path.isdir(book_path):
            continue
        for session in os.listdir(book_path):
            session_path = os.path.join(book_path, session)
            if os.path.isdir(session_path):
                sessions.append({
                    "session_key": _session_key(book, session),
                    "book_name": book,
                    "session_name": session,
                    "session_dir": session_path,
                })
    return sessions

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
    return {"sessions": metadata_sessions}

@app.get("/session/{book_name}/{session_name}/integrity")
def check_session_integrity(book_name: str, session_name: str):
    session_key = _session_key(book_name, session_name)
    metadata = session_manager.get_session_metadata(session_key)
    if not metadata:
        session_dir = os.path.join(LIBRARY_DIR, book_name, session_name)
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
    book_dir = os.path.join(LIBRARY_DIR, book_name)
    session_dir = os.path.join(book_dir, session_name)
    
    if not os.path.exists(session_dir):
        raise HTTPException(status_code=404, detail="Session not found in library.")
    
    epub_files = [f for f in os.listdir(book_dir) if f.endswith('.epub')]
    if not epub_files:
        raise HTTPException(status_code=404, detail="EPUB file missing from book directory.")
        
    try:
        parsed_book = parse_epub(os.path.join(book_dir, epub_files[0]))
        session_key = f"{book_name}::{session_name}"
        
        session_manager.set_book(session_key, parsed_book, session_dir=session_dir)
        continuity_path = os.path.join(session_dir, "continuity.json")
        if not os.path.exists(continuity_path):
            write_continuity_metadata(session_dir, book_name, session_type="resumed")
            
        return {
            "message": f"Mounted {session_name} into memory.",
            "total_chapters": parsed_book.total_chapters,
            "session_type": "resumed",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/series-matches")
def get_series_matches(title: str, author: str = ""):
    return {"matches": find_series_matches(LIBRARY_DIR, title, author)}

@app.post("/upload")
async def upload_epub(
    file: UploadFile = File(...),
    session_name: str = Form("Default_Session"),
    series_parent_book: str | None = Form(None),
    series_parent_session: str | None = Form(None),
):
    if not file.filename.lower().endswith('.epub'): 
        raise HTTPException(status_code=400, detail="Invalid extension.")
        
    temp_path = os.path.join(LIBRARY_DIR, f"temp_{file.filename}")
    with open(temp_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
        
    try:
        parsed_book = parse_epub(temp_path)
        safe_title = sanitize_session_component(parsed_book.title, fallback="Book")
        safe_session = sanitize_session_component(session_name, fallback="Default_Session")
        
        book_dir = os.path.join(LIBRARY_DIR, safe_title)
        session_dir = os.path.join(book_dir, safe_session)
        db_dir = os.path.join(session_dir, "database")
        
        os.makedirs(db_dir, exist_ok=True)
        inherited_graph = False
        if series_parent_book:
            parent_session = series_parent_session or latest_session_for_book(LIBRARY_DIR, series_parent_book)
            if not parent_session:
                raise HTTPException(status_code=404, detail="Series parent session not found.")
            inherited_graph = inherit_series_graph(
                LIBRARY_DIR,
                series_parent_book,
                parent_session,
                session_dir,
                target_book=safe_title,
                target_session=safe_session,
            )
            series_parent_session = parent_session
        
        final_epub_path = os.path.join(book_dir, file.filename)
        if not os.path.exists(final_epub_path):
            shutil.move(temp_path, final_epub_path)
        else:
            os.remove(temp_path) 

        session_key = f"{safe_title}::{safe_session}"
        session_manager.update_session_metadata(
            session_key,
            book_name=safe_title,
            session_name=safe_session,
            label=session_name.strip() or safe_session,
            internal_session_id=session_key,
            session_name_quality="sanitized",
        )
        session_manager.set_book(session_key, parsed_book, session_dir=session_dir)
        write_continuity_metadata(
            session_dir,
            safe_title,
            series_parent_book,
            series_parent_session,
            inherited_graph,
            "inherited-series" if inherited_graph else "standalone",
        )
        series_matches = find_series_matches(
            LIBRARY_DIR,
            parsed_book.title,
            parsed_book.author,
            exclude_book_name=safe_title,
        )
        
        return {
            "book_name": safe_title,
            "session_name": safe_session,
            "total_chapters": parsed_book.total_chapters,
            "series_matches": series_matches,
            "inherited_graph": inherited_graph,
        }
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/book/{book_name}/{session_name}")
def get_book_metadata(book_name: str, session_name: str):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    
    if not book: raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    return {"title": book.title, "table_of_contents": [{"index": ch.index, "title": ch.title} for ch in book.chapters]}

@app.get("/chapter/{book_name}/{session_name}/{chapter_index}")
def get_chapter_data(book_name: str, session_name: str, chapter_index: int):
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    chapter_file = os.path.join(db_dir, f"chapter_{chapter_index}.json")
    graph_path = os.path.join(db_dir, "graph.db")

    if os.path.exists(graph_path):
        db = BookDatabase(db_dir)
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

@app.get("/export-graph/{book_name}/{session_name}")
def export_graph(book_name: str, session_name: str):
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = BookDatabase(db_dir)
    try:
        return db.export_graph_state()
    finally:
        db.close()


@app.get("/chapter-snapshot/{book_name}/{session_name}/{chapter_index}")
def get_chapter_snapshot(book_name: str, session_name: str, chapter_index: int, revision: int | None = None):
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = BookDatabase(db_dir)
    try:
        snapshot = SnapshotStore.get(db, chapter_index, revision)
    finally:
        db.close()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Reader snapshot not available for this chapter.")
    return snapshot


@app.get("/chapter-snapshot/{book_name}/{session_name}/{chapter_index}/history")
def get_chapter_snapshot_history(book_name: str, session_name: str, chapter_index: int):
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = BookDatabase(db_dir)
    try:
        history = SnapshotStore.history(db, chapter_index)
    finally:
        db.close()
    if not history:
        raise HTTPException(status_code=404, detail="Reader snapshot history not available for this chapter.")
    return {"chapter": chapter_index, "history": history}


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
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        raise HTTPException(status_code=404, detail="Graph database not found.")
    db = BookDatabase(db_dir)
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
    use_gemini_vision: bool = False,
):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    
    # Check the database/cache directly to find where to resume
    start_chapter = 0
    for i in range(target_chapter + 1):
        if not os.path.exists(os.path.join(db_dir, f"chapter_{i}.json")):
            start_chapter = i
            break
    else:
        start_chapter = target_chapter + 1
        
    total_to_process = (target_chapter - start_chapter) + 1

    session_manager.set_task(session_key, {
        "status": "processing",
        "target_chapter": target_chapter,
        "current_chapter": start_chapter,
        "progress": 0.0 if total_to_process > 0 else 100.0,
        "cancel_requested": False,
        "gemini_vision_fallback_authorized": bool(use_gemini_vision),
        "log": f"Resuming from Chapter {start_chapter}..." if start_chapter > 0 and total_to_process > 0 else ("Booting analysis..." if total_to_process > 0 else "Already up to date.")
    })

    db = None
    async with session_manager.get_lock(session_key):
        try:
            if total_to_process > 0:
                db = BookDatabase(db_dir)
                previous_events_cache = {}
                for i in range(start_chapter, target_chapter + 1):
                    if session_manager.cancel_requested(session_key):
                        session_manager.update_task(
                            session_key,
                            status="cancelled",
                            progress=round(((i - start_chapter) / total_to_process) * 100, 1),
                            log="Analysis cancelled between chapters."
                        )
                        return

                    session_manager.update_task(
                        session_key,
                        current_chapter=i,
                        progress=round(((i - start_chapter) / total_to_process) * 100, 1),
                        log=f"Processing Chapter {i}..."
                    )
                    
                    # Extraction appends immutable evidence. Derived graph work is replayed
                    # in staging below, after every requested chapter is available.
                    await asyncio.to_thread(
                        process_single_chapter,
                        key_manager,
                        i,
                        book,
                        db_dir,
                        db,
                        previous_events_cache,
                        False,
                        False,
                        "new_chapter",
                        use_gemini_vision,
                    )
                    session_manager.update_task(
                        session_key,
                        last_analyzed_chapter=i,
                    )

            if db is not None:
                db.close()
                db = None
            session_manager.update_task(session_key, log="Replaying immutable chapter evidence...")
            replay_result = await asyncio.to_thread(ReplayCoordinator(db_dir).replay, "new_chapter")
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
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    async with session_manager.get_lock(session_key):
        try:
            session_manager.set_task(session_key, {
                "status": "processing",
                "progress": 0.0,
                "log": "Replaying immutable chapter evidence...",
                "cancel_requested": False,
            })
            result = await asyncio.to_thread(ReplayCoordinator(db_dir).run, mode=mode, reason=reason)
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


async def background_reextract_task(
    book_name: str,
    session_name: str,
    chapter_index: int,
    reason: str = "explicit_reextract",
    use_gemini_vision: bool = False,
):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    if not book:
        session_manager.update_task(session_key, status="error", log="Session is not loaded.")
        return
    async with session_manager.get_lock(session_key):
        db = BookDatabase(db_dir)
        try:
            session_manager.set_task(session_key, {
                "status": "processing",
                "target_chapter": chapter_index,
                "current_chapter": chapter_index,
                "progress": 0.0,
                "log": f"Re-extracting Chapter {chapter_index}...",
                "cancel_requested": False,
            })
            await asyncio.to_thread(
                process_single_chapter,
                key_manager,
                chapter_index,
                book,
                db_dir,
                db,
                {},
                False,
                True,
                reason,
                use_gemini_vision,
            )
        except Exception as exc:
            session_manager.update_task(session_key, status="error", log=f"Re-extraction crash: {exc}")
            return
        finally:
            db.close()
        try:
            session_manager.update_task(session_key, log="Replaying revised chapter evidence...")
            result = await asyncio.to_thread(ReplayCoordinator(db_dir).replay, reason)
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

@app.post("/analyze/{book_name}/{session_name}/{chapter_index}", status_code=202)
async def trigger_analysis(
    book_name: str,
    session_name: str,
    chapter_index: int,
    background_tasks: BackgroundTasks,
    use_gemini_vision: bool = Query(
        default=False,
        description=(
            "Authorize conditional Gemini Vision fallback after local image tools are insufficient. "
            "This consumes only GEMINI_VISION_API_KEY* quota."
        ),
    ),
):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    
    if not book: 
        raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    if chapter_index < 0 or chapter_index >= book.total_chapters: 
        raise HTTPException(status_code=404, detail="Chapter out of bounds.")
    
    task_state = session_manager.get_task(session_key)
    if task_state.get("status") == "processing":
        return {"message": "Analysis is already actively running.", "session_key": session_key}

    background_tasks.add_task(background_analysis_task, book_name, session_name, chapter_index, use_gemini_vision)
    return {
        "message": "Analysis queued and initiated.",
        "session_key": session_key,
        "gemini_vision_fallback_authorized": bool(use_gemini_vision),
    }


@app.post("/rebuild/{book_name}/{session_name}", status_code=202)
async def trigger_rebuild(
    book_name: str,
    session_name: str,
    background_tasks: BackgroundTasks,
    reason: str = "manual_rebuild",
    mode: str = "normal",
):
    db_dir = os.path.join(LIBRARY_DIR, book_name, session_name, "database")
    if not os.path.isdir(db_dir):
        raise HTTPException(status_code=404, detail="Session database not found.")
    session_key = f"{book_name}::{session_name}"
    if session_manager.get_task(session_key).get("status") == "processing":
        raise HTTPException(status_code=409, detail="Analysis is already actively running.")
    if not str(reason or "").strip():
        raise HTTPException(status_code=400, detail="Rebuild reason must not be empty.")
    if mode not in {"normal", "full", "verify"}:
        raise HTTPException(status_code=400, detail="Replay mode must be normal, full, or verify.")
    background_tasks.add_task(background_rebuild_task, book_name, session_name, reason, mode)
    return {"message": "Graph replay queued.", "session_key": session_key, "mode": mode}


@app.post("/reanalyze/{book_name}/{session_name}/{chapter_index}", status_code=202)
async def trigger_reanalysis(
    book_name: str,
    session_name: str,
    chapter_index: int,
    background_tasks: BackgroundTasks,
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
    book: ParsedBook = session_manager.get_book(session_key)
    if not book:
        raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    if chapter_index < 0 or chapter_index >= book.total_chapters:
        raise HTTPException(status_code=404, detail="Chapter out of bounds.")
    if session_manager.get_task(session_key).get("status") == "processing":
        raise HTTPException(status_code=409, detail="Analysis is already actively running.")
    if not str(reason or "").strip():
        raise HTTPException(status_code=400, detail="Re-extraction reason must not be empty.")
    background_tasks.add_task(
        background_reextract_task,
        book_name,
        session_name,
        chapter_index,
        reason,
        use_gemini_vision,
    )
    return {
        "message": "Chapter re-extraction queued.",
        "session_key": session_key,
        "gemini_vision_fallback_authorized": bool(use_gemini_vision),
    }

@app.post("/cancel/{book_name}/{session_name}", status_code=202)
async def cancel_analysis(book_name: str, session_name: str):
    session_key = f"{book_name}::{session_name}"
    if not session_manager.request_cancel(session_key):
        raise HTTPException(status_code=409, detail="No active analysis is running for this session.")
    return {"message": "Cancellation requested.", "session_key": session_key}

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
