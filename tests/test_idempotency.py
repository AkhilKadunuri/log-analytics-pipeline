from __future__ import annotations

from pathlib import Path

from log_analytics.config import PipelineConfig
from log_analytics.pipeline import run_pipeline
from conftest import write_jsonl


def test_rerunning_identical_input_adds_no_events(tmp_path: Path):
    source = write_jsonl(
        tmp_path / "source.jsonl",
        [
            {
                "event_id": "stable-1",
                "timestamp": "2026-10-28T09:30:00Z",
                "service_name": "api",
                "severity": "INFO",
                "message": "same event",
            },
            {
                "event_id": "stable-2",
                "timestamp": "2026-10-28T09:31:00Z",
                "service_name": "api",
                "severity": "ERROR",
                "message": "second event",
            },
        ],
    )
    config = PipelineConfig(tmp_path / "idempotent.db", tmp_path / "output")
    first = run_pipeline([source], config)
    second = run_pipeline([source], config)
    assert first["inserted_count"] == 2
    assert second["inserted_count"] == 0
    assert second["duplicate_count"] == 2
    assert second["accepted_count"] == 2
    import sqlite3

    with sqlite3.connect(config.database_path) as connection:
        assert connection.execute("SELECT count(*) FROM log_events").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0] == 2
