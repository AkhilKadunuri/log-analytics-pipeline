"""Small transformation helpers kept separate from parsing and validation."""

from __future__ import annotations

from log_analytics.models import NormalizedEvent


def event_payload(event: NormalizedEvent) -> tuple[object, ...]:
    """Return identity-relevant data, excluding ingestion and source metadata."""
    return (
        event.timestamp_utc,
        event.service_name,
        event.severity,
        event.message,
        event.request_id,
        event.status_code,
        event.latency_ms,
    )
