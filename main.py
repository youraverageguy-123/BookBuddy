from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
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
from key_manager import GeminiKeyManager
from session_manager import SessionManager

LIBRARY_DIR = "library"
os.makedirs(LIBRARY_DIR, exist_ok=True)

key_manager = GeminiKeyManager()
session_manager = SessionManager()

app = FastAPI(title="BookBuddy API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def read_root(): 
    return {"status": "online"}

@app.get("/library")
def list_library():
    """Returns a nested hierarchy: { "Book_Name": ["Session_1", "Session_2"] }"""
    library_tree = {}
    if os.path.exists(LIBRARY_DIR):
        for book in os.listdir(LIBRARY_DIR):
            book_path = os.path.join(LIBRARY_DIR, book)
            if os.path.isdir(book_path):
                book_sessions = [s for s in os.listdir(book_path) if os.path.isdir(os.path.join(book_path, s))]
                library_tree[book] = book_sessions
    return {"library": library_tree}

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
        
        session_manager.set_book(session_key, parsed_book)
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
        safe_title = re.sub(r'[\\/*?:"<>|]', "", parsed_book.title).strip().replace(" ", "_")
        safe_session = re.sub(r'[\\/*?:"<>|]', "", session_name).strip().replace(" ", "_")
        
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
            )
            series_parent_session = parent_session
        
        final_epub_path = os.path.join(book_dir, file.filename)
        if not os.path.exists(final_epub_path):
            shutil.move(temp_path, final_epub_path)
        else:
            os.remove(temp_path) 

        session_key = f"{safe_title}::{safe_session}"
        session_manager.set_book(session_key, parsed_book)
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
    
    if os.path.exists(chapter_file):
        with open(chapter_file, "r") as f:
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

# ─── BACKGROUND QUEUE ENGINE ───

async def background_analysis_task(book_name: str, session_name: str, target_chapter: int):
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
                    
                    # Triggers the exact same bulletproof extraction loop as the CLI
                    await asyncio.to_thread(process_single_chapter, key_manager, i, book, db_dir, db, previous_events_cache)
            
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

@app.post("/analyze/{book_name}/{session_name}/{chapter_index}", status_code=202)
async def trigger_analysis(book_name: str, session_name: str, chapter_index: int, background_tasks: BackgroundTasks):
    session_key = f"{book_name}::{session_name}"
    book: ParsedBook = session_manager.get_book(session_key)
    
    if not book: 
        raise HTTPException(status_code=404, detail="Session not loaded. Call /load first.")
    if chapter_index < 0 or chapter_index >= book.total_chapters: 
        raise HTTPException(status_code=404, detail="Chapter out of bounds.")
    
    task_state = session_manager.get_task(session_key)
    if task_state.get("status") == "processing":
        return {"message": "Analysis is already actively running.", "session_key": session_key}

    background_tasks.add_task(background_analysis_task, book_name, session_name, chapter_index)
    return {"message": "Analysis queued and initiated.", "session_key": session_key}

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
