from __future__ import annotations

from config import AppConfig
from .gemini_provider import GeminiProvider
from .manager import AIManager


def create_ai_manager(config: AppConfig, observer=None) -> AIManager:
    provider = GeminiProvider(config.ai) if config.ai.provider == "gemini" else None
    return AIManager(config.ai, provider, observer)
