"""Independent database and metric consistency checks."""

from __future__ import annotations

from typing import Any

from log_analytics.storage import SQLiteStore


def _check(name: str, expected: Any, actual: Any, explanation: str) -> dict[str, Any]:
    return {
        "check_name": name,
        "expected": expected,
        "actual": actual,
        "passed": expected == actual,
        "explanation": explanation,
    }


def reconcile_run(
    store: SQLiteStore,
    run: dict[str, Any],
    analytics: dict[str, Any],
) -> dict[str, Any]:
    database = store.database_checks()
    summary_total = sum(row["total_events"] for row in analytics["service_summary"])
    checks = [
        _check(
            "input_classification_reconciles",
            run["input_count"],
            run["accepted_count"] + run["rejected_count"],
            "Each nonblank source record is accepted or rejected; exact duplicates are included in accepted.",
        ),
        _check(
            "parsed_record_count",
            run["input_count"] - run["parse_error_count"],
            run["parsed_count"],
            "Parsed means the record matched JSON-object or supported plain-text syntax.",
        ),
        _check(
            "accepted_duplicate_insert_reconciles",
            run["accepted_count"],
            run["inserted_count"] + run["duplicate_count"],
            "Accepted records consist of newly inserted events plus exact duplicates.",
        ),
        _check(
            "inserted_rows_query",
            run["inserted_count"],
            store.count_for_run(run["run_id"]),
            "The target table is queried independently by run_id.",
        ),
        _check(
            "primary_key_unique",
            database["total"],
            database["distinct_ids"],
            "SQLite event_id is the primary key; the distinct count must equal the row count.",
        ),
        _check(
            "accepted_required_fields_valid",
            0,
            database["invalid_required"],
            "Persisted records must have a timestamp, nonempty service, and recognized severity.",
        ),
        _check(
            "timestamps_normalized_to_utc",
            0,
            database["non_utc"],
            "Every stored timestamp uses an explicit +00:00 offset.",
        ),
        _check(
            "latency_business_rule",
            0,
            database["invalid_latency"],
            "Stored latency values must be nonnegative and finite.",
        ),
        _check(
            "aggregate_event_total",
            database["total"],
            summary_total,
            "The grouped service summary total must equal the independently queried target row count.",
        ),
    ]
    failed = [check["check_name"] for check in checks if not check["passed"]]
    return {
        "run_id": run["run_id"],
        "passed": not failed,
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }
