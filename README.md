# Data Engineering Log Analytics Pipeline

A reproducible local Python pipeline that reads structured JSON Lines and a
documented plain-text log format, validates and normalizes events, stores clean
records in SQLite, quarantines rejected input, and produces error, latency, and
data-quality reports.

## Business problem

Application logs are useful only when their timestamps, severity, identifiers,
and measurements can be trusted. This pipeline makes inconsistent records
visible, preserves their origin, prevents repeated ingestion from creating
duplicate events, and produces metrics that analysts can reproduce from stored
data.

## Scope and non-goals

It supports two explicit line-oriented formats, SQLite persistence, repeatable batch runs,
CSV/JSON outputs, and synthetic data. It is not a general-purpose parser,
distributed stream processor, cloud service, or production observability
platform. Kafka, Spark, Airflow, cloud storage, and arbitrary vendor-specific
formats are intentionally out of scope.

## Features

- Parses JSONL objects and the supported key-value plain-text format.
- Continues after malformed lines and stores rejected raw input with a reason.
- Normalizes timezone-aware timestamps to ISO-8601 UTC.
- Normalizes `WARN` to `WARNING`, `CRITICAL` to `FATAL`, and `TRACE` to `DEBUG`.
- Derives stable SHA-256 IDs when `event_id` is absent.
- Deduplicates within a batch and against SQLite; reports conflicting IDs as
  rejected records instead of silently overwriting them.
- Uses parameterized SQL, a database uniqueness constraint, and a batch
  transaction.
- Produces service, time-window error, latency, quality, and reconciliation
  reports.
- Generates seeded synthetic data, including controlled invalid records and
  exact duplicates.
- Includes a known-answer reference fixture, pytest suite, CLI, and benchmark.

## Technology

- Python 3.12 or later (the code uses only the standard library at runtime).
- SQLite for durable local storage.
- pytest for the automated test suite.
- pandas is intentionally not required: the summaries use grouped SQLite
  results in Python and a documented percentile calculation, keeping installs
  small and behavior explicit.

## Architecture

```text
JSONL / supported text files
  -> source discovery and line parsing
  -> schema validation and UTC/severity normalization
  -> deterministic event IDs and duplicate classification
  -> SQLite log_events + rejected_records + pipeline_runs
  -> service/time-window/latency analytics
  -> reconciliation checks
  -> CSV and JSON output files
```

The detailed stage boundaries and transaction behavior are in
[`docs/architecture.md`](docs/architecture.md). Column definitions are in
[`docs/data_dictionary.md`](docs/data_dictionary.md), and rules are in
[`docs/business_rules.md`](docs/business_rules.md).

## Repository map

```text
log-analytics-pipeline/
├── README.md
├── pyproject.toml
├── requirements.txt
├── data/
│   ├── expected/             # fixed reference input and expected answers
│   ├── generated/            # generated datasets (ignored by Git)
│   ├── quarantine/           # SQLite is the authoritative quarantine store
│   └── raw/                  # small JSONL and plain-text examples
├── docs/                     # architecture, rules, dictionary, troubleshooting
├── output/                   # reports and local SQLite DB (DB ignored by Git)
├── reports/                  # tradeoffs, benchmark, execution, acceptance
├── src/log_analytics/        # pipeline package and CLI
└── tests/                    # unit and integration tests
```

## Supported input formats

### JSON Lines

One JSON object per nonblank line. Required fields are `timestamp`,
`service_name`, `severity`, and `message`. `event_id` is optional; optional
fields are `request_id`, `status_code`, and `latency_ms`. JSON status codes must
be integers and JSON latencies must be numbers; the text parser converts valid
numeric attributes before validation.

```json
{"event_id":"evt-0001","timestamp":"2026-10-28T09:30:00Z","service_name":"payment-service","severity":"ERROR","message":"Payment failed","request_id":"req-001","status_code":500,"latency_ms":245.5}
```

JSON timestamps must contain `Z` or an explicit UTC offset. Extra properties
are treated as schema drift and quarantined.

### Plain text

The supported format is:

```text
YYYY-MM-DD HH:MM:SS SEVERITY service_name key=value ... message="quoted text"
```

For example:

```text
2026-10-28 09:30:00 ERROR payment-service request_id=req-003 status_code=503 latency_ms=350.2 message="Upstream service unavailable"
```

The date and time in this text format are explicitly defined as UTC when no
offset is present. Values use shell-style quoting for spaces; supported
attributes are the same as JSONL. This parser does not claim to support
arbitrary log formats.

Blank lines are ignored and are not included in `input_count`; source line
numbers still refer to physical file lines. Directories are scanned recursively
for `.jsonl`, `.log`, and `.txt` files in sorted path order.

## Installation

Python 3.12+ is required. From this repository directory:

### macOS and Linux

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

### Windows PowerShell

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

No `.env` file or secrets are needed. Runtime dependencies are from the Python
standard library.

## Generate data

Generate a deterministic 1,000-line dataset:

