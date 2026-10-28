"""Shared data structures used by the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    raw_record: str
    source_file: str
    source_line: int
    fields: dict[str, Any] | None
    parse_error: str | None = None


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    timestamp_utc: str
    service_name: str
    severity: str
    message: str
    request_id: str | None
    status_code: int | None
    latency_ms: float | None
    source_file: str
    source_line: int
    run_id: str
    ingested_at_utc: str


@dataclass(frozen=True)
class Rejection:
    source_file: str
    source_line: int
    raw_record: str
    rejection_reason: str


@dataclass(frozen=True)
class BatchDeduplication:
    unique_events: list[NormalizedEvent]
    duplicate_count: int
    conflicts: list[tuple[NormalizedEvent, str]]
