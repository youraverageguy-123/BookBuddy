"""Bounded, redacted BookBuddy file logging for production diagnostics."""
from __future__ import annotations

import gzip
import logging
import logging.handlers
import os
import re
import shutil
from pathlib import Path


class RedactionFilter(logging.Filter):
    _patterns = (
        (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+"), r"\1<redacted>"),
        (re.compile(r"(?i)((?:api[_-]?key|token|credential)\s*[:=]\s*)[^\s,;]+"), r"\1<redacted>"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in self._patterns:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True


def _gzip_rotate(source: str, destination: str) -> None:
    with open(source, "rb") as input_file, gzip.open(destination, "wb", compresslevel=6) as output_file:
        shutil.copyfileobj(input_file, output_file)
    os.remove(source)


def configure_file_logging(
    log_dir: str | Path, level: int = logging.INFO
) -> tuple[Path, logging.Handler, bool]:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "bookbuddy.log"
    root = logging.getLogger()
    marker = str(target.resolve())
    existing = next(
        (handler for handler in root.handlers if getattr(handler, "bookbuddy_target", None) == marker),
        None,
    )
    if existing is not None:
        return target, existing, False
    handler = logging.handlers.RotatingFileHandler(
        target, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8", delay=True
    )
    handler.bookbuddy_target = marker
    handler.namer = lambda name: f"{name}.gz"
    handler.rotator = _gzip_rotate
    handler.addFilter(RedactionFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.setLevel(level)
    root.addHandler(handler)
    root.setLevel(level)
    return target, handler, True


def close_file_logging(handler: logging.Handler, *, owned: bool) -> None:
    """Release a handler created for one application lifespan.

    A reused handler belongs to the lifespan that originally registered it and
    must not be removed by a second, overlapping application instance.
    """
    if not owned:
        return
    root = logging.getLogger()
    root.removeHandler(handler)
    handler.close()
