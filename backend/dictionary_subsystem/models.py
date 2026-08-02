from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


KnowledgeKind = Literal["entity", "terminology"]


@dataclass(frozen=True)
class KnowledgeObjectRef:
    kind: KnowledgeKind
    object_id: int


@dataclass
class HighlightRequest:
    chapter_index: int
    selected_text: str
    selection_start: int | None = None
    selection_end: int | None = None
    context_text: str | None = None
    sentence_text: str | None = None
    previous_sentence: str | None = None
    next_sentence: str | None = None
    paragraph_text: str | None = None
    sentence_selection_start: int | None = None
    sentence_selection_end: int | None = None
    language: str = "en"
    allow_ai_fallback: bool = False
    knowledge_as_of_chapter: int | None = None
    explain_function_words: bool = False


@dataclass(frozen=True)
class ContextWindow:
    sentence: str
    previous_sentence: str = ""
    next_sentence: str = ""
    paragraph: str = ""
    selection_start: int | None = None
    selection_end: int | None = None

    @property
    def surrounding_text(self) -> str:
        return " ".join(
            value.strip()
            for value in (self.previous_sentence, self.sentence, self.next_sentence)
            if value and value.strip()
        )


@dataclass
class ServiceResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    provider_version: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.data,
            "status": self.status,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "diagnostics": self.diagnostics,
        }
