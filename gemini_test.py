import json
import os
import re
import shutil

from analysis_engine import process_single_chapter
from continuity_manager import find_series_matches, inherit_series_graph, latest_session_for_book, write_continuity_metadata
from db_manager import BookDatabase
from epub_parser import parse_epub
from key_manager import GeminiKeyManager


LIBRARY_DIR = "library"


def safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", value).strip().replace(" ", "_")
    return cleaned or fallback


def prompt_choice(prompt: str, valid: set[str] | None = None, allow_back: bool = False) -> str:
    while True:
        value = input(prompt).strip()
        lowered = value.lower()
        if lowered == "q":
            raise SystemExit
        if allow_back and lowered == "b":
            return "b"
        if valid is None or lowered in valid:
            return value
        print("Invalid selection. Try again.")


def choose_book():
    os.makedirs(LIBRARY_DIR, exist_ok=True)

    while True:
        books = sorted([
            d for d in os.listdir(LIBRARY_DIR)
            if os.path.isdir(os.path.join(LIBRARY_DIR, d))
        ])

        print("\n=== Select Book ===")
        print("[0] Upload a new EPUB")
        for idx, book_name in enumerate(books, 1):
            print(f"[{idx}] {book_name}")
        print("[q] Quit")

        choice = prompt_choice("Selection: ")
        if not choice.isdigit():
            print("Enter a number or q.")
            continue

        choice_idx = int(choice)
        if choice_idx == 0:
            epub_path = input("EPUB path: ").strip(' "\'')
            if not os.path.exists(epub_path):
                print("File not found. Try again.")
                continue

            parsed_book = parse_epub(epub_path)
            book_name = safe_name(parsed_book.title, "Untitled_Book")
            book_dir = os.path.join(LIBRARY_DIR, book_name)
            os.makedirs(book_dir, exist_ok=True)

            dest_epub_path = os.path.join(book_dir, os.path.basename(epub_path))
            if not os.path.exists(dest_epub_path):
                shutil.copy(epub_path, dest_epub_path)

            return parsed_book, book_name, book_dir

        if 1 <= choice_idx <= len(books):
            book_name = books[choice_idx - 1]
            book_dir = os.path.join(LIBRARY_DIR, book_name)
            epub_files = [f for f in os.listdir(book_dir) if f.lower().endswith(".epub")]
            if not epub_files:
                print("No EPUB found for that book.")
                continue
            parsed_book = parse_epub(os.path.join(book_dir, epub_files[0]))
            return parsed_book, book_name, book_dir

        print("Invalid selection. Try again.")


def choose_session(book, book_name: str, book_dir: str):
    while True:
        existing_sessions = sorted([
            d for d in os.listdir(book_dir)
            if os.path.isdir(os.path.join(book_dir, d))
        ])

        print("\n=== Select Session ===")
        for idx, session in enumerate(existing_sessions):
            print(f"[{idx}] {session}")
        print(f"[{len(existing_sessions)}] Create new session")
        print("[b] Back")
        print("[q] Quit")

        choice = prompt_choice("Selection: ", allow_back=True)
        if choice == "b":
            return None
        if not choice.isdigit():
            print("Enter a number, b, or q.")
            continue

        choice_idx = int(choice)
        if choice_idx < len(existing_sessions):
            session_name = existing_sessions[choice_idx]
            session_dir = os.path.join(book_dir, session_name)
            continuity_path = os.path.join(session_dir, "continuity.json")
            if not os.path.exists(continuity_path):
                write_continuity_metadata(session_dir, book_name, session_type="resumed")
        elif choice_idx == len(existing_sessions):
            session_name = safe_name(input("New session name: "), "Default_Session")
            session_dir = os.path.join(book_dir, session_name)
            os.makedirs(os.path.join(session_dir, "database"), exist_ok=True)
            maybe_link_series(book, book_name, session_dir)
        else:
            print("Invalid selection. Try again.")
            continue

        session_dir = os.path.join(book_dir, session_name)
        os.makedirs(os.path.join(session_dir, "database"), exist_ok=True)
        return session_name, session_dir


