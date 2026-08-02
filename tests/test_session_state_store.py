from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile

from session_manager import SessionManager


def test_concurrent_session_metadata_updates_merge_without_temp_collisions():
    with tempfile.TemporaryDirectory() as root:
        state_path = Path(root, "session_state.json")
        managers = [SessionManager(str(state_path)) for _ in range(4)]

        def update(index: int) -> None:
            managers[index % len(managers)].update_session_metadata(
                f"Book::{index}",
                book_name="Book",
                session_name=str(index),
                metadata_revision=1,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(update, range(32)))

        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert set(payload["sessions"]) == {f"Book::{index}" for index in range(32)}
        assert not list(Path(root).glob(".*.tmp"))


def test_corrupt_session_state_fails_closed_before_mutation():
    with tempfile.TemporaryDirectory() as root:
        state_path = Path(root, "session_state.json")
        state_path.write_text("{not-json", encoding="utf-8")
        try:
            SessionManager(str(state_path))
        except RuntimeError as exc:
            assert "unreadable" in str(exc)
        else:
            raise AssertionError("corrupt session state must not be silently replaced")


def test_hard_delete_recomputes_target_instead_of_trusting_persisted_path():
    with tempfile.TemporaryDirectory() as root:
        library = Path(root, "library")
        expected = library / "Book" / "Reading"
        expected.mkdir(parents=True)
        (expected / "owned.txt").write_text("owned", encoding="utf-8")
        outside = Path(root, "outside")
        outside.mkdir()
        marker = outside / "preserve.txt"
        marker.write_text("preserve", encoding="utf-8")

        manager = SessionManager(str(library / "session_state.json"))
        manager.update_session_metadata(
            "Book::Reading",
            book_name="Book",
            session_name="Reading",
            session_dir=str(outside),
        )
        result = manager.hard_delete_session("Book::Reading", str(library), dry_run=False)

        deleted_target = Path(result["session_dir"])
        assert deleted_target.name == "Reading"
        assert deleted_target.parent.name == "Book"
        assert not expected.exists()
        assert marker.read_text(encoding="utf-8") == "preserve"


def test_hard_delete_rejects_mismatched_metadata_identity():
    with tempfile.TemporaryDirectory() as root:
        library = Path(root, "library")
        manager = SessionManager(str(library / "session_state.json"))
        manager.update_session_metadata(
            "Book::Reading",
            book_name="AnotherBook",
            session_name="Reading",
            session_dir=str(library / "AnotherBook" / "Reading"),
        )
        try:
            manager.hard_delete_session("Book::Reading", str(library), dry_run=False)
        except ValueError as exc:
            assert "identity" in str(exc)
        else:
            raise AssertionError("mismatched metadata identity must not authorize deletion")
