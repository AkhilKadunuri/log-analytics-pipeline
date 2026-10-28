"""SQLite persistence with explicit transactions and conflict classification."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from log_analytics.models import NormalizedEvent, Rejection
from log_analytics.transformer import event_payload

SCHEMA = """
CREATE TABLE IF NOT EXISTS log_events (
    event_id TEXT PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    service_name TEXT NOT NULL CHECK (length(trim(service_name)) > 0),
    severity TEXT NOT NULL CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'FATAL')),
    message TEXT NOT NULL,
    request_id TEXT,
    status_code INTEGER CHECK (status_code IS NULL OR status_code BETWEEN 100 AND 599),
    latency_ms REAL CHECK (latency_ms IS NULL OR latency_ms >= 0),
    source_file TEXT NOT NULL,
    source_line INTEGER NOT NULL CHECK (source_line > 0),
    run_id TEXT NOT NULL,
    ingested_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_events_time_service ON log_events(timestamp_utc, service_name);
CREATE INDEX IF NOT EXISTS idx_log_events_severity ON log_events(severity);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    duration_seconds REAL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'succeeded_with_rejections', 'failed')),
    input_count INTEGER NOT NULL DEFAULT 0,
    parsed_count INTEGER NOT NULL DEFAULT 0,
    parse_error_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    source_description TEXT NOT NULL,
    time_window TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rejected_records (
    reject_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file TEXT NOT NULL,
    source_line INTEGER NOT NULL,
    raw_record TEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    rejected_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejected_records_run ON rejected_records(run_id);
"""

EVENT_COLUMNS = (
    "event_id",
    "timestamp_utc",
    "service_name",
    "severity",
    "message",
    "request_id",
    "status_code",
    "latency_ms",
    "source_file",
    "source_line",
    "run_id",
    "ingested_at_utc",
)


class SQLiteStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row

        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def start_run(self, run_id: str, started_at: str, sources: str, window: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO pipeline_runs
                   (run_id, started_at_utc, status, source_description, time_window)
                   VALUES (?, ?, 'running', ?, ?)""",
                (run_id, started_at, sources, window),
            )

    @staticmethod
    def _event_values(event: NormalizedEvent) -> tuple[Any, ...]:
        return tuple(getattr(event, column) for column in EVENT_COLUMNS)

    @staticmethod
    def _rejection_id(run_id: str, rejection: Rejection) -> str:
        identity = "\x1f".join(
            (
                run_id,
                rejection.source_file,
                str(rejection.source_line),
                rejection.raw_record,
                rejection.rejection_reason,
            )
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def persist_batch(
        self,
        run_id: str,
        events: Sequence[NormalizedEvent],
        rejections: Sequence[Rejection],
        input_count: int,
        parsed_count: int,
        parse_error_count: int,
        in_batch_duplicates: int,
    ) -> dict[str, int]:
        """Persist a batch atomically; exact database repeats become duplicates."""
        inserted = 0
        database_duplicates = 0
        final_rejections = list(rejections)
        event_placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        event_insert = f"INSERT INTO log_events ({', '.join(EVENT_COLUMNS)}) VALUES ({event_placeholders})"
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for event in events:
                existing = connection.execute(
                    "SELECT * FROM log_events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                if existing is not None:
                    existing_payload = (
                        existing["timestamp_utc"],
                        existing["service_name"],
                        existing["severity"],
                        existing["message"],
                        existing["request_id"],
                        existing["status_code"],
                        existing["latency_ms"],
                    )
                    if existing_payload == event_payload(event):
                        database_duplicates += 1
                    else:
                        final_rejections.append(
                            Rejection(
                                event.source_file,
                                event.source_line,
                                json.dumps(dict(zip(EVENT_COLUMNS, self._event_values(event))), ensure_ascii=False),
                                f"event_id {event.event_id!r} conflicts with an existing stored event",
                            )
                        )
                    continue
                connection.execute(event_insert, self._event_values(event))
                inserted += 1

            rejected_at = self._utc_now()
            for rejection in final_rejections:
                connection.execute(
                    """INSERT OR IGNORE INTO rejected_records
                       (reject_id, run_id, source_file, source_line, raw_record,
                        rejection_reason, rejected_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self._rejection_id(run_id, rejection),
                        run_id,
                        rejection.source_file,
                        rejection.source_line,
                        rejection.raw_record,
                        rejection.rejection_reason,
                        rejected_at,
                    ),
                )

        total_duplicates = in_batch_duplicates + database_duplicates
        return {
            "input_count": input_count,
            "parsed_count": parsed_count,
            "parse_error_count": parse_error_count,
            "accepted_count": inserted + total_duplicates,
            "rejected_count": len(final_rejections),
            "duplicate_count": total_duplicates,
            "inserted_count": inserted,
            "failed_count": 0,
        }

    def update_run_counts(self, run_id: str, counts: dict[str, int]) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE pipeline_runs SET input_count=?, parsed_count=?, parse_error_count=?,
                   accepted_count=?, rejected_count=?, duplicate_count=?, inserted_count=?,
                   failed_count=? WHERE run_id=?""",
                (
                    counts["input_count"],
                    counts["parsed_count"],
                    counts["parse_error_count"],
                    counts["accepted_count"],
                    counts["rejected_count"],
                    counts["duplicate_count"],
                    counts["inserted_count"],
                    counts["failed_count"],
                    run_id,
                ),
            )

    def finalize_run(
        self,
        run_id: str,
        ended_at: str,
        duration_seconds: float,
        status: str,
        error_message: str | None = None,
        failed_count: int = 0,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE pipeline_runs SET ended_at_utc=?, duration_seconds=?, status=?,
                   error_message=?, failed_count=? WHERE run_id=?""",
                (ended_at, duration_seconds, status, error_message, failed_count, run_id),
            )

    def mark_failed(self, run_id: str, ended_at: str, duration_seconds: float, message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE pipeline_runs SET ended_at_utc=?, duration_seconds=?, status='failed',
                   error_message=?, failed_count=1 WHERE run_id=?""",
                (ended_at, duration_seconds, message[:2000], run_id),
            )

    def all_events(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM log_events ORDER BY timestamp_utc, event_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def all_rejections(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM rejected_records ORDER BY rejected_at_utc, reject_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"pipeline run not found: {run_id}")
        return dict(row)

    def count_for_run(self, run_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT count(*) AS total FROM log_events WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row["total"])

    def database_checks(self) -> dict[str, int]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT count(*) AS total,
                   count(DISTINCT event_id) AS distinct_ids,
                   sum(CASE WHEN length(trim(service_name))=0 OR timestamp_utc IS NULL
                       OR severity NOT IN ('DEBUG','INFO','WARNING','ERROR','FATAL') THEN 1 ELSE 0 END)
                       AS invalid_required,
                   sum(CASE WHEN substr(timestamp_utc, -6) != '+00:00' THEN 1 ELSE 0 END)
                       AS non_utc,
                   sum(CASE WHEN latency_ms IS NOT NULL AND (latency_ms < 0 OR latency_ms > 1.7976931348623157e308)
                       THEN 1 ELSE 0 END) AS invalid_latency
                   FROM log_events"""
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    @staticmethod
    def _utc_now() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()
