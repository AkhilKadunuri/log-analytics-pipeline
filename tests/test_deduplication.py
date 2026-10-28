from __future__ import annotations

from log_analytics.deduplication import deduplicate_batch
from log_analytics.models import NormalizedEvent


def _event(event_id: str, message: str = "ok", line: int = 1) -> NormalizedEvent:
    return NormalizedEvent(
        event_id,
        "2026-10-28T09:30:00+00:00",
        "api",
        "INFO",
        message,
        None,
        200,
        1.0,
        "logs.jsonl",
        line,
        "run",
        "2026-10-28T09:31:00+00:00",
    )


def test_identical_event_id_in_one_batch_is_duplicate():
    result = deduplicate_batch([_event("id", line=1), _event("id", line=2)])
    assert len(result.unique_events) == 1
    assert result.duplicate_count == 1
    assert result.conflicts == []


def test_same_id_with_conflicting_payload_is_not_silently_collapsed():
    result = deduplicate_batch([_event("id"), _event("id", "different", 2)])
    assert len(result.unique_events) == 1
    assert result.duplicate_count == 0
    assert len(result.conflicts) == 1


def test_legitimate_repeated_messages_with_different_ids_are_preserved():
    result = deduplicate_batch([_event("one"), _event("two", line=2)])
    assert len(result.unique_events) == 2
    assert result.duplicate_count == 0
