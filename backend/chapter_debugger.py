from datetime import datetime
from pathlib import Path

from config import PROMPT_VERSION
from epub_parser import parse_epub


def prompt_choice(prompt: str, allow_back: bool = False) -> str:
    while True:
        value = input(prompt).strip()
        lowered = value.lower()
        if lowered == "q":
            raise SystemExit
        if allow_back and lowered == "b":
            return "b"
        if value:
            return value
        print("Enter a value, b, or q.")


def choose_epub(library: Path) -> Path:

    while True:
        books = []
        if library.exists():
            for book_folder in library.iterdir():
                if book_folder.is_dir():
                    books.extend(book_folder.glob("*.epub"))

        print("\n=== Isolated Chapter Debugger ===")
        for idx, book in enumerate(books, start=1):
            print(f"[{idx}] {book}")
        print("[n] New EPUB path")
        print("[q] Quit")

        choice = prompt_choice("Selection: ").lower()
        if choice == "n":
            epub_path = Path(input("EPUB path: ").strip(' "\''))
            if epub_path.exists():
                return epub_path
            print("File not found. Try again.")
            continue

        if choice.isdigit() and 1 <= int(choice) <= len(books):
            return books[int(choice) - 1]

        print("Invalid selection. Try again.")


def choose_chapter(total_chapters: int) -> int:
    while True:
        value = prompt_choice(f"Chapter index 0 to {total_chapters - 1} ([q] quit): ")
        if value.isdigit():
            chapter_idx = int(value)
            if 0 <= chapter_idx < total_chapters:
                return chapter_idx
        print("Invalid chapter. Try again.")


def write_debug_file(debug_dir: Path, chapter_idx: int, suffix: str, content: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = debug_dir / f"chapter_{chapter_idx}_{timestamp}_{suffix}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def main():
    from ai import GenerationRequest
    from bootstrap import create_ai_manager
    from config import load_config

    config = load_config()
    epub_path = choose_epub(config.paths.library_dir)
    book = parse_epub(str(epub_path))

    print(f"\nBook: {book.title}")
    print(f"Chapters: {book.total_chapters}")

    chapter_idx = choose_chapter(book.total_chapters)
    chapter = book.chapters[chapter_idx]

    prompt = f"""You are running BookBuddy isolated debug extraction.
No graph state is available.
Do not use prior chapter context.
Return ONLY valid JSON.

Extract:
1. pov_character_found
2. entities_present
3. relationships with source, target, trust_score, relationship_evidence from this chapter only
4. major_events

CHAPTER TEXT:
{chapter.content}
"""

    debug_dir = config.paths.log_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = write_debug_file(debug_dir, chapter_idx, "prompt", prompt)

    ai_manager = create_ai_manager(config)
    key_id = ""
    try:
        result = ai_manager.generate(GenerationRequest(
            role="chapter_analysis",
            prompt=prompt,
            temperature=0.0,
            safety_profile="unrestricted",
        ))
        key_id = result.credential_id
        response_text = result.text or ""
        response_path = write_debug_file(debug_dir, chapter_idx, "response", response_text)
        print("\nSUCCESS")
        print(f"Key: {key_id}")
        print(f"Prompt: {prompt_path}")
        print(f"Response: {response_path}")
        print(response_text[:2000])
    except Exception as exc:
        error_text = (
            f"prompt_version: {PROMPT_VERSION}\n"
            f"model_name: {config.ai.chapter_model}\n"
            f"key_id: {key_id}\n"
            f"chapter_index: {chapter_idx}\n"
            f"chapter_title: {chapter.title}\n"
            f"type: {type(exc).__name__}\n"
            f"error: {exc}\n"
        )
        error_path = write_debug_file(debug_dir, chapter_idx, "error", error_text)
        print("\nFAILED")
        print(error_text)
        print(f"Error log: {error_path}")
    finally:
        ai_manager.close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        print("\nExiting debugger.")
    except KeyboardInterrupt:
        print("\nStopping safely.")
