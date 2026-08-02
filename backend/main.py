"""Canonical BookBuddy backend process launcher."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def _diagnostic(message: str) -> None:
    """Write opt-in frozen-startup breadcrumbs without affecting normal logs."""
    path = os.environ.get("BOOKBUDDY_DIAGNOSTIC_LOG")
    if not path:
        return
    try:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def _ensure_frozen_streams() -> None:
    """Give windowless PyInstaller builds valid streams for logging libraries."""
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _configuration_root() -> Path | None:
    """Find an explicitly supplied, adjacent, or verified source-tree .env."""
    explicit = os.environ.get("BOOKBUDDY_PROJECT_ROOT", "").strip()
    if explicit:
        return Path(explicit).resolve()
    candidates = [Path.cwd().resolve()]
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        candidates.extend([executable.parent, *list(executable.parents)[:5]])
    else:
        source_dir = Path(__file__).resolve().parent
        candidates.extend([source_dir, source_dir.parent])
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        env_files = (candidate / ".env", candidate / "config" / ".env")
        if not any(path.is_file() for path in env_files):
            continue
        if candidate == Path.cwd().resolve() or candidate == Path(sys.executable).resolve().parent or (candidate / "packaging" / "bookbuddy-backend.spec").is_file():
            return candidate
    return None


def main() -> int:
    _ensure_frozen_streams()
    _diagnostic("launcher:entered")
    from dependency_manager import ensure_dependencies

    # PyInstaller has already resolved and embedded the required import graph.
    # Distribution metadata is intentionally absent from a one-file bundle,
    # so the source-environment dependency check would report false negatives.
    if not getattr(sys, "frozen", False):
        ensure_dependencies("BookBuddy Backend", prompt=True)
    _diagnostic(f"launcher:dependencies_ready:frozen={getattr(sys, 'frozen', False)}")

    from config import load_config
    import uvicorn
    _diagnostic("launcher:runtime_imports_ready")

    configuration_root = _configuration_root()
    if configuration_root is not None:
        os.environ.setdefault("BOOKBUDDY_PROJECT_ROOT", str(configuration_root))
    config = load_config(configuration_root)
    _diagnostic(f"launcher:config_ready:{config.server.host}:{config.server.port}")
    from app import app
    _diagnostic("launcher:asgi_app_ready")
    logging.basicConfig(
        level=getattr(logging, config.server.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _diagnostic("launcher:uvicorn_starting")
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level.lower(),
        loop="asyncio",
        http="h11",
        ws="none",
        timeout_graceful_shutdown=int(config.server.shutdown_timeout_seconds),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
