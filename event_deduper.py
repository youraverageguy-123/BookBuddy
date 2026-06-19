def add_event_with_cluster(
    db,
    chapter: int,
    summary: str,
    event_order: int,
    event_type: str = "plot",
    confidence: float = 0.7,
    source_payload: dict | None = None,
) -> int | None:
    event_id = db.add_event(
        chapter=chapter,
        summary=summary,
        event_order=event_order,
        event_type=event_type,
        confidence=confidence,
        source_payload=source_payload,
    )
    if event_id:
        db.add_event_cluster_member(event_id, summary, confidence=confidence)
    return event_id
