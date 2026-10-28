from __future__ import annotations

import math

import pytest

from log_analytics.models import SourceRecord
from log_analytics.validator import RecordValidationError, normalize_severity, normalize_timestamp, validate_and_normalize
from conftest import make_json_record


def _validate(fields):
    return validate_and_normalize(
        SourceRecord("raw", "fixture.jsonl", 1, fields),
        "run-1",
        "2026-10-28T00:00:00+00:00",
    )


def test_timezone_offset_is_converted_to_utc():
    event = _validate(make_json_record(timestamp="2026-10-28T09:31:00+05:30"))
    assert event.timestamp_utc == "2026-10-28T04:01:00+00:00"


def test_naive_timestamp_is_rejected():
    with pytest.raises(RecordValidationError, match="timezone"):
        normalize_timestamp("2026-10-28T09:31:00")


@pytest.mark.parametrize(("raw", "expected"), [("WARN", "WARNING"), ("critical", "FATAL"), ("trace", "DEBUG")])
def test_severity_aliases_are_normalized(raw, expected):
    assert normalize_severity(raw) == expected


def test_unknown_severity_is_rejected():
    with pytest.raises(RecordValidationError, match="unknown severity"):
        normalize_severity("NOTICE")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        (make_json_record(service_name="  "), "service_name"),
        (make_json_record(timestamp="bad"), "timestamp"),
        (make_json_record(status_code=99), "status_code"),
        (make_json_record(status_code=200.5), "status_code"),
        (make_json_record(status_code="200"), "status_code"),
        (make_json_record(latency_ms=-0.1), "latency_ms"),
        (make_json_record(latency_ms="not numeric"), "latency_ms"),
        (make_json_record(latency_ms="1.25"), "latency_ms"),
        (make_json_record(latency_ms=math.inf), "latency_ms"),
        (make_json_record(severity="UNKNOWN"), "unknown severity"),
        (make_json_record(event_id=""), "event_id"),
        (make_json_record(surprise=True), "unexpected fields"),
    ],
)
def test_invalid_fields_are_rejected(fields, reason):
    with pytest.raises(RecordValidationError, match=reason):
        _validate(fields)


def test_null_optional_fields_are_allowed():
    event = _validate(make_json_record(request_id=None, status_code=None, latency_ms=None))
    assert event.request_id is None
    assert event.status_code is None
    assert event.latency_ms is None


def test_missing_event_id_gets_a_deterministic_fallback():
    fields = make_json_record()
    fields.pop("event_id")
    first = _validate(fields)
    second = _validate(fields)
    assert first.event_id == second.event_id
    assert first.event_id.startswith("sha256:")


@pytest.mark.parametrize("field", ["service_name", "timestamp"])
def test_missing_required_field_is_rejected(field):
    fields = make_json_record()
    fields.pop(field)
    with pytest.raises(RecordValidationError, match=field):
        _validate(fields)
