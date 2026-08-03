"""Non-secret persisted state for optional AI onboarding and verification."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time


DEFAULT_STATE = {
    "schema_version": "bookbuddy_ai_state_v1",
    "background_analysis_enabled": False,
    "background_analysis_paused": False,
    "verification": {},
}


class AISettingsStateStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def read(self) -> dict:
        if not self.path.is_file():
            return {**DEFAULT_STATE, "verification": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {**DEFAULT_STATE, "verification": {}}
        return {
            **DEFAULT_STATE,
            "background_analysis_enabled": bool(payload.get("background_analysis_enabled", False)),
            "background_analysis_paused": bool(payload.get("background_analysis_paused", False)),
            "verification": payload.get("verification", {}) if isinstance(payload.get("verification"), dict) else {},
        }

    def write(self, state: dict) -> dict:
        payload = {
            "schema_version": DEFAULT_STATE["schema_version"],
            "background_analysis_enabled": bool(state.get("background_analysis_enabled", False)),
            "background_analysis_paused": bool(state.get("background_analysis_paused", False)),
            "verification": state.get("verification", {}),
            "updated_at": time.time(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return payload

    def update(self, **changes) -> dict:
        state = self.read()
        state.update(changes)
        return self.write(state)

    def record_verification(self, capability: str, outcome: str, model: str, message: str) -> dict:
        state = self.read()
        verification = dict(state["verification"])
        verification[capability] = {
            "outcome": outcome,
            "model": model,
            "message": message,
            "verified_at": time.time(),
        }
        state["verification"] = verification
        return self.write(state)

