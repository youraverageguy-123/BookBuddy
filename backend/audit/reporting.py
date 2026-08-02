from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import AuditReport


def write_report(report: AuditReport, output_dir: str | Path) -> dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    report.finish()
    json_path = target / "audit-report.json"
    markdown_path = target / "audit-report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    checksums = target / "checksums.sha256"
    lines = []
    for path in sorted(item for item in target.rglob("*") if item.is_file() and item != checksums):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(target).as_posix()}")
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path.resolve()), "markdown": str(markdown_path.resolve()), "checksums": str(checksums.resolve())}


def _markdown(report: AuditReport) -> str:
    lines = [
        "# BookBuddy Release Audit",
        "",
        f"- Run: `{report.run_id}`",
        f"- Profile: `{report.profile}`",
        f"- Decision: **{report.release_decision}**",
        f"- Started: `{report.started_at}`",
        f"- Finished: `{report.finished_at or ''}`",
        "",
        "## Findings",
        "",
        "| Check | Status | Severity | Summary |",
        "|---|---|---|---|",
    ]
    for item in report.findings:
        summary = item.summary.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{item.check}` | {item.status} | {item.severity} | {summary} |")
    lines.extend(["", "## Metrics", "", "```json", json.dumps(report.metrics, indent=2, ensure_ascii=False, sort_keys=True), "```", ""])
    if report.exclusions:
        lines.extend(["## Replay exclusions", "", "```json", json.dumps(report.exclusions, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)
