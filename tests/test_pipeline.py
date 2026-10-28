from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from log_analytics.config import PipelineConfig
from log_analytics.pipeline import run_pipeline
from conftest import PROJECT_ROOT, write_jsonl


def test_reference_fixture_has_expected_known_answers(tmp_path: Path):
    expected = json.loads(
        (PROJECT_ROOT / "data/expected/reference_expected.json").read_text(encoding="utf-8")
    )
    result = run_pipeline(
        [PROJECT_ROOT / "data/expected/reference_logs.jsonl"],
        PipelineConfig(tmp_path / "reference.db", tmp_path / "reference-output"),
    )
    assert result["status"] == "succeeded_with_rejections"
    assert {key: result[key] for key in expected["counts"]} == expected["counts"]

    service_rows = list(
        csv.DictReader((tmp_path / "reference-output/service_summary.csv").open(encoding="utf-8"))
    )
    assert len(service_rows) == 2
    assert service_rows[0]["service_name"] == expected["service_summary"][0]["service_name"]
    assert float(service_rows[1]["error_rate_pct"]) == expected["service_summary"][1]["error_rate_pct"]
    latency_rows = list(
        csv.DictReader((tmp_path / "reference-output/latency_summary.csv").open(encoding="utf-8"))
    )
    payment = next(row for row in latency_rows if row["service_name"] == "payment-service")
    assert float(payment["p95_latency_ms"]) == expected["payment_latency"]["p95_latency_ms"]
    report = json.loads(
        (tmp_path / "reference-output/reconciliation_report.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is True


def test_mixed_json_and_text_inputs_and_out_of_order_events(tmp_path: Path):
    json_path = write_jsonl(
        tmp_path / "in" / "one.jsonl",
        [
            {
                "event_id": "newer",
                "timestamp": "2026-10-28T11:00:00Z",
                "service_name": "api",
                "severity": "INFO",
                "message": "newer event",
            }
        ],
    )
    text_path = tmp_path / "in" / "two.log"
    text_path.write_text(
        '2026-10-28 09:00:00 ERROR api request_id=req-9 status_code=500 latency_ms=8 message="late arrival"\n',
        encoding="utf-8",
    )
    result = run_pipeline(
        [json_path, text_path],
        PipelineConfig(tmp_path / "store.db", tmp_path / "out"),
    )
    assert result["accepted_count"] == 2
    assert result["rejected_count"] == 0
    events = (tmp_path / "store.db")
    import sqlite3

    with sqlite3.connect(events) as connection:
        timestamps = [
            row[0]
            for row in connection.execute(
                "SELECT timestamp_utc FROM log_events ORDER BY timestamp_utc"
            )
        ]
    assert timestamps[0].startswith("2026-10-28T09:00:00")


def test_report_failure_marks_run_failed_without_losing_committed_events(tmp_path: Path, monkeypatch):
    source = write_jsonl(
        tmp_path / "source.jsonl",
        [
            {
                "event_id": "safe-retry",
                "timestamp": "2026-10-28T09:30:00Z",
                "service_name": "api",
                "severity": "INFO",
                "message": "committed before report",
            }
        ],
    )
    config = PipelineConfig(tmp_path / "store.db", tmp_path / "output")

    def fail_reports(*_args, **_kwargs):
        raise OSError("simulated report disk failure")

    monkeypatch.setattr("log_analytics.pipeline.write_outputs", fail_reports)
    with pytest.raises(OSError, match="simulated report disk failure"):
        run_pipeline([source], config)

    with sqlite3.connect(config.database_path) as connection:
        assert connection.execute("SELECT count(*) FROM log_events").fetchone()[0] == 1
        assert connection.execute("SELECT status FROM pipeline_runs").fetchone()[0] == "failed"


def test_reconciliation_failure_marks_run_failed(tmp_path: Path, monkeypatch):
    source = write_jsonl(
        tmp_path / "source.jsonl",
        [
            {
                "event_id": "check-failure",
                "timestamp": "2026-10-28T09:30:00Z",
                "service_name": "api",
                "severity": "INFO",
                "message": "event",
            }
        ],
    )
    config = PipelineConfig(tmp_path / "store.db", tmp_path / "output")
    monkeypatch.setattr(
        "log_analytics.pipeline.reconcile_run",
        lambda *_args, **_kwargs: {
            "run_id": "test",
            "passed": False,
            "checks_passed": 0,
            "checks_failed": 1,
            "checks": [],
            "failed_checks": ["forced_failure"],
        },
    )
    result = run_pipeline([source], config)
    assert result["status"] == "failed"
    with sqlite3.connect(config.database_path) as connection:
        status, failure = connection.execute(
            "SELECT status, error_message FROM pipeline_runs"
        ).fetchone()
    assert status == "failed"
    assert "forced_failure" in failure


def test_empty_directory_is_a_successful_zero_input_batch(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run_pipeline(
        [empty],
        PipelineConfig(tmp_path / "empty.db", tmp_path / "empty-output"),
    )
    assert result["status"] == "succeeded"
    assert result["input_count"] == 0
    assert result["reconciliation"]["passed"] is True
