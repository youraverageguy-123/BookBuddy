import re


def normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())


def dedupe_lines(text: str, limit: int | None = None) -> str:
    seen = set()
    lines = []
    for raw_line in str(text or "").splitlines():
        line = normalize_space(raw_line)
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
        if limit and len(lines) >= limit:
            break
    return "\n".join(lines)


def is_low_value_context_line(line: str) -> bool:
    lowered = normalize_space(line).lower()
    if not lowered:
        return True
    if "status: expired" in lowered or "status: rejected" in lowered:
        return True
    if "surface_form: descriptor" in lowered or "surface_form: location_fragment" in lowered:
        return True
    return False


def filter_context_block(text: str, max_lines: int | None = None) -> str:
    kept = []
    for line in dedupe_lines(text).splitlines():
        if is_low_value_context_line(line):
            continue
        kept.append(line)
        if max_lines and len(kept) >= max_lines:
            break
    return "\n".join(kept) if kept else "No filtered context available."


def quote_is_dialogue_fragment(evidence: str) -> bool:
    stripped = normalize_space(evidence)
    if not stripped:
        return True
    quote_count = stripped.count('"') + stripped.count("'")
    if quote_count % 2 == 1:
        return True
    if re.fullmatch(r"['\"].{1,80}", stripped):
        return True
    return False
