from __future__ import annotations

from typing import Protocol

from .models import GenerationRequest, ProviderResponse


class AIProvider(Protocol):
    name: str

    def is_available(self, capability: str) -> bool: ...
    def generate(self, request: GenerationRequest, *, model: str) -> ProviderResponse: ...
    def close(self) -> None: ...
