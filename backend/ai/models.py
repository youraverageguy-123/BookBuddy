from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AIError(RuntimeError):
    """Base class for sanitized provider-neutral failures."""

    def __init__(self, message: str, *, credential_id: str = "", retry_after: float = 0.0, code: str = ""):
        super().__init__(message)
        self.credential_id = credential_id
        self.retry_after = max(0.0, float(retry_after))
        self.code = code


class AIServiceUnavailable(AIError):
    pass


class QuotaExhaustedError(AIError):
    pass


class SafetyRejectedError(AIError):
    pass


class TransientAIError(AIError):
    pass


class PermanentAIError(AIError):
    pass


@dataclass(frozen=True)
class GenerationRequest:
    role: str
    prompt: str
    response_schema: Any = None
    temperature: float = 0.0
    safety_profile: str = "default"
    media: bytes | None = None
    media_mime_type: str = "application/octet-stream"
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    response_json: bool = False
    # Caps retries for requests a person is waiting on; background work keeps the full budget.
    max_attempts: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    parsed: Any = None
    text: str = ""
    provider: str = ""
    model: str = ""
    credential_id: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    parsed: Any = None
    text: str = ""
    provider: str = ""
    model: str = ""
    credential_id: str = ""
    attempts: int = 1
    safety_triggers: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
