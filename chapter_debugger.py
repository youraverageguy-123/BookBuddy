from datetime import datetime
from pathlib import Path

from google.genai import types

from config import GEMINI_MODEL_NAME, PROMPT_VERSION
from epub_parser import parse_epub
from key_manager import GeminiKeyManager


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


def choose_epub() -> Path:
    library = Path("library")

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
    epub_path = choose_epub()
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

    debug_dir = Path("logs") / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = write_debug_file(debug_dir, chapter_idx, "prompt", prompt)

    key_manager = GeminiKeyManager()
    client, key_id = key_manager.get_available_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                safety_settings=[
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.OFF),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.OFF),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.OFF),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.OFF),
                ],
            ),
        )
        response_text = response.text or ""
        response_path = write_debug_file(debug_dir, chapter_idx, "response", response_text)
        print("\nSUCCESS")
        print(f"Key: {key_id}")
        print(f"Prompt: {prompt_path}")
        print(f"Response: {response_path}")
        print(response_text[:2000])
    except Exception as exc:
        error_text = (
            f"prompt_version: {PROMPT_VERSION}\n"
            f"model_name: {GEMINI_MODEL_NAME}\n"
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


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        print("\nExiting debugger.")
    except KeyboardInterrupt:
        print("\nStopping safely.")
