# Troubleshooting

## `No module named log_analytics`

Activate the virtual environment and install the local package from the
repository directory:

```bash
python -m pip install -e ".[test]"
```

Alternatively, run with the package path explicitly:

```bash
PYTHONPATH=src python -m log_analytics.cli --help
```

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m log_analytics.cli --help
```

## Python version is too old

The package requires Python 3.12 or later. Check `python --version` (or
`py -3.12 --version` on Windows) and activate the intended interpreter.

## Input is not discovered

Only `.jsonl`, `.log`, and `.txt` file extensions are read. For a directory,
discovery is recursive. Verify the path exists and contains supported files.
Blank lines are ignored.

## Records appear in `rejected_records`

Inspect `source_file`, `source_line`, and `rejection_reason` for the relevant
run. Common causes are naive JSON timestamps, unknown severity values, status
codes outside 100–599, negative or non-finite latency, unexpected JSON fields,
or plain-text quoting that does not match the documented grammar.

Raw rejected lines may contain secrets or personal data. Do not paste them into
public issue trackers.

## Existing database makes reports larger than expected

Reports are regenerated from every event in the selected database, not just
the latest run. Use a new `--db` path for an isolated backfill or demo.

## A repeated ID is rejected

The same `event_id` must identify the same normalized timestamp, service,
severity, message, request ID, status, and latency. If the payload changed,
choose a new source event ID or intentionally review the source correction.
The pipeline does not overwrite prior events.

## Database is locked or cannot be written

Close other processes using the database, check that the output directory is
writable, and retry. SQLite waits up to 30 seconds for a lock. A failed write
transaction rolls back the event and rejection batch and records a failed run
when the database remains available.
