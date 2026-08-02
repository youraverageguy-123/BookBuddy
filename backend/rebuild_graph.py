"""Interactive entry point for non-destructive graph replay."""

import os
import time
import argparse
import json

from snapshot_manager import ReplayCoordinator


def _choose(items: list[str], label: str) -> str:
    if not items:
        raise RuntimeError(f"No {label} found.")
    print(f"\nAvailable {label}:")
    for index, item in enumerate(items):
        print(f"[{index}] {item}")
    return items[int(input(f"\nSelect {label[:-1]} index: "))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic BookBuddy graph replay.")
    parser.add_argument("--db-dir", help="Session database directory; omit for interactive selection")
    parser.add_argument("--mode", choices=("normal", "full", "verify"), default="normal")
    parser.add_argument("--reason", default="cli_rebuild")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if args.db_dir:
        db_dir = args.db_dir
        label = db_dir
    else:
        library_dir = "library"
        books = sorted(
            name for name in os.listdir(library_dir)
            if os.path.isdir(os.path.join(library_dir, name))
        ) if os.path.isdir(library_dir) else []
        book_name = _choose(books, "books")
        book_dir = os.path.join(library_dir, book_name)
        sessions = sorted(
            name for name in os.listdir(book_dir)
            if os.path.isdir(os.path.join(book_dir, name))
        )
        session_name = _choose(sessions, "sessions")
        db_dir = os.path.join(book_dir, session_name, "database")
        label = f"{book_name} / {session_name}"

    print(f"Running {args.mode} replay for {label}...")
    started_at = time.time()
    result = ReplayCoordinator(db_dir).run(mode=args.mode, reason=args.reason)
    result["elapsed_seconds"] = round(time.time() - started_at, 3)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{args.mode} replay {'promoted' if result.get('promoted') else 'not promoted'} "
            f"after {result['elapsed_seconds']:.2f}s; "
            f"{result.get('snapshots_changed', 0)} reader snapshot revision(s) changed."
        )


if __name__ == "__main__":
    main()
