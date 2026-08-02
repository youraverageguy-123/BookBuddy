"""Provider-neutral AI boundary for BookBuddy."""

from .manager import AIManager
from .factory import create_ai_manager
from .models import (
    AIError,
    AIServiceUnavailable,
    GenerationRequest,
    GenerationResult,
    PermanentAIError,
    QuotaExhaustedError,
    SafetyRejectedError,
    TransientAIError,
)

__all__ = [
    "AIManager", "create_ai_manager", "AIError", "AIServiceUnavailable", "GenerationRequest",
    "GenerationResult", "PermanentAIError", "QuotaExhaustedError",
    "SafetyRejectedError", "TransientAIError",
]
