"""Reproducible service, time-window, latency, and quality summaries."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SEVERITIES = ("DEBUG", "INFO", "WARNING", "ERROR", "FATAL")


def percentile(values: list[float], quantile: float) -> float | None:
    """Inclusive, linearly interpolated percentile (position=(n-1)*q)."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _window_start(timestamp: str, window: str) -> str:
    instant = datetime.fromisoformat(timestamp).astimezone(UTC)
    if window == "hour":
        instant = instant.replace(minute=0, second=0, microsecond=0)
    elif window == "day":
        instant = instant.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError("window must be 'hour' or 'day'")
    return instant.isoformat()


def build_analytics(events: list[dict[str, Any]], window: str) -> dict[str, Any]:
    service_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bucket_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    severity_counts: Counter[str] = Counter()
    for event in events:
        service_groups[event["service_name"]].append(event)
        bucket = _window_start(event["timestamp_utc"], window)
        bucket_groups[(bucket, event["service_name"])].append(event)
        severity_counts[event["severity"]] += 1

    service_summary: list[dict[str, Any]] = []
    latency_summary: list[dict[str, Any]] = []
    for service, group in sorted(service_groups.items()):
        errors = sum(row["severity"] == "ERROR" for row in group)
        fatals = sum(row["severity"] == "FATAL" for row in group)
        http_4xx = sum(
            row["status_code"] is not None and 400 <= row["status_code"] <= 499
            for row in group
        )
        http_5xx = sum(
            row["status_code"] is not None and 500 <= row["status_code"] <= 599
            for row in group
        )
        latency_values = [float(row["latency_ms"]) for row in group if row["latency_ms"] is not None]
        total = len(group)
        service_summary.append(
            {
                "service_name": service,
                "total_events": total,
                "error_count": errors,
                "fatal_count": fatals,
                "combined_error_count": errors + fatals,
                "error_rate_pct": round(100 * (errors + fatals) / total, 4) if total else 0.0,
                "http_4xx_count": http_4xx,
                "http_5xx_count": http_5xx,
                "http_failure_rate_pct": round(100 * (http_4xx + http_5xx) / total, 4)
                if total
                else 0.0,
                "valid_latency_count": len(latency_values),
            }
        )
        latency_summary.append(
            {
                "service_name": service,
                "latency_count": len(latency_values),
                "missing_latency_count": total - len(latency_values),
                "min_latency_ms": round(min(latency_values), 4) if latency_values else None,
                "mean_latency_ms": round(sum(latency_values) / len(latency_values), 4)
                if latency_values
                else None,
                "p50_latency_ms": _round_percentile(latency_values, 0.50),
                "p95_latency_ms": _round_percentile(latency_values, 0.95),
                "p99_latency_ms": _round_percentile(latency_values, 0.99),
                "max_latency_ms": round(max(latency_values), 4) if latency_values else None,
            }
        )

    error_summary: list[dict[str, Any]] = []
    for (bucket, service), group in sorted(bucket_groups.items()):
        error_count = sum(row["severity"] in {"ERROR", "FATAL"} for row in group)
        total = len(group)
        error_summary.append(
            {
                "window_start_utc": bucket,
                "service_name": service,
                "total_events": total,
                "error_count": error_count,
                "error_rate_pct": round(100 * error_count / total, 4) if total else 0.0,
            }
        )

    return {
        "service_summary": service_summary,
        "latency_summary": latency_summary,
        "error_summary": error_summary,
        "severity_distribution": {severity: severity_counts[severity] for severity in SEVERITIES},
        "event_count": len(events),
    }


def _round_percentile(values: list[float], quantile: float) -> float | None:
    value = percentile(values, quantile)
    return round(value, 4) if value is not None else None


def write_outputs(
    output_dir: Path,
    analytics: dict[str, Any],
    events: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
    run: dict[str, Any],
    reconciliation: dict[str, Any],
    window: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "service_summary.csv",
        analytics["service_summary"],
        (
            "service_name",
            "total_events",
            "error_count",
            "fatal_count",
            "combined_error_count",
            "error_rate_pct",
            "http_4xx_count",
            "http_5xx_count",
            "http_failure_rate_pct",
            "valid_latency_count",
        ),
    )
    _write_csv(
        output_dir / "latency_summary.csv",
        analytics["latency_summary"],
        (
            "service_name",
            "latency_count",
            "missing_latency_count",
            "min_latency_ms",
            "mean_latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "max_latency_ms",
        ),
    )
    _write_csv(
        output_dir / "error_summary.csv",
        analytics["error_summary"],
        ("window_start_utc", "service_name", "total_events", "error_count", "error_rate_pct"),
    )
    rejection_reasons = Counter(row["rejection_reason"] for row in rejections)
    quality_report = {
        "run_id": run["run_id"],
        "run_status": run["status"],
        "counts": {
            key: run[key]
            for key in (
                "input_count",
                "parsed_count",
                "parse_error_count",
                "accepted_count",
                "rejected_count",
                "duplicate_count",
                "inserted_count",
            )
        },
        "stored_event_count": len(events),
        "severity_distribution": analytics["severity_distribution"],
        "missing_optional_values": {
            "request_id": sum(row["request_id"] is None for row in events),
            "status_code": sum(row["status_code"] is None for row in events),
            "latency_ms": sum(row["latency_ms"] is None for row in events),
        },
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
        "time_window_utc": window,
        "percentile_method": "inclusive linear interpolation at position (n - 1) * q",
        "reconciliation_passed": reconciliation["passed"],
    }
    _write_json(output_dir / "quality_report.json", quality_report)
    _write_json(output_dir / "reconciliation_report.json", reconciliation)


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, content: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as target:
        json.dump(content, target, indent=2, ensure_ascii=False, sort_keys=True)
        target.write("\n")
