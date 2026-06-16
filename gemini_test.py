import os
import json
import re
import shutil
from epub_parser import parse_epub
from analysis_engine import process_single_chapter
from db_manager import BookDatabase
from key_manager import GeminiKeyManager

# ─── Setup ────────────────────────────────────────────────
key_manager = GeminiKeyManager()

LIBRARY_DIR = "library"
os.makedirs(LIBRARY_DIR, exist_ok=True)

print("\n=== BookBuddy AI Tester ===")

# ─── Book Discovery ───────────────────────────────────────
books = sorted([d for d in os.listdir(LIBRARY_DIR) if os.path.isdir(os.path.join(LIBRARY_DIR, d))])
book = None
book_dir = ""

if books:
    print("\n📚 Available Books in Library:")
    print("  [0] Upload a NEW EPUB file")
    for idx, b in enumerate(books, 1):
        print(f"  [{idx}] {b}")
    
    choice = input("\nSelect option: ")
    try:
        choice_idx = int(choice)
        if choice_idx == 0:
            epub_path = input("Enter path to EPUB file (without quotes): ").strip(' "\'')
            if not os.path.exists(epub_path):
                print(f"❌ Error: File not found at {epub_path}")
                exit(1)
            book = parse_epub(epub_path)
            safe_title = re.sub(r'[\\/*?:"<>|]', "", book.title).strip().replace(" ", "_")
            book_dir = os.path.join(LIBRARY_DIR, safe_title)
            os.makedirs(book_dir, exist_ok=True)
            
            dest_epub_path = os.path.join(book_dir, os.path.basename(epub_path))
            if not os.path.exists(dest_epub_path): 
                shutil.copy(epub_path, dest_epub_path)
        elif 1 <= choice_idx <= len(books):
            book_name = books[choice_idx - 1]
            book_dir = os.path.join(LIBRARY_DIR, book_name)
            epub_files = [f for f in os.listdir(book_dir) if f.endswith('.epub')]
            if not epub_files:
                print(f"❌ Error: No EPUB found in {book_dir}")
                exit(1)
            epub_path = os.path.join(book_dir, epub_files[0])
            book = parse_epub(epub_path)
        else:
            print("❌ Invalid choice.")
            exit(1)
    except ValueError:
        print("❌ Invalid input.")
        exit(1)
else:
    epub_path = input("Enter path to EPUB file (without quotes): ").strip(' "\'')
    if not os.path.exists(epub_path):
        print(f"❌ Error: File not found at {epub_path}")
        exit(1)
    book = parse_epub(epub_path)
    safe_title = re.sub(r'[\\/*?:"<>|]', "", book.title).strip().replace(" ", "_")
    book_dir = os.path.join(LIBRARY_DIR, safe_title)
    os.makedirs(book_dir, exist_ok=True)
    
    dest_epub_path = os.path.join(book_dir, os.path.basename(epub_path))
    if not os.path.exists(dest_epub_path): 
        shutil.copy(epub_path, dest_epub_path)

print(f"✅ Success! Loaded '{book.title}' ({book.total_chapters} chapters).")

# ─── Session Discovery ────────────────────────────────────
existing_sessions = sorted([d for d in os.listdir(book_dir) if os.path.isdir(os.path.join(book_dir, d))])

if existing_sessions:
    print(f"\n📂 Found existing sessions for {book.title}:")
    for idx, d in enumerate(existing_sessions):
        print(f"  [{idx}] {d}")
    print(f"  [{len(existing_sessions)}] Create NEW session")
    
    choice = input("\nSelect option: ")
    try:
        choice_idx = int(choice)
        if choice_idx < len(existing_sessions):
            session_name = existing_sessions[choice_idx]
        else:
            session_name = input("\nEnter a custom name for this new session: ").strip()
    except ValueError:
        print("Invalid choice. Creating new session.")
        session_name = input("\nEnter a custom name for this new session: ").strip()
else:
    session_name = input("\nEnter a custom name for your first session: ").strip()

safe_session_name = re.sub(r'[\\/*?:"<>|]', "", session_name).strip().replace(" ", "_")
if not safe_session_name: 
    safe_session_name = "Default_Session"

SESSION_DIR = os.path.join(book_dir, safe_session_name)
DB_DIR = os.path.join(SESSION_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)
db = BookDatabase(DB_DIR)
previous_events_cache = {}

print(f"\n📁 Active Database: {DB_DIR}")

# ─── Execution Engine ─────────────────────────────────
while True:
    chapter_input = input(f"\nWhich chapter index do you want to analyze? (0 to {book.total_chapters - 1}) or 'q' to quit: ")
    if chapter_input.lower() == 'q': break
    try:
        target_idx = int(chapter_input)
        
        if target_idx < 0 or target_idx >= book.total_chapters:
            print(f"❌ Chapter must be between 0 and {book.total_chapters - 1}")
            continue
            
        print(f"\n🧠 Preparing analysis for Chapter {target_idx}...")
        
        for i in range(target_idx):
            if not os.path.exists(os.path.join(DB_DIR, f"chapter_{i}.json")): 
                process_single_chapter(key_manager, i, book, DB_DIR, db, previous_events_cache)
                
        final_data = process_single_chapter(key_manager, target_idx, book, DB_DIR, db, previous_events_cache)
        
        print(f"\n✅ Chapter {target_idx} Complete!")
        print(json.dumps(final_data, indent=2))
        
    except ValueError:
        print("❌ Please enter a valid chapter number.")
    except Exception as e: 
        print(f"\n❌ Error: {e}")
