from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from config import AIConfig
from .models import (
    AIServiceUnavailable,
    GenerationRequest,
    PermanentAIError,
    ProviderResponse,
    QuotaExhaustedError,
    SafetyRejectedError,
    TransientAIError,
)


@dataclass
class _Credential:
    identifier: str
    client: Any
    next_available_at: float = 0.0


class GeminiProvider:
    """Gemini SDK adapter. Importing this module does not import the SDK."""

    name = "gemini"

    def __init__(self, config: AIConfig):
        self.config = config
        self._lock = threading.Lock()
        self._indexes = {"text": 0, "vision": 0}
        self._closed = False
        self._sdk_error: Exception | None = None
        self._types = None
        self._pools: dict[str, list[_Credential]] = {"text": [], "vision": []}
        try:
            from google import genai
            from google.genai import types

            self._types = types
            for capability, credentials in (
                ("text", config.api_keys), ("vision", config.vision_api_keys)
            ):
                for identifier, secret in credentials:
                    http_options = types.HttpOptions(timeout=int(config.request_timeout_seconds * 1000))
                    client = genai.Client(api_key=secret, http_options=http_options)
                    self._pools[capability].append(_Credential(identifier, client))
        except (ImportError, ModuleNotFoundError) as exc:
            self._sdk_error = exc
        except Exception as exc:
            # Provider initialization is optional. Keep the API available.
            self._sdk_error = exc
            self.close()

    def is_available(self, capability: str) -> bool:
        return not self._closed and self._sdk_error is None and bool(self._pools.get(capability))

    def _next(self, capability: str) -> _Credential:
        if not self.is_available(capability):
            raise AIServiceUnavailable(f"AI capability unavailable: {capability}")
        with self._lock:
            pool = self._pools[capability]
            now = time.monotonic()
            start = self._indexes[capability]
            for offset in range(len(pool)):
                index = (start + offset) % len(pool)
                credential = pool[index]
                if credential.next_available_at <= now:
                    self._indexes[capability] = (index + 1) % len(pool)
                    return credential
            retry_after = max(0.0, min(item.next_available_at for item in pool) - now)
        raise TransientAIError("All AI credentials are cooling down", retry_after=retry_after)

    def _cooldown(self, capability: str, identifier: str) -> None:
        with self._lock:
            for credential in self._pools[capability]:
                if credential.identifier == identifier:
                    credential.next_available_at = max(
                        credential.next_available_at,
                        time.monotonic() + self.config.key_cooldown_seconds,
                    )

    @staticmethod
    def _parsed_response(response) -> tuple[Any, str]:
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, dict):
                return dict(parsed), str(getattr(response, "text", "") or "")
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump(), str(getattr(response, "text", "") or "")
            if hasattr(parsed, "dict"):
                return parsed.dict(), str(getattr(response, "text", "") or "")
        text = str(getattr(response, "text", "") or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines.pop(0)
            if lines and lines[-1].startswith("```"):
                lines.pop()
            text = "\n".join(lines).strip()
        return None, text

    def generate(self, request: GenerationRequest, *, model: str) -> ProviderResponse:
        capability = "vision" if request.role == "vision" else "text"
        credential = self._next(capability)
        try:
            contents: Any = request.prompt
            if request.media is not None:
                contents = [
                    request.prompt,
                    self._types.Part.from_bytes(data=request.media, mime_type=request.media_mime_type),
                ]
            config_kwargs: dict[str, Any] = {"temperature": request.temperature}
            if request.response_schema is not None:
                config_kwargs.update(
                    response_mime_type="application/json",
                    response_schema=request.response_schema,
                )
            elif request.role == "vision":
                config_kwargs["response_mime_type"] = "application/json"
            if request.safety_profile == "unrestricted":
                config_kwargs["safety_settings"] = [
                    self._types.SafetySetting(category=category, threshold=self._types.HarmBlockThreshold.OFF)
                    for category in (
                        self._types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        self._types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        self._types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        self._types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    )
                ]
            response = credential.client.models.generate_content(
                model=model,
                contents=contents,
                config=self._types.GenerateContentConfig(**config_kwargs),
            )
            parsed, text = self._parsed_response(response)
            prompt_feedback = getattr(response, "prompt_feedback", None)
            if getattr(prompt_feedback, "block_reason", None):
                raise SafetyRejectedError("AI request was blocked by provider safety policy")
            if request.response_schema is not None or request.role == "vision":
                if parsed is None and text:
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise PermanentAIError("AI returned no parseable JSON") from exc
                if parsed is None:
                    raise PermanentAIError("AI returned no parseable JSON")
            usage = getattr(response, "usage_metadata", None)
            if hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            return ProviderResponse(
                parsed=parsed,
                text=text,
                provider=self.name,
                model=model,
                credential_id=credential.identifier,
                usage=usage if isinstance(usage, dict) else {},
            )
        except (SafetyRejectedError, PermanentAIError):
            raise
        except Exception as exc:
            message = str(exc).lower()
            if "blocked" in message or "prohibited" in message or "safety" in message:
                raise SafetyRejectedError("AI request was blocked", credential_id=credential.identifier) from exc
            if any(marker in message for marker in ("429", "quota", "resource exhausted", "exhausted")):
                self._cooldown(capability, credential.identifier)
                raise QuotaExhaustedError("AI quota exhausted", credential_id=credential.identifier) from exc
            if any(marker in message for marker in ("timeout", "timed out", "connection", "temporar", "500", "502", "503", "504")):
                raise TransientAIError("Transient AI provider failure", credential_id=credential.identifier) from exc
            raise PermanentAIError(f"AI provider failure: {type(exc).__name__}", credential_id=credential.identifier) from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for pool in self._pools.values():
            for credential in pool:
                close = getattr(credential.client, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
