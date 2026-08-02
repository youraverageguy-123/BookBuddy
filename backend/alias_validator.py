from dataclasses import dataclass
from context_filter import quote_is_dialogue_fragment

TRUE_ALIAS = "alias_candidate"
TITLE_LINK = "title_link"
REJECTED = "rejected"
NEEDS_REVIEW = "needs_review"
CONFLICT = "conflict"
_TITLE_WORDS = {
    "baron", "captain", "chief", "commander", "count", "countess", "duke",
    "duchess", "emperor", "empress", "governor", "king", "lady", "lord",
    "magistrate", "major", "minister", "officer", "president", "prince",
    "princess", "queen", "senator", "sir", "warden",
}
_WEAK_ROLE_WORDS = {
    "aunt", "boy", "brother", "child", "cousin", "daughter", "father",
    "friend", "girl", "guard", "husband", "man", "mother", "servant",
    "sister", "son", "uncle", "wife", "woman",
}

@dataclass(frozen=True)
class AliasValidationResult:
    status: str
    confidence_delta: float = 0.0
    reason: str = ""

def _tokens(value: str) -> list[str]:
    return [token for token in str(value or "").lower().replace("-", " ").split() if token]

def _is_title_word(token: str) -> bool:
    token = str(token or "").lower()
    if token in _TITLE_WORDS:
        return True
    return token.startswith("arch") and token[4:] in _TITLE_WORDS

def _is_possessive_phrase(value: str) -> bool:
    lowered = str(value or "").lower()
    return "'s " in lowered or lowered.endswith("'s") or "’s " in lowered or lowered.endswith("’s")

def _looks_like_title(value: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    tokens = _tokens(stripped)
    if stripped.lower().startswith("the ") and 1 < len(tokens) <= 4:
        return True
    if any(_is_title_word(token) for token in tokens):
        return True
    if len(tokens) <= 3 and any(part[:1].isupper() for part in stripped.split()):
        compact = stripped.replace(" ", "")
        return any(_is_title_word(word) for word in _tokens(compact))
    return False

def _looks_like_weak_role(value: str) -> bool:
    tokens = _tokens(value)
    return bool(tokens) and all(token in _WEAK_ROLE_WORDS or token in {"the", "of"} for token in tokens)

def validate_alias(
    db,
    entity_id: int,
    canonical_name: str,
    alias_name: str,
    chapter_idx: int,
    evidence: str = "",
) -> AliasValidationResult:
    alias_key = db.normalize_alias_key(alias_name)
    canonical_key = db.normalize_alias_key(canonical_name)
    if not alias_key:
        return AliasValidationResult(REJECTED, reason="empty alias")
    if alias_key == canonical_key:
        return AliasValidationResult(REJECTED, reason="self alias")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM entities WHERE lower(canonical_name) = lower(?)", (alias_name.strip(),))
        row = cursor.fetchone()
        if row and row[0] != entity_id:
            return AliasValidationResult(CONFLICT, reason="alias is another canonical entity")
        cursor.execute(
            "SELECT entity_id FROM aliases WHERE alias_key = ? AND entity_id != ? AND COALESCE(status, 'candidate') != 'rejected'",
            (alias_key, entity_id),
        )
        if cursor.fetchone():
            return AliasValidationResult(CONFLICT, reason="alias already linked to another entity")
    if _is_possessive_phrase(alias_name):
        if _looks_like_title(alias_name):
            return AliasValidationResult(TITLE_LINK, -0.1, "possessive title phrase")
        return AliasValidationResult(NEEDS_REVIEW, -0.2, "possessive or relational phrase")
    if _looks_like_weak_role(alias_name):
        return AliasValidationResult(NEEDS_REVIEW, -0.25, "bare role phrase")
    if _looks_like_title(alias_name):
        return AliasValidationResult(TITLE_LINK, -0.05, "title-like phrase")
    if quote_is_dialogue_fragment(evidence):
        return AliasValidationResult(NEEDS_REVIEW, -0.15, "weak dialogue evidence")
    return AliasValidationResult(TRUE_ALIAS)