```bash
python -m log_analytics.cli generate --records 1000 --seed 42 --output data/generated/logs.jsonl
```

Tune `--invalid-ratio`, `--duplicate-ratio`, and `--output`. Ratios must be
between 0 and 1 and sum to no more than 1. The same seed, record count, and
ratios reproduce the same file. Generated datasets are intentionally excluded
from Git.

## Run the pipeline

Use both sample formats:

```bash
python -m log_analytics.cli run \
  --input data/raw/sample_logs.jsonl \
  --input data/raw/sample_text.log \
  --db output/log_analytics.db \
  --output-dir output \
  --window hour
```

PowerShell accepts the same command over multiple lines with backticks:

```powershell
python -m log_analytics.cli run `
  --input data/raw/sample_logs.jsonl `
  --input data/raw/sample_text.log `
  --db output/log_analytics.db `
  --output-dir output `
  --window hour
```

`--input` may be repeated and may name a file or directory. `--window` accepts
`hour` or `day`; windows use UTC and include timestamps at the start of each
window. The database is persistent. Reports summarize all events currently in
that database, while quality counts also show the current run.

The run command writes:

- `service_summary.csv`
- `latency_summary.csv`
- `error_summary.csv`
- `quality_report.json`
- `reconciliation_report.json`

The SQLite database contains `log_events`, `pipeline_runs`, and
`rejected_records`. Rejections keep the original line and source location; be
careful because real log lines can contain secrets or personal data.

## Tests

```bash
python -m pytest -v
```

Tests use temporary files and databases and do not call external services. The
reference fixture has fixed expected counts and aggregate values in
`data/expected/reference_expected.json`.

## Benchmark

Measure 10,000 and 100,000 records separately:

```bash
python -m log_analytics.cli benchmark --records 10000 --seed 42 --report reports/benchmark_10000.json
python -m log_analytics.cli benchmark --records 100000 --seed 42 --report reports/benchmark_100000.json
```

Generation and pipeline times are measured independently with
`time.perf_counter()`. Pipeline time includes parsing, validation, SQLite,
analytics, reconciliation, and report writes. Results vary by machine and
filesystem; see [`reports/performance_report.md`](reports/performance_report.md)
for measurements actually run in this environment.

## Counting, duplicates, and retries

- `input_count`: nonblank source lines encountered.
- `parsed_count`: lines recognized as JSON objects or supported text records;
  a parsed row can still fail schema validation.
- `parse_error_count`: nonblank lines that could not be parsed.
- `accepted_count`: valid, non-conflicting records, including exact duplicates.
- `rejected_count`: malformed, invalid, schema-drift, or conflicting-ID rows
  stored in `rejected_records`.
- `duplicate_count`: exact repeated events in the batch or already stored;
  duplicates are a subset of `accepted_count`.
- `inserted_count`: rows newly committed by this run (equal to
  `accepted_count - duplicate_count` for a successful local transaction).

For completed runs, the accounting rule is:

```text
input_count = accepted_count + rejected_count
parsed_count = input_count - parse_error_count
accepted_count = inserted_count + duplicate_count
```

Run statuses are `succeeded`, `succeeded_with_rejections`, or `failed`.
Exact duplicates pass validation and are included in `accepted_count`, but are
separately measured in `duplicate_count` and not inserted again. Reprocessing an
identical file does not create additional target rows. A repeated ID with a
different normalized payload is quarantined. A failed post-commit report or
reconciliation step can leave committed events in place, but the run is marked
failed and retry remains safe because event IDs are unique.

Fallback IDs hash canonical supported fields together with the input path and
physical source line. This preserves identical messages on separate lines as
separate events and makes reruns of the same path stable. Moving or renaming the
file changes fallback IDs. A source-provided stable `event_id` is preferred.

## Failure handling and limits

Row-level errors are quarantined and do not stop the batch. A fatal file,
database, or report error marks the run failed. New event and quarantine writes
are grouped in one SQLite transaction; a failed write rolls back that batch.
If a later reporting stage fails after the data transaction commits, the run is
marked failed and a retry is idempotent.

The implementation buffers a batch and analytical rows in memory, so it is
appropriate for assessment-sized datasets (including 100,000 lines), not
unbounded files. It uses one local SQLite database and does not provide
cross-process exactly-once orchestration, schema migration tooling, arbitrary
timezone assumptions, or configurable custom schemas.

## Security and privacy

Use synthetic data for demos. Raw logs and quarantined rows may contain
credentials or personal information; restrict access to the local database,
avoid sharing it, and apply your organization's retention policy. SQL values
are parameterized, log text is never executed, and credentials are not needed.
The repository ignores generated datasets, output databases, virtual
environments, and caches.

## Future improvements

- Streaming/chunked processing for larger data volumes.
- Configurable source-timezone assumptions and schema versioning.
- A quarantine export command with safe redaction options.
- Database migration/versioning and concurrent-worker coordination.
- Additional parsers as separately tested input adapters.
