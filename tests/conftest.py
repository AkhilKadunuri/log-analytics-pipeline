from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def make_json_record(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "event_id": "test-001",
        "timestamp": "2026-10-28T09:30:00Z",
        "service_name": "test-service",
        "severity": "INFO",
        "message": "request completed",
        "request_id": None,
        "status_code": None,
        "latency_ms": None,
    }
    fields.update(overrides)
    return fields


def write_jsonl(path: Path, rows: list[dict[str, object] | str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as target:
        for row in rows:
            target.write(row if isinstance(row, str) else json.dumps(row, ensure_ascii=False))
            target.write("\n")
    return path
