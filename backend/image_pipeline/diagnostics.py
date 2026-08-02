"""Structured diagnostics shared by image pipeline stages."""

from __future__ import annotations


def diagnostic(
    stage: str,
    status: str,
    code: str,
    detail: str = "",
    *,
    recoverable: bool = True,
    **context,
) -> dict:
    item = {
        "stage": str(stage or "unknown"),
        "status": str(status or "unknown"),
        "code": str(code or "unknown"),
        "detail": str(detail or ""),
        "recoverable": bool(recoverable),
    }
    if context:
        item["context"] = context
    return item


def failure_state(stage: str, code: str, recoverable: bool = True) -> dict:
    return {
        "state": "degraded" if recoverable else "failed",
        "stage": str(stage or "unknown"),
        "code": str(code or "unknown"),
        "recoverable": bool(recoverable),
    }
