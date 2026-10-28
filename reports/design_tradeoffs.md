# Design trade-offs

## Python and standard library

Python was selected because it is approachable for an entry-level data
engineering assessment and has strong built-in support for JSON, timestamps,
hashing, regular expressions, file iteration, timing, logging, and SQLite.
The runtime has no third-party dependencies. pandas is deliberately omitted:
the required aggregates are small enough to express clearly with standard
library grouping, and using a fixed percentile formula avoids ambiguity about
library defaults.

## SQLite for local durability

SQLite provides durable tables, constraints, indexes, uniqueness, and explicit
transactions without a separate service. It makes the project reproducible on
Windows, macOS, and Linux. It is suitable for a single-machine assessment, but
not a substitute for a managed warehouse or concurrent distributed ingestion
system.

## JSONL and a narrow text grammar

Both inputs are easy to inspect, generate, and stream one physical line at a
time. JSONL has an explicit schema; the plain-text grammar demonstrates a
second parser without pretending to support arbitrary logs. Unsupported
formats are rejected rather than heuristically misread.

## Raw quarantine and normalized target

Accepted events have stable typed columns for analysis. Rejected input remains
separate in `rejected_records`, with the raw line, source path, line number, and
reason. This preserves auditability without polluting analytical aggregates.
Raw data can contain sensitive values, so the SQLite file must be protected.

## Event IDs and duplicates

Source-provided IDs are the reliable identity. Missing IDs use SHA-256 over a
canonical set of supported fields plus source path and physical line. The
location prevents collapsing identical legitimate messages on separate lines
and makes same-path reruns stable. The trade-off is that moving the file changes
fallback identity. A primary key is the final protection, exact replays are
counted, and payload conflicts are quarantined instead of overwritten.

## Error rate and HTTP failures

The severity error rate is `(ERROR + FATAL) / all accepted events`. This
measures application log severity. HTTP 4xx/5xx rates are separate because an
HTTP status can disagree with the severity chosen by a producer. Both use
explicit denominators and guard zero-event groups.

## Latency percentiles

The project uses inclusive linear interpolation over sorted observations:
position `(n - 1) * q`, then interpolate neighboring values. This works for
small groups and gives fixed expected values for tests. It uses memory
proportional to each service's latency observations; larger data should use a
streaming quantile sketch or database/warehouse percentile functions.

## Idempotency, transactions, and retries

Events and quarantine rows are inserted in one `BEGIN IMMEDIATE` transaction.
Unique IDs are checked under that write lock, and the database enforces the
primary key. A failed database transaction cannot partially persist the batch.
If reporting fails after commit, the run is marked failed but the durable event
rows remain; rerunning is safe because existing exact events become duplicates.
This is honest local idempotency, not distributed exactly-once processing.

## Performance choices

The pipeline iterates files rather than reading the raw file as one string,
uses one database connection/transaction for batch persistence, and includes
indexes for time/service and severity queries. The benchmark in
`performance_report.md` records measured results. Batch candidate events and
analytics rows are held in memory, which favors clarity and a 100,000-record
workload over unbounded streaming.

## What changes at larger scale

For millions or billions of records, use chunked transforms and writes,
partitioned object storage, a warehouse, and incremental or distributed
aggregations. Add schema versioning, coordinated migrations, controlled
concurrency, secure retention, access controls, and operational alerting.
Those additions would increase operational complexity and are not justified
for this assessment-sized local project.
