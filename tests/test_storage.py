from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from log_analytics.models import NormalizedEvent, Rejection
from log_analytics.storage import SQLiteStore


def _event(run_id: str, latency: float | None = 5.0) -> NormalizedEvent:
    return NormalizedEvent(
        "stored-1",
        "2026-10-28T09:30:00+00:00",
        "api",
        "INFO",
        "ok",
        None,
        200,
        latency,
        "logs.jsonl",
        1,
        run_id,
        "2026-10-28T09:31:00+00:00",
    )


def test_database_persists_events_runs_and_rejections(tmp_path: Path):
    store = SQLiteStore(tmp_path / "store.db")
    store.start_run("run-1", "2026-10-28T09:31:00+00:00", "[]", "hour")
    counts = store.persist_batch(
        "run-1",
        [_event("run-1")],
        [Rejection("logs.jsonl", 2, "bad", "bad record")],
        2,
        2,
        0,
        0,
    )
    store.update_run_counts("run-1", counts)
    assert counts["inserted_count"] == 1
    assert store.count_for_run("run-1") == 1
    assert len(store.all_rejections()) == 1
    assert store.get_run("run-1")["input_count"] == 2


def test_existing_event_id_is_ignored_as_an_exact_duplicate(tmp_path: Path):
    store = SQLiteStore(tmp_path / "store.db")
    for run_id in ("run-1", "run-2"):
        store.start_run(run_id, "2026-10-28T09:31:00+00:00", "[]", "hour")
    first = store.persist_batch("run-1", [_event("run-1")], [], 1, 1, 0, 0)
    second = store.persist_batch("run-2", [_event("run-2")], [], 1, 1, 0, 0)
    assert first["inserted_count"] == 1
    assert second["duplicate_count"] == 1
    assert second["accepted_count"] == 1
    assert second["inserted_count"] == 0
    assert len(store.all_events()) == 1


def test_existing_event_id_with_changed_payload_is_rejected(tmp_path: Path):
    store = SQLiteStore(tmp_path / "store.db")
    store.start_run("run-1", "2026-10-28T09:31:00+00:00", "[]", "hour")
    store.start_run("run-2", "2026-10-28T09:32:00+00:00", "[]", "hour")
    store.persist_batch("run-1", [_event("run-1")], [], 1, 1, 0, 0)
    changed = NormalizedEvent(
        "stored-1",
        "2026-10-28T09:30:00+00:00",
        "api",
        "INFO",
        "changed message",
        None,
        200,
        5.0,
        "logs.jsonl",
        2,
        "run-2",
        "2026-10-28T09:32:00+00:00",
    )
    counts = store.persist_batch("run-2", [changed], [], 1, 1, 0, 0)
    assert counts["rejected_count"] == 1
    assert counts["duplicate_count"] == 0
    assert counts["accepted_count"] == 0
    assert "conflicts with an existing" in store.all_rejections()[0]["rejection_reason"]


def test_database_check_failure_rolls_back_batch(tmp_path: Path):
    store = SQLiteStore(tmp_path / "store.db")
    store.start_run("run-1", "2026-10-28T09:31:00+00:00", "[]", "hour")
    with pytest.raises(sqlite3.IntegrityError):
        store.persist_batch("run-1", [_event("run-1", latency=-1)], [], 1, 1, 0, 0)
    assert store.all_events() == []
    assert store.all_rejections() == []
