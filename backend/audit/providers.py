from __future__ import annotations

import hashlib

from ai.models import ProviderResponse


def deterministic_payload(content_hash: str, chapter_index: int) -> dict:
    token = hashlib.sha256(f"{chapter_index}:{content_hash}".encode("utf-8")).hexdigest()[:16]
    name = f"AuditSubject_{token}"
    return {
        "pov_character_found": name,
        "new_aliases_discovered": [],
        "new_group_aliases_discovered": [],
        "entities_present": [{"name": name, "entity_type": "INDIVIDUAL", "active_status": "active_participant"}],
        "relationships": [],
        "major_events": [],
        "entity_semantic_relations": [],
        "language_observations": [],
        "life_status_events": [],
        "legacy_signals": [],
        "_metadata": {"audit_provider": "deterministic_v1", "source_hash": content_hash},
    }


class DeterministicAuditProvider:
    """Offline provider whose output depends only on request metadata."""

    def is_available(self, capability: str) -> bool:
        return capability == "text"

    def generate(self, request, *, model: str) -> ProviderResponse:
        content_hash = str(request.metadata.get("content_hash") or "")
        chapter_index = int(request.metadata.get("chapter_index", 0))
        payload = deterministic_payload(content_hash, chapter_index)
        return ProviderResponse(
            parsed=payload,
            provider="deterministic-audit",
            model=model,
            credential_id="offline",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def close(self) -> None:
        return None
