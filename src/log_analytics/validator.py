"""Schema validation and severity/timestamp normalization."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

from log_analytics.models import NormalizedEvent, SourceRecord

ALLOWED_FIELDS = {
    "event_id",
    "timestamp",
    "service_name",
    "severity",
    "message",
    "request_id",
    "status_code",
    "latency_ms",
}
SEVERITY_ALIASES = {
    "TRACE": "DEBUG",
    "WARN": "WARNING",
    "CRITICAL": "FATAL",
}
SEVERITIES = {"DEBUG", "INFO", "WARNING", "ERROR", "FATAL"}


class RecordValidationError(ValueError):
    """Raised when a parsed record violates the input contract."""


def normalize_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordValidationError("timestamp must be a non-empty string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RecordValidationError("timestamp is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecordValidationError("timestamp must include a timezone or UTC offset")
    return parsed.astimezone(UTC).isoformat()


def normalize_severity(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordValidationError("severity must be a non-empty string")
    severity = value.strip().upper()
    severity = SEVERITY_ALIASES.get(severity, severity)
    if severity not in SEVERITIES:
        raise RecordValidationError(f"unknown severity: {value!r}")
    return severity


def _optional_string(fields: dict[str, Any], name: str) -> str | None:
    value = fields.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordValidationError(f"{name} must be a string or null")
    return value.strip() or None


def _optional_status_code(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise RecordValidationError("status_code must be an integer from 100 to 599")
    if isinstance(value, int):
        status = value
    else:
        raise RecordValidationError("status_code must be an integer from 100 to 599")
    if not 100 <= status <= 599:
        raise RecordValidationError("status_code must be between 100 and 599")
    return status


def _optional_latency(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordValidationError("latency_ms must be a finite non-negative number")
    latency = float(value)
    if not math.isfinite(latency) or latency < 0:
        raise RecordValidationError("latency_ms must be finite and non-negative")
    return latency


def _fallback_event_id(fields: dict[str, Any], record: SourceRecord) -> str:
    identity = {
        "source_file": record.source_file,
        "source_line": record.source_line,
        "fields": {key: fields.get(key) for key in sorted(ALLOWED_FIELDS - {"event_id"})},
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_and_normalize(
    record: SourceRecord,
    run_id: str,
    ingested_at_utc: str,
) -> NormalizedEvent:
    """Convert a parsed record to the normalized target model."""
    fields = record.fields
    if fields is None:
        raise RecordValidationError(record.parse_error or "record could not be parsed")

    unknown = sorted(set(fields) - ALLOWED_FIELDS)
    if unknown:
        raise RecordValidationError(f"unexpected fields: {', '.join(unknown)}")

    timestamp = normalize_timestamp(fields.get("timestamp"))
    severity = normalize_severity(fields.get("severity"))
    service_value = fields.get("service_name")
    if not isinstance(service_value, str) or not service_value.strip():
        raise RecordValidationError("service_name must be a non-empty string")
    message_value = fields.get("message")
    if not isinstance(message_value, str):
        raise RecordValidationError("message must be a string")

    supplied_id = fields.get("event_id")
    if supplied_id is None:
        event_id = _fallback_event_id(fields, record)
    elif not isinstance(supplied_id, str) or not supplied_id.strip():
        raise RecordValidationError("event_id must be a non-empty string when provided")
    else:
        event_id = supplied_id.strip()

    return NormalizedEvent(
        event_id=event_id,
        timestamp_utc=timestamp,
        service_name=service_value.strip(),
        severity=severity,
        message=message_value,
        request_id=_optional_string(fields, "request_id"),
        status_code=_optional_status_code(fields.get("status_code")),
        latency_ms=_optional_latency(fields.get("latency_ms")),
        source_file=record.source_file,
        source_line=record.source_line,
        run_id=run_id,
        ingested_at_utc=ingested_at_utc,
    )