def maybe_link_series(book, book_name: str, session_dir: str):
    matches = find_series_matches(LIBRARY_DIR, book.title, book.author, exclude_book_name=book_name)
    if not matches:
        write_continuity_metadata(session_dir, book_name)
        return

    print("\nPossible series matches:")
    for idx, match in enumerate(matches, 1):
        print(f"[{idx}] {match['book_name']} ({', '.join(match['sessions'])})")
    print("[0] Continue standalone")

    choice = prompt_choice("Parent book selection: ")
    if not choice.isdigit() or int(choice) == 0:
        write_continuity_metadata(session_dir, book_name)
        return

    choice_idx = int(choice)
    if not 1 <= choice_idx <= len(matches):
        print("Invalid parent selection; continuing standalone.")
        write_continuity_metadata(session_dir, book_name)
        return

    parent_book = matches[choice_idx - 1]["book_name"]
    parent_session = latest_session_for_book(LIBRARY_DIR, parent_book)
    inherited = False
    if parent_session:
        inherited = inherit_series_graph(LIBRARY_DIR, parent_book, parent_session, session_dir)
    write_continuity_metadata(session_dir, book_name, parent_book, parent_session, inherited)


def print_summary(chapter_idx: int, data: dict, chapter_file: str):
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Chapter: {chapter_idx}")
    print(f"POV: {data.get('pov_character_found', '')}")
    print(f"Entities: {len(data.get('entities_present', []))}")
    print(f"Relationships: {len(data.get('relationships', []))}")
    print(f"Aliases: {len(data.get('new_aliases_discovered', []))}")
    print(f"Group aliases: {len(data.get('new_group_aliases_discovered', []))}")
    print(f"Major events: {len(data.get('major_events', []))}")
    print(f"Output saved: {chapter_file}")


def run_chapter_loop(key_manager, book, db_dir: str):
    db = BookDatabase(db_dir)
    previous_events_cache = {}
    try:
        while True:
            print("\n=== Select Chapter ===")
            print(f"Enter chapter index 0 to {book.total_chapters - 1}")
            print("[b] Back")
            print("[q] Quit")
            chapter_input = prompt_choice("Chapter: ", allow_back=True)
            if chapter_input == "b":
                return
            if not chapter_input.isdigit():
                print("Enter a chapter number, b, or q.")
                continue

            chapter_idx = int(chapter_input)
            if chapter_idx < 0 or chapter_idx >= book.total_chapters:
                print(f"Chapter must be between 0 and {book.total_chapters - 1}.")
                continue

            while True:
                chapter_file = os.path.join(db_dir, f"chapter_{chapter_idx}.json")
                try:
                    for i in range(chapter_idx):
                        if not os.path.exists(os.path.join(db_dir, f"chapter_{i}.json")):
                            process_single_chapter(key_manager, i, book, db_dir, db, previous_events_cache)

                    data = process_single_chapter(key_manager, chapter_idx, book, db_dir, db, previous_events_cache)
                    print_summary(chapter_idx, data, chapter_file)
                    next_action = prompt_choice("\n[r] Reanalyze cached result [c] Change chapter [b] Back [q] Quit: ", {"r", "c", "b", "q"})
                    if next_action.lower() == "r":
                        print("Immutable cache is enabled; delete the chapter cache manually before re-extraction.")
                        continue
                    if next_action.lower() == "c":
                        break
                    if next_action.lower() == "b":
                        return
                except Exception as exc:
                    print("\n" + "=" * 60)
                    print("ANALYSIS FAILED")
                    print("=" * 60)
                    print(f"Chapter: {chapter_idx}")
                    print(f"Type: {type(exc).__name__}")
                    print(f"Reason: {exc}")
                    next_action = prompt_choice("\n[r] Retry [c] Change chapter [b] Back [q] Quit: ", {"r", "c", "b", "q"})
                    if next_action.lower() == "r":
                        continue
                    if next_action.lower() == "c":
                        break
                    if next_action.lower() == "b":
                        return
    finally:
        db.close()


def main():
    key_manager = GeminiKeyManager()
    print("\n=== BookBuddy AI Tester ===")

    while True:
        book, book_name, book_dir = choose_book()
        while True:
            selected = choose_session(book, book_name, book_dir)
            if selected is None:
                break
            session_name, session_dir = selected
            db_dir = os.path.join(session_dir, "database")
            print(f"\nActive database: {db_dir}")
            run_chapter_loop(key_manager, book, db_dir)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        print("\nExiting BookBuddy Tester.")
    except KeyboardInterrupt:
        print("\nStopping safely.")
