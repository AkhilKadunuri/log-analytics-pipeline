"""Deterministic synthetic JSONL generator for demos and benchmarks."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SERVICES = ("auth-service", "payment-service", "catalog-service", "notification-service")
SEVERITIES = ("DEBUG", "INFO", "INFO", "WARNING", "ERROR", "FATAL")
MESSAGES = {
    "DEBUG": "cache lookup completed",
    "INFO": "request completed successfully",
    "WARNING": "retrying upstream request",
    "ERROR": "request failed",
    "FATAL": "service could not recover",
}


def _valid_event(index: int, rng: random.Random) -> dict[str, Any]:
    timestamp = datetime(2026, 10, 28, tzinfo=UTC) + timedelta(
        seconds=rng.randint(0, 7 * 24 * 60 * 60)
    )
    severity = rng.choice(SEVERITIES)
    status_by_severity = {
        "DEBUG": 200,
        "INFO": 200,
        "WARNING": 429,
        "ERROR": 500,
        "FATAL": 503,
    }
    return {
        "event_id": f"evt-{index:08d}",
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "service_name": rng.choice(SERVICES),
        "severity": severity,
        "message": MESSAGES[severity],
        "request_id": f"req-{index:08d}" if rng.random() > 0.08 else None,
        "status_code": status_by_severity[severity] if rng.random() > 0.12 else None,
        "latency_ms": round(rng.lognormvariate(4.2, 0.8), 3) if rng.random() > 0.1 else None,
    }


def _invalid_line(index: int, event: dict[str, Any], invalid_kind: int) -> str:
    altered = dict(event)
    if invalid_kind == 0:
        altered.pop("service_name")
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 1:
        altered["timestamp"] = "not-a-timestamp"
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 2:
        altered["severity"] = "NOTICE"
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 3:
        altered["status_code"] = 99
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 4:
        altered["latency_ms"] = -1
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 5:
        altered["latency_ms"] = float("inf")
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 6:
        altered["surprise_field"] = "schema drift"
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 7:
        altered["timestamp"] = "2026-10-28T12:00:00"
        return json.dumps(altered, ensure_ascii=False)
    if invalid_kind == 8:
        return '{"event_id": broken-json'
    if invalid_kind == 9:
        altered["message"] = 17
        return json.dumps(altered, ensure_ascii=False)
    altered["event_id"] = ""
    return json.dumps(altered, ensure_ascii=False)


def generate_jsonl(
    output_path: Path,
    records: int,
    seed: int = 42,
    invalid_ratio: float = 0.05,
    duplicate_ratio: float = 0.02,
) -> dict[str, int]:
    """Write exactly ``records`` deterministic lines and return planned counts."""
    if records < 0:
        raise ValueError("records must be non-negative")
    if not 0 <= invalid_ratio <= 1 or not 0 <= duplicate_ratio <= 1:
        raise ValueError("ratios must be between 0 and 1")
    if invalid_ratio + duplicate_ratio > 1:
        raise ValueError("invalid_ratio + duplicate_ratio must not exceed 1")

    rng = random.Random(seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    valid_lines: list[str] = []
    counts = {"generated": 0, "planned_invalid": 0, "planned_duplicates": 0}
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for index in range(records):
            choice = rng.random()
            if choice < duplicate_ratio and valid_lines:
                line = rng.choice(valid_lines)
                counts["planned_duplicates"] += 1
            elif choice < duplicate_ratio + invalid_ratio:
                line = _invalid_line(index, _valid_event(index, rng), index % 11)
                counts["planned_invalid"] += 1
            else:
                event = _valid_event(index, rng)
                line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                valid_lines.append(line)
            output.write(line + "\n")
            counts["generated"] += 1
    return counts
