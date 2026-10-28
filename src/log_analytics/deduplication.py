"""Deterministic in-batch duplicate classification."""

from __future__ import annotations

from log_analytics.models import BatchDeduplication, NormalizedEvent
from log_analytics.transformer import event_payload


def deduplicate_batch(events: list[NormalizedEvent]) -> BatchDeduplication:
    """Keep the first event ID, count identical repeats, and expose conflicts."""
    first_by_id: dict[str, NormalizedEvent] = {}
    unique: list[NormalizedEvent] = []
    conflicts: list[tuple[NormalizedEvent, str]] = []
    duplicates = 0

    for event in events:
        previous = first_by_id.get(event.event_id)
        if previous is None:
            first_by_id[event.event_id] = event
            unique.append(event)
        elif event_payload(previous) == event_payload(event):
            duplicates += 1
        else:
            conflicts.append((event, f"event_id {event.event_id!r} has conflicting payloads in this batch"))
    return BatchDeduplication(unique, duplicates, conflicts)
