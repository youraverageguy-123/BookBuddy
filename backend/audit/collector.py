from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import statistics
import threading
import time
import tracemalloc
from typing import Any, Iterator


@dataclass
class AuditEvent:
    stage: str
    operation: str
    chapter: int | None = None
    duration_ms: float = 0.0
    status: str = "ok"
    input_count: int | None = None
    output_count: int | None = None
    skip_reason: str = ""
    retries: int = 0
    token_usage: dict[str, Any] = field(default_factory=dict)
    cache_outcome: str = ""
    error_class: str = ""
    memory_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditCollector:
    """Thread-safe structured event sink; callers opt in by injection."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self._lock = threading.Lock()
        if not tracemalloc.is_tracing():
            tracemalloc.start()

    def record(self, event: AuditEvent | dict[str, Any]) -> None:
        if isinstance(event, dict):
            event = AuditEvent(**event)
        with self._lock:
            self.events.append(event)

    @contextmanager
    def measure(self, stage: str, operation: str, *, chapter: int | None = None, **metadata: Any) -> Iterator[AuditEvent]:
        event = AuditEvent(stage=stage, operation=operation, chapter=chapter, metadata=metadata)
        started = time.perf_counter()
        try:
            yield event
        except Exception as exc:
            event.status = "error"
            event.error_class = type(exc).__name__
            raise
        finally:
            event.duration_ms = round((time.perf_counter() - started) * 1000, 3)
            event.memory_bytes = tracemalloc.get_traced_memory()[0]
            self.record(event)

    def summary(self) -> dict[str, Any]:
        grouped: dict[str, list[float]] = {}
        for event in self.events:
            grouped.setdefault(f"{event.stage}.{event.operation}", []).append(event.duration_ms)
        metrics = {}
        for key, values in sorted(grouped.items()):
            ordered = sorted(values)
            index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.95)))
            metrics[key] = {
                "count": len(values),
                "average_ms": round(statistics.fmean(values), 3),
                "median_ms": round(statistics.median(values), 3),
                "p95_ms": round(ordered[index], 3),
                "max_ms": round(max(values), 3),
            }
        return metrics

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.events]
