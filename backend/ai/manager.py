from __future__ import annotations

import logging
import threading
import time

from config import AIConfig
from .models import (
    AIServiceUnavailable,
    GenerationRequest,
    GenerationResult,
    PermanentAIError,
    QuotaExhaustedError,
    SafetyRejectedError,
    TransientAIError,
)


class AIManager:
    """Select models and apply bounded retry policy around one active provider."""

    def __init__(self, config: AIConfig, provider=None, observer=None):
        self.config = config
        self.provider = provider
        self._closing = threading.Event()
        self._logger = logging.getLogger(__name__)
        self.observer = observer

    def _observe(self, payload: dict) -> None:
        if self.observer is None:
            return
        try:
            callback = getattr(self.observer, "record", self.observer)
            callback(payload)
        except Exception:
            self._logger.debug("AI observer rejected an event", exc_info=True)

    def is_available(self, capability: str) -> bool:
        return bool(
            not self._closing.is_set()
            and self.provider is not None
            and self.provider.is_available(capability)
        )

    def _model_for(self, role: str) -> str:
        if role == "vision":
            return self.config.vision_model
        if role == "dictionary":
            return self.config.dictionary_model
        return self.config.chapter_model

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        capability = "vision" if request.role == "vision" else "text"
        if not self.is_available(capability):
            raise AIServiceUnavailable(f"AI capability unavailable: {capability}")
        attempts_allowed = self.config.vision_max_retries if capability == "vision" else self.config.max_retries
        safety_triggers = 0
        last_error: Exception | None = None

        for attempt in range(1, attempts_allowed + 1):
            if self._closing.is_set():
                raise AIServiceUnavailable("AI service is shutting down")
            try:
                if self.config.pacing_seconds and self._closing.wait(self.config.pacing_seconds):
                    raise AIServiceUnavailable("AI service is shutting down")
                response = self.provider.generate(request, model=self._model_for(request.role))
                result = GenerationResult(
                    parsed=response.parsed,
                    text=response.text,
                    provider=response.provider,
                    model=response.model,
                    credential_id=response.credential_id,
                    attempts=attempt,
                    safety_triggers=safety_triggers,
                    usage=response.usage,
                )
                self._observe({
                    "stage": "ai", "operation": request.role,
                    "chapter": request.metadata.get("chapter_index"),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "status": "ok", "retries": max(0, attempt - 1),
                    "token_usage": response.usage,
                    "metadata": {"provider": response.provider, "model": response.model},
                })
                return result
            except SafetyRejectedError as exc:
                last_error = exc
                safety_triggers += 1
                delay = max(self.config.safety_retry_seconds, exc.retry_after)
            except (QuotaExhaustedError, TransientAIError) as exc:
                last_error = exc
                delay = max(exc.retry_after, min(2 ** (attempt - 1), 60))
            except PermanentAIError:
                raise
            if attempt < attempts_allowed and self._closing.wait(delay):
                raise AIServiceUnavailable("AI service is shutting down")

        if last_error is not None:
            raise last_error
        raise AIServiceUnavailable("AI generation failed without a provider response")

    def verify(self, capability: str) -> GenerationResult:
        if capability not in {"text", "vision"} or not self.is_available(capability):
            raise AIServiceUnavailable(f"AI capability unavailable: {capability}", code="provider_unavailable")
        role = "vision" if capability == "vision" else "chapter"
        model = self._model_for(role)
        response = self.provider.verify(capability, model=model)
        return GenerationResult(
            provider=response.provider,
            model=response.model,
            credential_id=response.credential_id,
        )

    def list_models(self, capability: str = "text") -> list[dict]:
        if capability not in {"text", "vision"} or not self.is_available(capability):
            raise AIServiceUnavailable(f"AI capability unavailable: {capability}", code="provider_unavailable")
        lister = getattr(self.provider, "list_models", None)
        if lister is None:
            raise AIServiceUnavailable("This provider cannot list models", code="provider_unavailable")
        return lister(capability)

    def close(self) -> None:
        if self._closing.is_set():
            return
        self._closing.set()
        if self.provider is not None:
            self.provider.close()

    def reconfigure(self, config: AIConfig, provider) -> None:
        """Atomically replace optional provider credentials without restarting."""
        old_provider = self.provider
        self.config = config
        self.provider = provider
        self._closing.clear()
        if old_provider is not None:
            old_provider.close()
