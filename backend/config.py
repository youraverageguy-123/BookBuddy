"""Immutable BookBuddy configuration.

Runtime configuration is loaded once by the composition root.  The module
level names at the bottom are compatibility views for the existing domain
modules; their values all originate from ``DEFAULT_CONFIG``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_canonical_version() -> str:
    version_path = PROJECT_ROOT / "config" / "version.json"
    try:
        payload = json.loads(version_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Canonical version metadata is unreadable: {version_path}") from exc
    version = str(payload.get("version", "")).strip()
    components = version.split(".")
    if len(components) != 3 or any(not component.isdigit() for component in components):
        raise RuntimeError("Canonical BookBuddy version must use numeric major.minor.patch format")
    return version


CANONICAL_BOOKBUDDY_VERSION = _load_canonical_version()


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    shutdown_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class SecurityConfig:
    upload_max_bytes: int = 256 * 1024 * 1024
    epub_max_members: int = 20_000
    epub_max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    epub_max_compression_ratio: float = 250.0
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1",
        "http://localhost",
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "tauri://localhost",
        "http://tauri.localhost",
    )


@dataclass(frozen=True)
class PathConfig:
    project_root: Path
    library_dir: Path
    cache_dir: Path
    log_dir: Path
    config_dir: Path
    reader_state_path: Path
    pronunciation_corpus_root: Path | None = None
    pronunciation_corpus_index: Path | None = None


@dataclass(frozen=True)
class AIConfig:
    provider: str = "gemini"
    chapter_model: str = "gemini-2.5-flash"
    dictionary_model: str = "gemini-2.5-flash"
    vision_model: str = "gemini-2.5-flash"
    max_retries: int = 20
    vision_max_retries: int = 2
    pacing_seconds: float = 1.0
    safety_retry_seconds: float = 3.0
    key_cooldown_seconds: float = 65.0
    request_timeout_seconds: float = 120.0
    api_keys: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    vision_api_keys: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    credential_source: str = "none"


@dataclass(frozen=True)
class ContractConfig:
    bookbuddy_version: str = CANONICAL_BOOKBUDDY_VERSION
    prompt_version: str = "prompt_v15_landmarks"
    normalization_version: int = 4
    cache_version: int = 13
    graph_schema_version: int = 24
    image_evidence_schema_version: str = "image_evidence_v2"
    image_parser_version: str = "image_parser_v4"
    image_local_confidence_threshold: float = 0.62
    image_ai_fallback_enabled: bool = True
    image_vision_prompt_version: str = "image_vision_evidence_v1"
    snapshot_contract_version: str = "reader_snapshot_v2"
    replay_version: str = "replay_v1"
    dictionary_response_version: str = "dictionary_response_v1"
    dictionary_wsd_confidence_threshold: float = 0.52
    dictionary_wsd_margin_threshold: float = 0.08
    csre_ambiguity_margin: float = 0.08
    dictionary_cache_size: int = 512
    dictionary_max_selection_length: int = 160
    dictionary_max_context_length: int = 4000
    reader_state_relative_path: str = "reader_state/reader.db"
    terminology_min_support: int = 2
    terminology_min_chapters: int = 2
    terminology_candidate_confidence: float = 0.45
    terminology_confirmed_confidence: float = 0.75


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    paths: PathConfig
    ai: AIConfig
    contracts: ContractConfig = field(default_factory=ContractConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    def __repr__(self) -> str:
        return (
            "AppConfig(server=" + repr(self.server)
            + ", paths=" + repr(self.paths)
            + ", ai=AIConfig(provider=" + repr(self.ai.provider)
            + ", chapter_model=" + repr(self.ai.chapter_model)
            + ", dictionary_model=" + repr(self.ai.dictionary_model)
            + ", vision_model=" + repr(self.ai.vision_model)
            + ", credentials=<redacted>), contracts=" + repr(self.contracts)
            + ", security=" + repr(self.security) + ")"
        )


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _integer(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(values.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _number(values: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(values.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc


def _path(root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _credential_pool(values: Mapping[str, str], prefix: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (key, str(value).strip())
        for key, value in sorted(values.items())
        if (key == prefix or key.startswith(prefix + "_")) and str(value).strip()
    )


def load_config(
    project_root: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    """Load defaults, then ``.env``, then explicit/process environment."""
    root = Path(project_root or os.environ.get("BOOKBUDDY_PROJECT_ROOT") or PROJECT_ROOT).resolve()
    env_path = root / ".env"
    if not env_path.is_file():
        env_path = root / "config" / ".env"
    values = _read_dotenv(env_path)
    values.update(dict(os.environ if environ is None else environ))

    config_dir = _path(root, str(values.get("BOOKBUDDY_CONFIG_DIR", "config")))
    text_keys_present = bool(_credential_pool(values, "GEMINI_API_KEY"))
    vision_keys_present = bool(_credential_pool(values, "GEMINI_VISION_API_KEY"))
    encrypted_loaded = False
    try:
        from ai_credentials import EncryptedCredentialStore
        stored = EncryptedCredentialStore(config_dir / "ai-credentials.bin").read()
        encrypted_loaded = bool(stored["api_keys"] or stored["vision_api_keys"])
        if stored["api_keys"]:
            for key in tuple(values):
                if key == "GEMINI_API_KEY" or key.startswith("GEMINI_API_KEY_"):
                    values.pop(key)
            for index, secret in enumerate(stored["api_keys"], 1):
                values[f"GEMINI_API_KEY_ENCRYPTED_{index}"] = secret
        if stored["vision_api_keys"]:
            for key in tuple(values):
                if key == "GEMINI_VISION_API_KEY" or key.startswith("GEMINI_VISION_API_KEY_"):
                    values.pop(key)
            for index, secret in enumerate(stored["vision_api_keys"], 1):
                values[f"GEMINI_VISION_API_KEY_ENCRYPTED_{index}"] = secret
    except (OSError, ValueError, RuntimeError):
        encrypted_loaded = False

    host = str(values.get("BOOKBUDDY_HOST", "127.0.0.1")).strip()
    port = _integer(values, "BOOKBUDDY_PORT", 8000)
    log_level = str(values.get("BOOKBUDDY_LOG_LEVEL", "INFO")).strip().upper()
    shutdown_timeout = _number(values, "BOOKBUDDY_SHUTDOWN_TIMEOUT_SECONDS", 30.0)
    if not host:
        raise ValueError("BOOKBUDDY_HOST must not be empty")
    if not 1 <= port <= 65535:
        raise ValueError("BOOKBUDDY_PORT must be between 1 and 65535")
    if shutdown_timeout <= 0:
        raise ValueError("BOOKBUDDY_SHUTDOWN_TIMEOUT_SECONDS must be positive")

    upload_max = _integer(values, "BOOKBUDDY_UPLOAD_MAX_BYTES", 256 * 1024 * 1024)
    epub_members = _integer(values, "BOOKBUDDY_EPUB_MAX_MEMBERS", 20_000)
    epub_uncompressed = _integer(values, "BOOKBUDDY_EPUB_MAX_UNCOMPRESSED_BYTES", 2 * 1024 * 1024 * 1024)
    epub_ratio = _number(values, "BOOKBUDDY_EPUB_MAX_COMPRESSION_RATIO", 250.0)
    if min(upload_max, epub_members, epub_uncompressed) < 1 or epub_ratio <= 1:
        raise ValueError("EPUB security limits must be positive")
    cors_value = str(values.get("BOOKBUDDY_CORS_ORIGINS", "")).strip()
    cors_origins = tuple(item.strip() for item in cors_value.split(",") if item.strip()) or SecurityConfig().cors_origins

    provider = str(values.get("AI_PROVIDER", "gemini")).strip().lower()
    if provider not in {"gemini"}:
        raise ValueError(f"Unsupported AI_PROVIDER: {provider}")
    max_retries = _integer(values, "AI_MAX_RETRIES", 20)
    vision_max_retries = _integer(values, "AI_VISION_MAX_RETRIES", 2)
    pacing = _number(values, "AI_PACING_SECONDS", 1.0)
    safety_retry = _number(values, "AI_SAFETY_RETRY_SECONDS", 3.0)
    cooldown = _number(values, "AI_KEY_COOLDOWN_SECONDS", 65.0)
    request_timeout = _number(values, "AI_REQUEST_TIMEOUT_SECONDS", 120.0)
    if max_retries < 1 or vision_max_retries < 1:
        raise ValueError("AI retry counts must be at least 1")
    if min(pacing, safety_retry, cooldown, request_timeout) < 0 or request_timeout == 0:
        raise ValueError("AI timing settings must be non-negative and timeout must be positive")

    contracts = ContractConfig()
    library = _path(root, str(values.get("BOOKBUDDY_LIBRARY_DIR", "library")))
    cache = _path(root, str(values.get("BOOKBUDDY_CACHE_DIR", ".cache")))
    log_dir = _path(root, str(values.get("BOOKBUDDY_LOG_DIR", "logs")))
    reader_state = _path(library, str(values.get("BOOKBUDDY_READER_STATE_PATH", contracts.reader_state_relative_path)))
    corpus_root_value = str(values.get("PRONUNCIATION_CORPUS_ROOT", "")).strip()
    corpus_index_value = str(values.get("PRONUNCIATION_CORPUS_INDEX", "")).strip()
    api_key_pool = _credential_pool(values, "GEMINI_API_KEY")
    vision_key_pool = _credential_pool(values, "GEMINI_VISION_API_KEY")
    if not encrypted_loaded and (api_key_pool or vision_key_pool):
        try:
            from ai_credentials import EncryptedCredentialStore
            EncryptedCredentialStore(config_dir / "ai-credentials.bin").write(
                [secret for _, secret in api_key_pool],
                [secret for _, secret in vision_key_pool],
            )
            encrypted_loaded = True
        except (OSError, RuntimeError):
            pass

    return AppConfig(
        server=ServerConfig(host, port, log_level, shutdown_timeout),
        paths=PathConfig(
            project_root=root,
            library_dir=library,
            cache_dir=cache,
            log_dir=log_dir,
            config_dir=config_dir,
            reader_state_path=reader_state,
            pronunciation_corpus_root=_path(root, corpus_root_value) if corpus_root_value else None,
            pronunciation_corpus_index=_path(root, corpus_index_value) if corpus_index_value else None,
        ),
        ai=AIConfig(
            provider=provider,
            chapter_model=str(values.get("AI_CHAPTER_MODEL", values.get("GEMINI_MODEL_NAME", "gemini-2.5-flash"))),
            dictionary_model=str(values.get("AI_DICTIONARY_MODEL", values.get("GEMINI_MODEL_NAME", "gemini-2.5-flash"))),
            vision_model=str(values.get("AI_VISION_MODEL", values.get("GEMINI_MODEL_NAME", "gemini-2.5-flash"))),
            max_retries=max_retries,
            vision_max_retries=vision_max_retries,
            pacing_seconds=pacing,
            safety_retry_seconds=safety_retry,
            key_cooldown_seconds=cooldown,
            request_timeout_seconds=request_timeout,
            api_keys=api_key_pool,
            vision_api_keys=vision_key_pool,
            credential_source=("encrypted" if encrypted_loaded else "environment" if text_keys_present or vision_keys_present else "none"),
        ),
        contracts=contracts,
        security=SecurityConfig(upload_max, epub_members, epub_uncompressed, epub_ratio, cors_origins),
    )


DEFAULT_CONFIG = load_config()

# Compatibility views. New startup/service code consumes AppConfig directly.
BOOKBUDDY_VERSION = DEFAULT_CONFIG.contracts.bookbuddy_version
AI_CHAPTER_MODEL_NAME = DEFAULT_CONFIG.ai.chapter_model
GEMINI_MODEL_NAME = AI_CHAPTER_MODEL_NAME  # developer-tool compatibility
PROMPT_VERSION = DEFAULT_CONFIG.contracts.prompt_version
NORMALIZATION_VERSION = DEFAULT_CONFIG.contracts.normalization_version
CACHE_VERSION = DEFAULT_CONFIG.contracts.cache_version
GRAPH_SCHEMA_VERSION = DEFAULT_CONFIG.contracts.graph_schema_version
IMAGE_EVIDENCE_SCHEMA_VERSION = DEFAULT_CONFIG.contracts.image_evidence_schema_version
IMAGE_PARSER_VERSION = DEFAULT_CONFIG.contracts.image_parser_version
IMAGE_LOCAL_CONFIDENCE_THRESHOLD = DEFAULT_CONFIG.contracts.image_local_confidence_threshold
IMAGE_GEMINI_FALLBACK_ENABLED = DEFAULT_CONFIG.contracts.image_ai_fallback_enabled
IMAGE_GEMINI_FALLBACK_MODEL = DEFAULT_CONFIG.ai.vision_model
IMAGE_GEMINI_FALLBACK_MAX_RETRIES = DEFAULT_CONFIG.ai.vision_max_retries
IMAGE_GEMINI_VISION_PROMPT_VERSION = DEFAULT_CONFIG.contracts.image_vision_prompt_version
SNAPSHOT_CONTRACT_VERSION = DEFAULT_CONFIG.contracts.snapshot_contract_version
REPLAY_VERSION = DEFAULT_CONFIG.contracts.replay_version
DICTIONARY_RESPONSE_VERSION = DEFAULT_CONFIG.contracts.dictionary_response_version
DICTIONARY_WSD_CONFIDENCE_THRESHOLD = DEFAULT_CONFIG.contracts.dictionary_wsd_confidence_threshold
DICTIONARY_WSD_MARGIN_THRESHOLD = DEFAULT_CONFIG.contracts.dictionary_wsd_margin_threshold
CSRE_AMBIGUITY_MARGIN = DEFAULT_CONFIG.contracts.csre_ambiguity_margin
DICTIONARY_CACHE_SIZE = DEFAULT_CONFIG.contracts.dictionary_cache_size
DICTIONARY_MAX_SELECTION_LENGTH = DEFAULT_CONFIG.contracts.dictionary_max_selection_length
DICTIONARY_MAX_CONTEXT_LENGTH = DEFAULT_CONFIG.contracts.dictionary_max_context_length
TERMINOLOGY_MIN_SUPPORT = DEFAULT_CONFIG.contracts.terminology_min_support
TERMINOLOGY_MIN_CHAPTERS = DEFAULT_CONFIG.contracts.terminology_min_chapters
TERMINOLOGY_CANDIDATE_CONFIDENCE = DEFAULT_CONFIG.contracts.terminology_candidate_confidence
TERMINOLOGY_CONFIRMED_CONFIDENCE = DEFAULT_CONFIG.contracts.terminology_confirmed_confidence
PRONUNCIATION_CORPUS_ROOT = str(DEFAULT_CONFIG.paths.pronunciation_corpus_root or "")
PRONUNCIATION_CORPUS_INDEX = str(DEFAULT_CONFIG.paths.pronunciation_corpus_index or "")
READER_STATE_PATH = DEFAULT_CONFIG.contracts.reader_state_relative_path
MAX_EXTRACTION_RETRIES = DEFAULT_CONFIG.ai.max_retries
API_PACING_SECONDS = DEFAULT_CONFIG.ai.pacing_seconds
SAFETY_RETRY_SECONDS = DEFAULT_CONFIG.ai.safety_retry_seconds
DEFAULT_KEY_COOLDOWN_SECONDS = DEFAULT_CONFIG.ai.key_cooldown_seconds

RESOLVER_VERSIONS = {
    "identity": "identity_pipeline_v1", "ontology": "ontology_resolution_v1",
    "life_status": "life_status_resolver_v1", "landmarks": "landmark_resolution_v1",
    "relationships": "relationship_resolution_v1", "reference_quarantine": "reference_quarantine_v1",
    "language_observations": "language_observations_v1", "image_evidence": "image_evidence_adapter_v2",
    "terminology": "terminology_resolver_v1",
}
RESOLVER_DEPENDENCIES = {
    "identity": (), "ontology": ("identity",), "life_status": ("identity",), "landmarks": ("identity",),
    "relationships": ("identity", "ontology", "life_status"), "reference_quarantine": (),
    "language_observations": ("identity", "ontology"), "image_evidence": (),
    "terminology": ("identity", "ontology", "reference_quarantine", "language_observations", "image_evidence"),
}
WSD_CONTEXT_CUES = {
    "emotion": {"smile", "smiled", "unfriendly", "affection", "affectionate", "warmth", "emotion", "impersonal"},
    "physical_temperature": {"water", "ice", "heat", "room", "beer", "drink", "temperature", "coldness"},
}

# Existing domain-policy constants retained as compatibility views.
ACTIVE_ENTITY_LIMIT = 40
REGEX_CACHE_SIZE = 1000
PREVIOUS_CONTEXT_CHAPTERS = 3
ALIAS_CANDIDATE_SUPPORT = 1
ALIAS_PROBABLE_SUPPORT = 2
ALIAS_ACCEPTED_SUPPORT = 4
ALIAS_BASE_CONFIDENCE = 0.35
ALIAS_LOWERCASE_PENALTY = 0.2
ALIAS_COMMON_NOUN_PENALTY = 0.25
ALIAS_TITLE_ONLY_PENALTY = 0.15
ALIAS_SUPPORT_CONFIDENCE_BOOST = 0.18
ALIAS_ACCEPTED_CONFIDENCE = 0.85
ENTITY_TYPE_CHANGE_SUPPORT = 3
ENTITY_TYPE_CHANGE_CONFIDENCE = 0.75
ENTITY_BASE_CONFIDENCE = 0.55
ENTITY_SUPPORT_CONFIDENCE_BOOST = 0.1
MEMORY_CARD_LIMIT = 12
MEMORY_CARD_RELATIONSHIP_LIMIT = 4
MEMORY_CARD_RECENT_EVENT_LIMIT = 3
EVENT_CONTEXT_LIMIT = 8
SEARCH_TERMS_LONG_TEXT_TOKEN_LIMIT = 180
SEARCH_TERMS_LONG_TEXT_TERM_LIMIT = 900
RELATIONSHIP_BASE_CONFIDENCE = 0.7
RELATIONSHIP_CONFIRMED_CONFIDENCE = 0.6
INHERITED_GRAPH_CONFIDENCE = 0.55
LOCAL_GRAPH_CONFIDENCE = 1.0
CONFIDENCE_DECAY_FACTOR = 0.96
CONFIDENCE_DECAY_AFTER_CHAPTERS = 4
LIFE_STATUS_DECAY_FACTOR = 0.995
LIFE_STATUS_DECAY_AFTER_CHAPTERS = 25
ALIAS_REVIEW_CONFIDENCE = 0.25
ALIAS_EXPIRED_CONFIDENCE = 0.12
ENTITY_REVIEW_CONFIDENCE = 0.3
RELATIONSHIP_CONTRADICTION_DELTA = 8
