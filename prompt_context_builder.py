from context_filter import filter_context_block


def build_prompt_context(
    db,
    chapter_text: str,
    previous_events_cache: dict[int, list[dict | str]] | None,
    chapter_index: int,
    previous_context_chapters: int,
) -> dict:
    chapter_text_lower = chapter_text.lower()
    cached_event_lines = []
    if previous_events_cache:
        start = max(0, chapter_index - previous_context_chapters)
        for prev_idx in range(start, chapter_index):
            for event in previous_events_cache.get(prev_idx, []):
                summary = event.get("summary", event.get("event", "")) if isinstance(event, dict) else event
                if summary:
                    cached_event_lines.append(f"- ch {prev_idx}: {summary}")

    return {
        "known_chars": db.get_known_entities_text("INDIVIDUAL", chapter_text_lower),
        "known_groups": db.get_known_entities_text("GROUP", chapter_text_lower),
        "known_locs": db.get_known_entities_text("LOCATION", chapter_text_lower),
        "memory_cards": filter_context_block(db.get_memory_cards_text(chapter_text_lower), max_lines=80),
        "relationship_context": filter_context_block(db.get_relationship_context_text(chapter_text_lower), max_lines=60),
        "social_web_context": filter_context_block(db.get_social_relationship_context_text(chapter_text_lower), max_lines=60),
        "life_status_context": filter_context_block(db.get_life_status_context_text(chapter_text_lower), max_lines=60),
        "prior_event_context": filter_context_block(
            db.get_relevant_events_text(chapter_text_lower, chapter_index=chapter_index),
            max_lines=40,
        ),
        "previous_cache_context": "\n".join(cached_event_lines) if cached_event_lines else "No cached prior chapter events available.",
    }
