from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Severity = Literal["critical", "warning", "info"]
FindingStatus = Literal["pass", "fail", "warning", "not_run", "not_applicable"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class AuditFinding:
    check: str
    status: FindingStatus
    severity: Severity = "critical"
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    run_id: str
    profile: str
    seed: int
    metadata: dict[str, Any]
    schema_version: str = "bookbuddy_audit_v1"
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    findings: list[AuditFinding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    exclusions: dict[str, list[str]] = field(default_factory=dict)

    def add(self, check: str, status: FindingStatus, summary: str, *, severity: Severity = "critical", **details: Any) -> None:
        self.findings.append(AuditFinding(check, status, severity, summary, details))

    @property
    def blockers(self) -> list[AuditFinding]:
        return [item for item in self.findings if item.severity == "critical" and item.status == "fail"]

    @property
    def warnings(self) -> list[AuditFinding]:
        return [item for item in self.findings if item.status == "warning" or (item.severity == "warning" and item.status == "fail")]

    @property
    def release_decision(self) -> str:
        if self.blockers:
            return "blocked"
        if any(item.status == "not_run" and item.severity == "critical" for item in self.findings):
            return "pending"
        return "ready_with_warnings" if self.warnings else "ready"

    def finish(self) -> None:
        self.finished_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["release_decision"] = self.release_decision
        payload["summary"] = {
            "passed": sum(item.status == "pass" for item in self.findings),
            "failed": sum(item.status == "fail" for item in self.findings),
            "warnings": len(self.warnings),
            "not_run": sum(item.status == "not_run" for item in self.findings),
            "blockers": len(self.blockers),
        }
        return payload
