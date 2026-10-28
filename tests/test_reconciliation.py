from __future__ import annotations

from pathlib import Path

from log_analytics.analytics import build_analytics
from log_analytics.models import NormalizedEvent
from log_analytics.reconciliation import reconcile_run
from log_analytics.storage import SQLiteStore


def test_reconciliation_detects_inconsistent_aggregate_total(tmp_path: Path):
    store = SQLiteStore(tmp_path / "store.db")
    store.start_run("run-1", "2026-10-28T09:31:00+00:00", "[]", "hour")
    event = NormalizedEvent(
        "one",
        "2026-10-28T09:30:00+00:00",
        "api",
        "INFO",
        "ok",
        None,
        None,
        1.0,
        "fixture.jsonl",
        1,
        "run-1",
        "2026-10-28T09:31:00+00:00",
    )
    counts = store.persist_batch("run-1", [event], [], 1, 1, 0, 0)
    store.update_run_counts("run-1", counts)
    analytics = build_analytics(store.all_events(), "hour")
    analytics["service_summary"][0]["total_events"] = 99
    result = reconcile_run(store, store.get_run("run-1"), analytics)
    assert result["passed"] is False
    assert "aggregate_event_total" in result["failed_checks"]
