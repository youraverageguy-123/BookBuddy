import os
import json
import time
from db_manager import BookDatabase
from analysis_engine import ingest_ai_payload

def extract_logic_only(chapter_index: int, db_dir: str, db: BookDatabase):
    chapter_file = os.path.join(db_dir, f"chapter_{chapter_index}.json")
    if not os.path.exists(chapter_file):
        return False
        
    with open(chapter_file, "r", encoding="utf-8") as f:
        ai_data = json.load(f)

    if "System skipped" in str(ai_data.get("major_events", [])):
        return True

    ingest_ai_payload(ai_data, chapter_index, db)
    return True

if __name__ == "__main__":
    print("\n=== BookBuddy Fast Graph Rebuilder ===")
    
    # Step 1: Select Book
    books = sorted([d for d in os.listdir("library") if os.path.isdir(os.path.join("library", d))])
    
    if not books:
        print("❌ No books found in library.")
        exit(1)
        
    print("\n📚 Available Books:")
    for idx, book_folder in enumerate(books):
        print(f"[{idx}] {book_folder}")
        
    try:
        book_selection = input("\nSelect book index: ")
        target_book = books[int(book_selection)]
        book_dir = os.path.join("library", target_book)
        
        # Step 2: Select Session
        sessions = sorted([d for d in os.listdir(book_dir) if os.path.isdir(os.path.join(book_dir, d))])
        
        if not sessions:
            print(f"❌ No sessions found for {target_book}.")
            exit(1)
            
        print(f"\n📂 Available Sessions for {target_book}:")
        for idx, session_folder in enumerate(sessions):
            print(f"[{idx}] {session_folder}")
            
        session_selection = input("\nSelect session index to rebuild: ")
        target_session = sessions[int(session_selection)]
        db_dir = os.path.join(book_dir, target_session, "database")
        
        # Execution
        graph_path = os.path.join(db_dir, "graph.db")
        if os.path.exists(graph_path):
            os.remove(graph_path)
            print("🗑️  Deleted old graph.db")
            
        print(f"⚙️  Rebuilding graph dynamically from {target_session} JSON cache...")
        start_time = time.time()
        db = BookDatabase(db_dir)
        
        idx = 0
        while True:
            try:
                success = extract_logic_only(idx, db_dir, db)
            except Exception:
                print(f"\nCRASHED ON CHAPTER {idx}")
                raise
            if not success: break
            idx += 1
            
        print(f"✅ Successfully rebuilt graph with {idx} chapters in {time.time() - start_time:.2f} seconds!")
        
    except Exception as e:
        print(f"❌ Error during rebuild: {e}")
