# Data dictionary

All tables are created by `storage.py`. Times are ISO-8601 strings with a
`+00:00` UTC offset. SQLite uses `TEXT`, `INTEGER`, and `REAL` affinities with
primary keys, checks, foreign keys, and indexes.

## `log_events`

**Grain:** one valid normalized event for a unique `event_id`.

| Column | Type | Null? | Meaning |
|---|---|---:|---|
| `event_id` | TEXT | No | Source ID or deterministic `sha256:` fallback; primary key. |
| `timestamp_utc` | TEXT | No | Event instant converted to UTC. |
| `service_name` | TEXT | No | Trimmed, nonempty originating service. |
| `severity` | TEXT | No | One of DEBUG, INFO, WARNING, ERROR, FATAL. |
| `message` | TEXT | No | Original message content. |
| `request_id` | TEXT | Yes | Correlation ID. |
| `status_code` | INTEGER | Yes | HTTP status from 100 through 599. |
| `latency_ms` | REAL | Yes | Finite, nonnegative latency in milliseconds. |
| `source_file` | TEXT | No | Input path used for this record. |
| `source_line` | INTEGER | No | 1-based physical line number. |
| `run_id` | TEXT | No | Ingestion run that first inserted the event. |
| `ingested_at_utc` | TEXT | No | UTC time at normalization. |

Indexes cover `(timestamp_utc, service_name)` and `severity`.

## `pipeline_runs`

**Grain:** one attempted pipeline execution. `run_id` is the primary key.

| Column | Type | Null? | Meaning |
|---|---|---:|---|
| `run_id` | TEXT | No | Unique UUID for this execution. |
| `started_at_utc` | TEXT | No | Run start. |
| `ended_at_utc` | TEXT | Yes | Run end; null while running. |
| `duration_seconds` | REAL | Yes | Measured elapsed time. |
| `status` | TEXT | No | running, succeeded, succeeded_with_rejections, or failed. |
| `input_count` | INTEGER | No | Nonblank physical records encountered. |
| `parsed_count` | INTEGER | No | Records recognized by a supported parser. |
| `parse_error_count` | INTEGER | No | Nonblank rows rejected during parsing. |
| `accepted_count` | INTEGER | No | Valid, non-conflicting input rows, including exact duplicates. |
| `rejected_count` | INTEGER | No | Parse, validation, or event-ID conflict rejections. |
| `duplicate_count` | INTEGER | No | Exact in-batch or previously stored repeats; subset of accepted count. |
| `inserted_count` | INTEGER | No | New event rows inserted; equals accepted count minus duplicates on success. |
| `failed_count` | INTEGER | No | Fatal run failure indicator (0 or 1). |
| `error_message` | TEXT | Yes | Fatal error or failed reconciliation details. |
| `source_description` | TEXT | No | JSON array of discovered input paths. |
| `time_window` | TEXT | No | UTC aggregate window: `hour` or `day`. |

The run is persisted before ingestion begins so fatal failures remain
observable.

## `rejected_records`

**Grain:** one raw rejected record for a specific run. `reject_id` is a SHA-256
key over run ID, source location, raw line, and reason.

| Column | Type | Null? | Meaning |
|---|---|---:|---|
| `reject_id` | TEXT | No | Deterministic rejection key within the run. |
| `run_id` | TEXT | No | Foreign key to `pipeline_runs`. |
| `source_file` | TEXT | No | Input path. |
| `source_line` | INTEGER | No | 1-based physical line number. |
| `raw_record` | TEXT | No | Original input line or serialized conflicting event. |
| `rejection_reason` | TEXT | No | Human-readable parse or validation failure. |
| `rejected_at_utc` | TEXT | No | UTC rejection time. |

## Output datasets

### `service_summary.csv`

One row per service across all events in the current database. Severity-based
error rate is `(ERROR + FATAL) / all events * 100`. HTTP failure rate is
`(4xx + 5xx) / all events * 100` and is intentionally separate.

### `latency_summary.csv`

One row per service. Null latency is omitted from statistics and separately
counted as missing. Percentiles use inclusive linear interpolation.

### `error_summary.csv`

One row per UTC time bucket and service. Hourly or daily bucket starts are
inclusive; the next bucket boundary is exclusive.

### `quality_report.json`

Current run counters, stored severity distribution, optional-field null counts,
rejection reason counts, percentile method, and reconciliation status.

### `reconciliation_report.json`

Named checks with expected and actual values, pass/fail flags, and explanations.
