from __future__ import annotations

from log_analytics.models import NormalizedEvent
from log_analytics.transformer import event_payload


def test_identity_payload_excludes_run_and_source_metadata():
    first = NormalizedEvent(
        "same",
        "2026-10-28T09:30:00+00:00",
        "api",
        "INFO",
        "ok",
        None,
        200,
        10.0,
        "a.jsonl",
        1,
        "run-a",
        "2026-10-28T09:31:00+00:00",
    )
    second = NormalizedEvent(
        "same",
        "2026-10-28T09:30:00+00:00",
        "api",
        "INFO",
        "ok",
        None,
        200,
        10.0,
        "b.jsonl",
        99,
        "run-b",
        "2026-10-29T00:00:00+00:00",
    )
    assert event_payload(first) == event_payload(second)
