from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any

from ai import AIManager, GenerationRequest, PermanentAIError, create_ai_manager
from config import IMAGE_EVIDENCE_SCHEMA_VERSION, load_config
from db_manager import BookDatabase
from graph_invariant_tests import assert_graph_invariants
from image_pipeline import parse_chapter_images
from snapshot_manager import EvidenceStore, ReplayCoordinator, SnapshotStore, resolver_manifest

from .collector import AuditCollector
from .database import (
    VOLATILE_COLUMNS,
    compare_databases,
    explain_query_plan,
    export_evidence_bundle,
    import_evidence_bundle,
    inspect_database,
)
from .fixtures import discover_epub, select_canary_chapters, validate_epub_archive
from .models import AuditReport
from .providers import DeterministicAuditProvider
from .reporting import write_report


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(command: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *command], capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False,
        )
        return (result.stdout or "").strip() if result.returncode == 0 else "unavailable"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def environment_metadata(config, fixture: Path | None = None) -> dict[str, Any]:
    diff = _git(["diff", "--binary", "HEAD"])
    status = _git(["status", "--short"])
    packages = {}
    try:
        from importlib.metadata import version
        for name in ("beautifulsoup4", "EbookLib", "fastapi", "pydantic", "uvicorn", "Pillow", "opencv-python-headless", "paddleocr"):
            try:
                packages[name] = version(name)
            except Exception:
                packages[name] = "unavailable"
    except Exception:
        pass
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "git_commit": _git(["rev-parse", "HEAD"]),
        "dirty": bool(status and status != "unavailable"),
        "dirty_status": status.splitlines(),
        "dirty_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff != "unavailable" else "unavailable",
        "configuration": {
            "server": asdict(config.server),
            "paths": {key: str(value) if value is not None else None for key, value in asdict(config.paths).items()},
            "ai": {"provider": config.ai.provider, "chapter_model": config.ai.chapter_model, "credentials": "<redacted>"},
            "contracts": asdict(config.contracts),
        },
        "packages": packages,
        "fixture": {"path": str(fixture), "sha256": file_hash(fixture)} if fixture else None,
        "resolver_manifest": resolver_manifest(),
    }


