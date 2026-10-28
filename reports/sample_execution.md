# Sample execution

This report records the actual mixed-format sample run executed in the project
environment.

## Command

```bash
PYTHONPATH=src python -m log_analytics.cli run \
  --input data/raw/sample_logs.jsonl \
  --input data/raw/sample_text.log \
  --db output/log_analytics_sample.db \
  --output-dir output \
  --window hour
```

## Results

- Environment: Python 3.12.12 on Linux x86_64.
- Status: `succeeded_with_rejections`.
- Duration: 0.055335 seconds.
- Input: 8 nonblank records; 7 parsed; 1 parse error.
- Classification: 5 accepted, 3 rejected, 1 duplicate, and 4 inserted.
- Reconciliation: 9 checks passed, 0 failed.
- Rejection reasons: one malformed JSON record, one invalid HTTP status, and
  one unknown severity.

## Outputs

The generated `output/` reports contain:

- `auth-service`: 1 event, 0% severity error rate, 35 ms mean latency.
- `payment-service`: 3 events, 3 ERROR/FATAL events, 100% severity error rate,
  315.3 ms mean latency, and 350.2 ms p95 latency.
- HTTP failure rate is 100% for payment-service, reported separately from its
  severity error rate.
- Severity distribution: 2 ERROR, 1 FATAL, 1 INFO.

`service_summary.csv`, `latency_summary.csv`, `error_summary.csv`,
`quality_report.json`, and `reconciliation_report.json` were generated from the
actual SQLite-backed run. The local sample database is ignored by Git.
