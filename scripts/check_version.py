"""Fail a local build when BookBuddy release metadata has drifted."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _json_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def main() -> int:
    canonical = _json_version(ROOT / "config" / "version.json")
    from config import ContractConfig

    versions = {
        "backend": ContractConfig().bookbuddy_version,
        "frontend": _json_version(ROOT / "frontend" / "package.json"),
        "tauri": _json_version(ROOT / "frontend" / "src-tauri" / "tauri.conf.json"),
        "cargo": str(
            tomllib.loads(
                (ROOT / "frontend" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
            )["package"]["version"]
        ),
    }
    mismatches = {name: value for name, value in versions.items() if value != canonical}
    if mismatches:
        details = ", ".join(f"{name}={value}" for name, value in sorted(mismatches.items()))
        print(f"BookBuddy version mismatch: canonical={canonical}; {details}", file=sys.stderr)
        return 1
    print(f"BookBuddy version metadata aligned at {canonical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
