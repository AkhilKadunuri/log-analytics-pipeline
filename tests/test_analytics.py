from __future__ import annotations

from log_analytics.analytics import build_analytics, percentile


def _row(event_id, service, severity, timestamp, latency, status):
    return {
        "event_id": event_id,
        "service_name": service,
        "severity": severity,
        "timestamp_utc": timestamp,
        "latency_ms": latency,
        "status_code": status,
        "request_id": None,
    }


def test_known_percentile_values_use_linear_interpolation():
    assert percentile([100.0, 300.0], 0.5) == 200.0
    assert percentile([100.0, 300.0], 0.95) == 290.0
    assert percentile([], 0.95) is None


def test_severity_and_http_failure_rates_are_separate():
    rows = [
        _row("1", "api", "ERROR", "2026-10-28T09:15:00+00:00", 10.0, 200),
        _row("2", "api", "INFO", "2026-10-28T09:30:00+00:00", None, 500),
        _row("3", "api", "FATAL", "2026-10-28T10:00:00+00:00", 30.0, None),
    ]
    result = build_analytics(rows, "hour")
    service = result["service_summary"][0]
    assert service["error_rate_pct"] == 66.6667
    assert service["http_failure_rate_pct"] == 33.3333
    assert service["valid_latency_count"] == 2
    assert result["latency_summary"][0]["missing_latency_count"] == 1
    assert [row["window_start_utc"] for row in result["error_summary"]] == [
        "2026-10-28T09:00:00+00:00",
        "2026-10-28T10:00:00+00:00",
    ]


def test_empty_analytics_has_stable_empty_outputs():
    result = build_analytics([], "day")
    assert result["event_count"] == 0
    assert result["service_summary"] == []
    assert result["latency_summary"] == []
    assert result["error_summary"] == []
    assert result["severity_distribution"]["ERROR"] == 0
