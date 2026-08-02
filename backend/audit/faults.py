from __future__ import annotations

from dataclasses import dataclass


class InjectedAuditFault(RuntimeError):
    pass


@dataclass
class FaultInjector:
    """Explicit test-only fault injector; never loaded from process environment."""

    point: str = ""
    occurrence: int = 1
    _seen: int = 0

    def hit(self, point: str) -> None:
        if point != self.point:
            return
        self._seen += 1
        if self._seen == self.occurrence:
            raise InjectedAuditFault(f"Injected audit fault at {point}")
