"""BookBuddy non-destructive release audit command."""

from __future__ import annotations

import argparse
import json

from audit.runner import execute


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("baseline", "offline", "live-canary", "stress", "all"))
    parser.add_argument("--epub", help="Explicit user-owned EPUB; otherwise discover the largest qualifying library fixture")
    parser.add_argument("--chapters", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--output", default="audit-results")
    parser.add_argument("--live-ai", action="store_true", help="Explicitly authorize the bounded live-provider canary")
    parser.add_argument("--vision", action="store_true", help="Separately authorize bounded vision fallback during live canary")
    parser.add_argument("--fail-on", choices=("critical", "warning"), default="critical")
    args = parser.parse_args()
    if args.chapters < 1:
        parser.error("--chapters must be positive")
    if args.vision and not args.live_ai:
        parser.error("--vision requires --live-ai")
    report = execute(
        profile=args.profile, epub=args.epub, chapters=args.chapters, seed=args.seed,
        output=args.output, live_ai=args.live_ai, vision=args.vision,
    )
    print(json.dumps({"decision": report.release_decision, "report": report.artifacts.get("json")}, indent=2))
    if report.blockers:
        return 1
    if args.fail_on == "warning" and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