def _payload(chapter, analysis: dict, image_evidence: list[dict]) -> dict:
    result = dict(analysis)
    result.update({
        "image_evidence_schema_version": IMAGE_EVIDENCE_SCHEMA_VERSION,
        "image_evidence": image_evidence,
        "_section_type": getattr(chapter, "section_type", "CHAPTER"),
        "_chapter_title": getattr(chapter, "title", ""),
    })
    result.setdefault("_metadata", {})["audit_source"] = "deterministic_offline_v1"
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _sample_evidence(graph_path: Path, output: Path, seed: int, limit: int = 50, source_chapters: dict[int, str] | None = None) -> dict[str, Any]:
    conn = sqlite3.connect(graph_path)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT chapter, revision, payload_json, payload_hash, trigger_reason FROM chapter_evidence_revisions WHERE is_active=1 ORDER BY chapter"
    ))
    conn.close()
    rng = random.Random(seed)
    if len(rows) > limit:
        bucket = max(1, len(rows) // limit)
        selected = [rng.choice(rows[index:index + bucket]) for index in range(0, len(rows), bucket) if rows[index:index + bucket]][:limit]
    else:
        selected = rows
    samples = []
    failures = []
    prohibited = {"reader_state", "snapshot", "canonical_entity_id", "raw_bytes"}
    for row in selected:
        payload = json.loads(row["payload_json"])
        actual_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        serialized = json.dumps(payload, sort_keys=True)
        bad_keys = sorted(key for key in prohibited if f'"{key}"' in serialized)
        if actual_hash != row["payload_hash"] or bad_keys:
            failures.append({"chapter": row["chapter"], "hash_valid": actual_hash == row["payload_hash"], "prohibited": bad_keys})
        samples.append({
            "chapter": row["chapter"],
            "revision": row["revision"],
            "payload_hash": row["payload_hash"],
            "trigger_reason": row["trigger_reason"],
            "image_count": len(payload.get("image_evidence") or []),
            "keys": sorted(payload),
            "source_excerpt": (source_chapters or {}).get(int(row["chapter"]), "")[:400],
            "review_status": "pending_human_review",
        })
    _write_json(output, {"schema_version": "bookbuddy_evidence_review_v1", "samples": samples, "machine_failures": failures})
    return {"count": len(samples), "machine_failures": failures, "human_review_pending": bool(samples)}


def _snapshot_audit(db_dir: Path, chapters: int) -> dict[str, Any]:
    targets = sorted({index for index in (5, 20, 70, 150, chapters - 1) if 0 <= index < chapters})
    db = BookDatabase(str(db_dir))
    failures = []
    try:
        for chapter in targets:
            entry = SnapshotStore.get(db, chapter)
            if not entry:
                failures.append({"chapter": chapter, "reason": "missing"})
                continue
            snapshot = entry["snapshot"]
            if snapshot.get("contract_version") != "reader_snapshot_v2":
                failures.append({"chapter": chapter, "reason": "contract"})
            if snapshot.get("reader_contract", {}).get("as_of_chapter") != chapter:
                failures.append({"chapter": chapter, "reason": "scope"})
            if any(marker in json.dumps(snapshot) for marker in ('"source_quote"', '"raw_bytes"', '"actual_status"')):
                failures.append({"chapter": chapter, "reason": "engine_evidence"})
    finally:
        db.close()
    return {"chapters": targets, "failures": failures}


def run_baseline(report: AuditReport, output: Path) -> None:
    started = time.perf_counter()
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    (output / "baseline-tests.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    report.metrics["baseline_tests_seconds"] = round(time.perf_counter() - started, 3)
    report.add("baseline.tests", "pass" if result.returncode == 0 else "fail", "Existing unittest discovery completed", returncode=result.returncode)
    excluded_directories = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "audit",
        "build",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
    runtime_files = [
        path
        for path in root.rglob("*.py")
        if not path.name.startswith("test_")
        and not excluded_directories.intersection(part.lower() for part in path.relative_to(root).parts)
    ]
    markers = []
    bare_excepts = []
    prints = []
    for path in runtime_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line):
                markers.append({"file": str(path.relative_to(root)), "line": line_number, "text": line.strip()[:200]})
            if re.match(r"^\s*except\s*:\s*$", line):
                bare_excepts.append({"file": str(path.relative_to(root)), "line": line_number})
            if re.search(r"\bprint\s*\(", line):
                prints.append({"file": str(path.relative_to(root)), "line": line_number})
    _write_json(output / "code-health.json", {"markers": markers, "bare_excepts": bare_excepts, "cli_prints": prints})
    report.add(
        "code_health.correctness_markers",
        "pass" if not markers and not bare_excepts else "fail",
        "Runtime development markers and bare except clauses classified",
        markers=markers, bare_excepts=bare_excepts, cli_print_count=len(prints),
    )
    locks = ["requirements-core.lock", "requirements-image.lock", "requirements-dictionary.lock", "requirements-ai-gemini.lock"]
    invalid_locks = []
    for name in locks:
        for line in Path(root, "requirements", name).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "==" not in stripped:
                invalid_locks.append({"file": name, "line": stripped})
    report.add("dependencies.locks", "pass" if not invalid_locks else "fail", "Core and optional dependency groups have exact lock entries", invalid=invalid_locks)
    from app import create_app
    api = create_app(load_config())
    openapi = api.openapi()
    _write_json(output / "openapi.json", openapi)
    wildcard_cors = "*" in config_security_origins(load_config())
    report.add(
        "api.openapi_contract", "pass" if openapi.get("paths") and not wildcard_cors else "fail",
        "OpenAPI contract captured and CORS wildcard rejected",
        paths=len(openapi.get("paths", {})), wildcard_cors=wildcard_cors,
    )


def config_security_origins(config) -> tuple[str, ...]:
    return tuple(config.security.cors_origins)


def run_offline(report: AuditReport, config, fixture: Path, book, chapter_limit: int, output: Path) -> None:
    collector = AuditCollector()
    selected = list(book.chapters[:chapter_limit])
    report.metrics["fixture"] = {
        "available_chapters": len(book.chapters),
        "selected_chapters": len(selected),
        "selected_images": sum(len(getattr(item, "image_descriptors", []) or []) for item in selected),
        "selected_words": sum(int(getattr(item, "word_count", 0)) for item in selected),
    }
    offline_ai = AIManager(replace(config.ai, pacing_seconds=0.0, max_retries=1), DeterministicAuditProvider(), collector)
    with tempfile.TemporaryDirectory(prefix="bookbuddy-offline-audit-") as temp:
        db_dir = Path(temp) / "graph-a"
        db_dir.mkdir()
        db = BookDatabase(str(db_dir))
        image_total = accounted_images = degraded = 0
        try:
            for chapter in selected:
                with collector.measure("pipeline", "chapter", chapter=chapter.index) as event:
                    descriptors = list(getattr(chapter, "image_descriptors", []) or [])
                    image_total += len(descriptors)
                    images = parse_chapter_images(descriptors, db=db) if descriptors else []
                    accounted_images += len(images)
                    degraded += sum(1 for item in images if (item.get("failure_state") or {}).get("state") in {"degraded", "failed"})
                    content_hash = hashlib.sha256(chapter.content.encode("utf-8")).hexdigest()
                    generated = offline_ai.generate(GenerationRequest(
                        role="chapter_analysis",
                        prompt="BookBuddy deterministic offline audit request",
                        metadata={"chapter_index": chapter.index, "content_hash": content_hash},
                    ))
                    EvidenceStore.record(db, chapter.index, _payload(chapter, generated.parsed, images), trigger_reason="offline_audit")
                    event.input_count = 1 + len(descriptors)
                    event.output_count = 1 + len(images)
        finally:
            db.close()
            offline_ai.close()
        report.add(
            "pipeline.stage_accounting",
            "pass" if image_total == accounted_images else "fail",
            "Every selected chapter and image produced evidence or structured degradation",
            chapters=len(selected), images=image_total, accounted_images=accounted_images, degraded_images=degraded,
        )

        with collector.measure("replay", "full"):
            first = ReplayCoordinator(str(db_dir)).run(mode="full", reason="offline_audit")
        report.add(
            "replay.initial", "pass" if first.get("promoted") else "fail", "Initial full replay completed",
            promoted=first.get("promoted"), chapters=first.get("chapters"), snapshots_changed=first.get("snapshots_changed"),
        )
        graph_a = db_dir / "graph.db"
        integrity = inspect_database(graph_a)
        _write_json(output / "database-schema.json", integrity)
        report.add("database.integrity", "pass" if integrity["passed"] else "fail", "SQLite integrity, foreign keys, and table classification checked", integrity=integrity["integrity_check"], foreign_key_issues=len(integrity["foreign_key_check"]), unknown_tables=integrity["unknown_tables"])
        sanity = assert_graph_invariants(str(graph_a))
        report.add("graph.invariants", "pass", "Graph invariants completed", issue_count=sanity["issue_count"])

        bundle = export_evidence_bundle(graph_a, output / "evidence-bundle.json")
        comparisons = []
        for pass_number in range(1, 4):
            fresh = Path(temp) / f"graph-b-{pass_number}"
            fresh.mkdir()
            import_evidence_bundle(output / "evidence-bundle.json", fresh)
            replay = ReplayCoordinator(str(fresh)).run(mode="full", reason=f"determinism_{pass_number}")
            comparison = compare_databases(graph_a, fresh / "graph.db", categories=("derived",))
            comparison["pass"] = pass_number
            comparison["replay"] = {"promoted": replay.get("promoted"), "chapters": replay.get("chapters")}
            comparisons.append(comparison)
        _write_json(output / "replay-comparison.json", comparisons)
        report.add("replay.three_pass", "pass" if all(item["matched"] for item in comparisons) else "fail", "Three fresh evidence-only replays compared all derived tables", comparisons=comparisons)

        verify = ReplayCoordinator(str(db_dir)).run(mode="verify", reason="offline_verify")
        report.add("replay.verify_mode", "pass" if verify.get("verified") else "fail", "Verify mode compared staged output", result=verify)
        sample = _sample_evidence(
            graph_a,
            output / "evidence-review.json",
            report.seed,
            source_chapters={int(item.index): item.content for item in selected},
        )
        report.add("evidence.machine_validation", "pass" if not sample["machine_failures"] else "fail", "Deterministic evidence sample passed machine validation", **sample)
        report.add("evidence.human_review", "not_run", "Evidence packet requires human observational-truth review", severity="critical", artifact="evidence-review.json")
        snapshots = _snapshot_audit(db_dir, len(selected))
        report.add("snapshots.reader_safety", "pass" if not snapshots["failures"] else "fail", "Reader snapshot contract and engine-evidence exclusions checked", **snapshots)

        plans = {
            "entity_lookup": explain_query_plan(graph_a, "SELECT * FROM entities WHERE id = ?", (1,)),
            "alias_lookup": explain_query_plan(graph_a, "SELECT alias_name FROM aliases WHERE entity_id = ? AND first_seen <= ?", (1, len(selected) - 1)),
            "snapshot_lookup": explain_query_plan(graph_a, "SELECT * FROM reader_snapshot_current WHERE chapter = ?", (len(selected) - 1,)),
            "chapter_evidence": explain_query_plan(graph_a, "SELECT payload_json FROM chapter_evidence_revisions WHERE chapter = ? AND is_active = 1", (0,)),
        }
        _write_json(output / "query-plans.json", plans)
        scans = [
            {"query": name, "detail": row.get("detail", "")}
            for name, rows in plans.items() for row in rows
            if "SCAN " in str(row.get("detail", "")).upper()
        ]
        report.add("database.query_plans", "warning" if scans else "pass", "Representative reader query plans captured", severity="warning", scans=scans)
        shutil.copy2(graph_a, output / "graph-a.db")

    _write_json(output / "audit-events.json", collector.as_dicts())
    report.metrics["stages"] = collector.summary()
    report.exclusions["replay_volatile_columns"] = sorted(VOLATILE_COLUMNS)
    report.artifacts.update({
        "events": "audit-events.json", "schema": "database-schema.json", "evidence": "evidence-bundle.json",
        "review": "evidence-review.json", "replay": "replay-comparison.json", "queries": "query-plans.json", "graph": "graph-a.db",
    })


def run_stress(report: AuditReport, fixture: Path, book, output: Path) -> None:
    archive = validate_epub_archive(fixture)
    report.metrics["stress_fixture"] = {
        **archive,
        "chapters": len(book.chapters),
        "images": sum(len(getattr(item, "image_descriptors", []) or []) for item in book.chapters),
        "words": sum(int(getattr(item, "word_count", 0)) for item in book.chapters),
    }
    report.add("stress.extraction_inventory", "pass", "Full EPUB extraction inventory completed without modifying library data", **report.metrics["stress_fixture"])
    with tempfile.TemporaryDirectory(prefix="bookbuddy-scale-audit-") as temp:
        summary_path = Path(temp, "stress-summary.json")
        timeout_seconds = max(30, int(os.environ.get("BOOKBUDDY_AUDIT_STRESS_TIMEOUT_SECONDS", "600")))
        try:
            subprocess.run(
                [sys.executable, "-m", "audit.stress_worker", str(Path(temp, "database")), str(summary_path)],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                timeout=timeout_seconds,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            result = {"timed_out": True, "timeout_seconds": timeout_seconds}
            _write_json(output / "stress-summary.json", result)
            report.metrics["synthetic_stress"] = result
            report.add("stress.synthetic_scale", "fail", "Synthetic replay exceeded its hard time budget", timeout_seconds=timeout_seconds)
            return
        except subprocess.CalledProcessError as exc:
            result = {"worker_failed": True, "returncode": exc.returncode, "stderr": (exc.stderr or "")[-2000:]}
            _write_json(output / "stress-summary.json", result)
            report.metrics["synthetic_stress"] = result
            report.add("stress.synthetic_scale", "fail", "Synthetic replay worker failed", **result)
            return
        result = json.loads(summary_path.read_text(encoding="utf-8"))
        _write_json(output / "stress-summary.json", result)
        counts = result["counts"]
        passed = all([
            result["replay"]["promoted"], result["verify"]["verified"], result["integrity"],
            counts["chapter_evidence_revisions"] >= 2_000,
            counts["entities"] >= 10_000,
            counts["aliases"] >= 20_000,
            counts["relationship_history"] >= 20_000,
        ])
        report.metrics["synthetic_stress"] = result
        report.add("stress.synthetic_scale", "pass" if passed else "fail", "Synthetic replay scale completed", **result)


class _AttemptBudgetProvider:
    def __init__(self, provider, maximum: int):
        self.provider = provider
        self.maximum = maximum
        self.attempts = 0

    def is_available(self, capability: str) -> bool:
        return self.provider is not None and self.provider.is_available(capability)

    def generate(self, request, *, model: str):
        if self.attempts >= self.maximum:
            raise PermanentAIError("Live audit request-attempt budget exhausted")
        self.attempts += 1
        return self.provider.generate(request, model=model)

    def close(self) -> None:
        if self.provider is not None:
            self.provider.close()


def _usage_count(usage: dict, names: tuple[str, ...]) -> int:
    for name in names:
        value = usage.get(name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def audited_model_price(pricing: dict, model: str) -> dict:
    model_price = pricing.get("models", {}).get(model)
    if not model_price:
        raise RuntimeError(f"No audited pricing entry for live model {model}")
    required = ("input_per_million_tokens", "output_per_million_tokens")
    if any(not isinstance(model_price.get(name), (int, float)) for name in required):
        raise RuntimeError(f"Official token pricing is not published for live model {model}")
    return model_price


def run_live_canary(report: AuditReport, config, book, chapters: int, output: Path, *, vision: bool) -> None:
    from analysis_engine import process_single_chapter

    selected = select_canary_chapters(list(book.chapters[:chapters]))
    pricing_path = Path(__file__).with_name("pricing.json")
    pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
    model_price = audited_model_price(pricing, config.ai.chapter_model)
    collector = AuditCollector()
    bounded_config = replace(
        config,
        ai=replace(config.ai, max_retries=2, vision_max_retries=2, pacing_seconds=0.0),
    )
    manager = create_ai_manager(bounded_config, observer=collector)
    manager.provider = _AttemptBudgetProvider(manager.provider, 10)
    if not manager.is_available("text"):
        manager.close()
        raise RuntimeError("Configured live text provider is unavailable")
    with tempfile.TemporaryDirectory(prefix="bookbuddy-live-canary-") as temp:
        db_dir = Path(temp) / "database"
        db_dir.mkdir()
        db = BookDatabase(str(db_dir))
        completed = []
        try:
            for chapter_index in selected:
                process_single_chapter(
                    manager,
                    chapter_index,
                    book,
                    str(db_dir),
                    db,
                    {},
                    False,
                    False,
                    True,
                    "live_canary",
                    vision,
                )
                completed.append(chapter_index)
        finally:
            db.close()
            attempts = manager.provider.attempts
            manager.close()
        replay = ReplayCoordinator(str(db_dir)).run(mode="full", reason="live_canary")
        integrity = inspect_database(db_dir / "graph.db")
        shutil.copy2(db_dir / "graph.db", output / "live-canary.db")
    usages = [event.token_usage for event in collector.events if event.stage == "ai" and event.status == "ok"]
    input_tokens = sum(_usage_count(item, ("input_tokens", "prompt_token_count", "prompt_tokens")) for item in usages)
    output_tokens = sum(_usage_count(item, ("output_tokens", "candidates_token_count", "completion_tokens")) for item in usages)
    cost = (
        input_tokens * float(model_price["input_per_million_tokens"])
        + output_tokens * float(model_price["output_per_million_tokens"])
    ) / 1_000_000
    _write_json(output / "live-canary-events.json", collector.as_dicts())
    report.metrics["live_canary"] = {
        "chapters": completed,
        "attempts": attempts,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": round(cost, 6),
        "pricing_as_of": pricing.get("as_of"),
    }
    report.add(
        "ai.live_canary",
        "pass" if completed == selected and attempts <= 10 and replay.get("promoted") and integrity["passed"] else "fail",
        "Bounded live-provider canary completed",
        **report.metrics["live_canary"],
    )


def execute(
    *, profile: str, epub: str | None, chapters: int, seed: int, output: str | Path,
    live_ai: bool = False, vision: bool = False,
) -> AuditReport:
    config = load_config()
    target = Path(output).resolve()
    target.mkdir(parents=True, exist_ok=True)
    fixture = parsed = None
    if profile in {"offline", "stress", "live-canary", "all"}:
        if epub:
            from epub_parser import parse_epub
            fixture = Path(epub).resolve()
            validate_epub_archive(fixture)
            parsed = parse_epub(str(fixture))
        else:
            fixture, parsed = discover_epub(config.paths.library_dir, chapters)
    report = AuditReport(uuid.uuid4().hex, profile, seed, environment_metadata(config, fixture))
    try:
        if profile in {"baseline", "all"}:
            run_baseline(report, target)
        if profile in {"offline", "all"}:
            run_offline(report, config, fixture, parsed, min(chapters, len(parsed.chapters)), target)
        if profile in {"stress", "all"}:
            run_stress(report, fixture, parsed, target)
        if profile in {"live-canary", "all"}:
            canaries = select_canary_chapters(list(parsed.chapters[:chapters]))
            if not live_ai:
                report.add("ai.live_canary", "not_run", "Live canary requires --live-ai; no network request was made", severity="critical", chapters=canaries)
            else:
                run_live_canary(report, config, parsed, min(chapters, len(parsed.chapters)), target, vision=vision)
    except Exception as exc:
        report.add("audit.execution", "fail", f"Audit profile raised {type(exc).__name__}: {exc}", error_class=type(exc).__name__)
    finally:
        report.artifacts.update(write_report(report, target))
    return report
