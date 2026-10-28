# Business rules and input contract

## Supported schema

Required JSON fields: `timestamp`, `service_name`, `severity`, and `message`.
`event_id` is optional and is derived if absent. Optional fields are
`request_id`, `status_code`, and `latency_ms`. Any extra JSON property is
quarantined as unexpected schema drift. Null optional fields are allowed.

The plain-text adapter supports one timestamp, severity, service name, and
shell-quoted `key=value` attributes. It recognizes the same field names as the
JSON schema. A missing message, repeated attribute, invalid quoting, or
unrecognized line is quarantined.

## Validation policy

- JSON timestamp strings must be ISO-8601 and timezone-aware. Explicit offsets
  are converted to UTC. Naive JSON timestamps are rejected.
- The documented plain-text format has no timezone token in its base example;
  its naive timestamp is explicitly interpreted as UTC. An explicit offset is
  respected.
- Severity is trimmed and uppercased. `WARN -> WARNING`, `CRITICAL -> FATAL`,
  and `TRACE -> DEBUG`. Other values outside DEBUG, INFO, WARNING, ERROR, FATAL
  are rejected.
- `service_name` must be a nonempty string after trimming.
- `message` must be a string. Empty strings are allowed; the raw line remains
  available for audit.
- Provided `event_id` must be a nonempty string. Missing IDs are derived.
- `status_code` must be a JSON integer (or a digit-only text attribute) in the
  inclusive range 100–599. Booleans, strings in JSON, and fractional values are
  invalid.
- `latency_ms` must be a JSON number (or a numeric text attribute), finite, and
  nonnegative. Strings in JSON are invalid. Missing values are stored as null
  and are never treated as zero.
- Every validation or parsing rejection stores raw content, source, line, and
  reason. One bad row does not stop the batch.
- Blank lines are skipped, not counted as input records.

## Identity and duplicate behavior

Provided IDs are the preferred identity. Fallback IDs are SHA-256 over a
canonical JSON representation of supported fields plus the input path and
physical line number. Identical messages at different lines remain distinct.
Rerunning the same file path with unchanged content yields stable IDs. Moving
or renaming the file changes fallback IDs; supply source IDs to avoid that
limitation.

An exact duplicate in a batch or SQLite is counted in `duplicate_count` and
not inserted. Reuse of an ID with a different normalized payload is rejected
and quarantined. SQLite's event primary key is the final duplicate barrier.

## Count reconciliation

For each run, accepted and rejected classifications are mutually exclusive.
Exact duplicates are a subset of accepted records:

```text
input_count = accepted_count + rejected_count
parsed_count = input_count - parse_error_count
accepted_count = inserted_count + duplicate_count
```

`parsed_count` includes schema-invalid records because parsing succeeded.
Exact duplicates pass validation and identity checks, so they remain accepted,
but are counted separately and are not inserted again. Conflicting IDs are
rejections. A successful run can have rejections and is then marked
`succeeded_with_rejections`.

## Analytics

- Severity error count is ERROR plus FATAL.
- Severity error rate denominator is all stored accepted events for that
  service or time bucket.
- HTTP failure rate counts status 400–599 and has its own denominator and
  column.
- Latency percentiles use sorted values and linear interpolation at
  `(n - 1) * quantile`, matching an inclusive percentile definition.
- Windows are UTC; hourly windows begin at minute 00 and daily windows at
  00:00:00. The start is inclusive.
- Reports aggregate the complete target database so they can be regenerated
  after each run.
