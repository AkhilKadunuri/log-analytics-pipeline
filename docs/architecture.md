# Architecture

## Flow

1. **Configuration and CLI** — `cli.py` parses generate, run, and benchmark
   commands; `PipelineConfig` supplies the database, output directory, and UTC
   window size.
2. **Discovery and ingestion** — `parser.py` expands repeatable file and
   directory inputs in deterministic path order. It counts nonblank records and
   preserves each physical line number and source path.
3. **Parsing** — Each line is decoded independently as a JSON object or the
   documented key/value text format. Parse failures become rejections rather
   than terminating the batch.
4. **Validation and normalization** — `validator.py` checks the exact schema,
   required fields and types, HTTP status range, finite nonnegative latency,
   timestamp offsets, and severity aliases. It creates a normalized event or a
   meaningful rejection reason.
5. **Identity and deduplication** — A source `event_id` is preferred. Missing
   IDs use SHA-256 of canonical supported fields plus source path and line.
   Exact repeats are counted; conflicting payloads under one ID are rejected.
6. **Persistence** — `storage.py` writes novel events and rejections in an
   explicit `BEGIN IMMEDIATE` transaction. SQLite primary keys and checks are
   the final integrity barrier. Repeats found in prior runs are counted as
   duplicates; conflicting historical IDs are quarantined.
7. **Analytics** — Reports are regenerated from all stored events. Service and
   hourly/daily summaries are sorted with stable columns. Percentiles use
   inclusive linear interpolation at `(n - 1) * q`.
8. **Reconciliation** — Counts, inserted rows, uniqueness, required fields,
   UTC timestamps, latency rules, and aggregate totals are independently
   checked. A failed check is recorded and fails the run.
9. **Monitoring** — A UUID run ID and start/status/counters/duration/source
   description are saved in `pipeline_runs`. Python logging emits a concise
   run summary.

## Transaction and retry boundary

The event and quarantine writes for a batch commit together. The run begins as
`running`; after the transaction, analytics and reconciliation run, and the
status becomes `succeeded`, `succeeded_with_rejections`, or `failed`.

If the database transaction fails, it rolls back its event and rejection
changes. If a later report step fails, the committed event rows remain and the
run becomes `failed`; retrying is safe because event IDs are deterministic or
source-provided and protected by a primary key. This is idempotent batch
ingestion, not a claim of distributed exactly-once processing.

## Storage grain

- `log_events`: one normalized event per unique `event_id`.
- `rejected_records`: one rejected source line per run and rejection reason.
- `pipeline_runs`: one row per CLI execution.
- CSV analytics: one row per service, service/window, or service latency
  summary, according to the file.

## Resource profile

Source files are iterated line by line, while normalized candidate rows and
analytical events are held in memory for a run. This keeps implementation
simple and suitable for the requested 100,000-record laptop benchmark. Larger
workloads should use chunked writes and streaming/grouped database queries.
