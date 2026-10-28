"""Orchestrate parsing, validation, SQLite writes, analytics, and reconciliation."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from log_analytics.analytics import build_analytics, write_outputs
from log_analytics.config import PipelineConfig
from log_analytics.deduplication import deduplicate_batch
from log_analytics.models import NormalizedEvent, Rejection
from log_analytics.parser import discover_files, iter_source_records
from log_analytics.reconciliation import reconcile_run
from log_analytics.storage import SQLiteStore
from log_analytics.validator import RecordValidationError, validate_and_normalize

logger = logging.getLogger(__name__)


def run_pipeline(input_paths: list[Path], config: PipelineConfig) -> dict[str, Any]:
    """Run one idempotent batch and return its persisted run summary."""
    files = discover_files(input_paths)
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(config.database_path)
    run_id = uuid.uuid4().hex
    started_at = datetime.now(UTC)
    start_clock = time.perf_counter()
    source_description = json.dumps([path.as_posix() for path in files], ensure_ascii=False)
    store.start_run(run_id, started_at.isoformat(), source_description, config.window)
    logger.info("run_started run_id=%s source_files=%d", run_id, len(files))

    input_count = 0
    parsed_count = 0
    parse_error_count = 0
    rejections: list[Rejection] = []
    validated_events: list[NormalizedEvent] = []
    try:
        for path in files:
            for record in iter_source_records(path):
                input_count += 1
                if record.fields is None:
                    parse_error_count += 1
                    rejections.append(
                        Rejection(
                            record.source_file,
                            record.source_line,
                            record.raw_record,
                            record.parse_error or "record could not be parsed",
                        )
                    )
                    continue
                parsed_count += 1
                try:
                    validated_events.append(
                        validate_and_normalize(
                            record,
                            run_id=run_id,
                            ingested_at_utc=datetime.now(UTC).isoformat(),
                        )
                    )
                except RecordValidationError as exc:
                    rejections.append(
                        Rejection(record.source_file, record.source_line, record.raw_record, str(exc))
                    )

        deduplicated = deduplicate_batch(validated_events)
        for event, reason in deduplicated.conflicts:
            rejections.append(
                Rejection(
                    event.source_file,
                    event.source_line,
                    json.dumps(
                        {
                            "event_id": event.event_id,
                            "timestamp_utc": event.timestamp_utc,
                            "service_name": event.service_name,
                            "severity": event.severity,
                            "message": event.message,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    reason,
                )
            )

        counts = store.persist_batch(
            run_id=run_id,
            events=deduplicated.unique_events,
            rejections=rejections,
            input_count=input_count,
            parsed_count=parsed_count,
            parse_error_count=parse_error_count,
            in_batch_duplicates=deduplicated.duplicate_count,
        )
        store.update_run_counts(run_id, counts)

        events = store.all_events()
        all_rejections = store.all_rejections()
        analytics = build_analytics(events, config.window)
        run_record = store.get_run(run_id)
        reconciliation = reconcile_run(store, run_record, analytics)

        if not reconciliation["passed"]:
            failed_checks = ", ".join(reconciliation["failed_checks"])
            status = "failed"
            error_message = f"reconciliation failed: {failed_checks}"
        elif counts["rejected_count"] > 0:
            status = "succeeded_with_rejections"
            error_message = None
        else:
            status = "succeeded"
            error_message = None

        elapsed = time.perf_counter() - start_clock
        ended_at = datetime.now(UTC).isoformat()
        store.finalize_run(
            run_id,
            ended_at,
            elapsed,
            status,
            error_message=error_message,
            failed_count=1 if status == "failed" else 0,
        )
        run_record = store.get_run(run_id)
        write_outputs(
            config.output_dir,
            analytics,
            events,
            all_rejections,
            run_record,
            reconciliation,
            config.window,
        )
        logger.info(
            "run_finished run_id=%s status=%s input=%d accepted=%d rejected=%d duplicates=%d inserted=%d",
            run_id,
            status,
            counts["input_count"],
            counts["accepted_count"],
            counts["rejected_count"],
            counts["duplicate_count"],
            counts["inserted_count"],
        )
        return {
            "run_id": run_id,
            "status": status,
            **counts,
            "duration_seconds": round(elapsed, 6),
            "source_files": [path.as_posix() for path in files],
            "reconciliation": reconciliation,
            "output_dir": config.output_dir.as_posix(),
            "database_path": config.database_path.as_posix(),
        }
    except Exception as exc:
        elapsed = time.perf_counter() - start_clock
        logger.exception("run_failed run_id=%s", run_id)
        try:
            store.mark_failed(
                run_id,
                datetime.now(UTC).isoformat(),
                elapsed,
                f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("failed_to_record_run_failure run_id=%s", run_id)
        raise
