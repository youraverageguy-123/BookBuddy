BOOKBUDDY_VERSION = "0.17.0"

GEMINI_MODEL_NAME = "gemini-2.5-flash"
PROMPT_VERSION = "prompt_v15_landmarks"
NORMALIZATION_VERSION = 4
CACHE_VERSION = 13
GRAPH_SCHEMA_VERSION = 23

# Image evidence is optional at runtime.  The chapter evidence contract stays
# available even when local OCR dependencies are not installed.
IMAGE_EVIDENCE_SCHEMA_VERSION = "image_evidence_v2"
IMAGE_PARSER_VERSION = "image_parser_v4"
IMAGE_LOCAL_CONFIDENCE_THRESHOLD = 0.62
# Gemini Vision is a conditional second pass. Local parsing always runs first.
# A caller must explicitly authorize its API usage with
# ``use_gemini_vision=True`` before a Vision request can be made.
IMAGE_GEMINI_FALLBACK_ENABLED = True
IMAGE_GEMINI_FALLBACK_MODEL = GEMINI_MODEL_NAME
IMAGE_GEMINI_FALLBACK_MAX_RETRIES = 2
IMAGE_GEMINI_VISION_PROMPT_VERSION = "image_vision_evidence_v1"

# Public derived-state contracts. Evidence remains versioned independently and
# checkpoints are operational metadata only.
SNAPSHOT_CONTRACT_VERSION = "reader_snapshot_v2"
REPLAY_VERSION = "replay_v1"

# Stable boundary versions used by chapter checkpoints. Bump the relevant
# value when changing resolver semantics so replay invalidates derived state.
RESOLVER_VERSIONS = {
    "identity": "identity_pipeline_v1",
    "ontology": "ontology_resolution_v1",
    "life_status": "life_status_resolver_v1",
    "landmarks": "landmark_resolution_v1",
    "relationships": "relationship_resolution_v1",
    "reference_quarantine": "reference_quarantine_v1",
    "language_observations": "language_observations_v1",
    "image_evidence": "image_evidence_adapter_v2",
}

# Each entry lists upstream resolver contracts. Downstream invalidation is
# computed from this declaration rather than inferred from call order.
RESOLVER_DEPENDENCIES = {
    "identity": (),
    "ontology": ("identity",),
    "life_status": ("identity",),
    "landmarks": ("identity",),
    "relationships": ("identity", "ontology", "life_status"),
    "reference_quarantine": (),
    "language_observations": ("identity", "ontology"),
    "image_evidence": (),
}

ACTIVE_ENTITY_LIMIT = 40
REGEX_CACHE_SIZE = 1000

MAX_EXTRACTION_RETRIES = 20
API_PACING_SECONDS = 1
SAFETY_RETRY_SECONDS = 3
DEFAULT_KEY_COOLDOWN_SECONDS = 65

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
