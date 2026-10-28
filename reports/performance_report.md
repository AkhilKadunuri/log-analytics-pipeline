# Performance report

## Method

The benchmark command uses `time.perf_counter()` to measure generation and
pipeline execution separately. Pipeline time includes parse, validate,
deduplicate, SQLite writes, analytics, reconciliation, and output generation.
Each run uses a fresh temporary SQLite file, output directory, and deterministic
input.

## Results

Measurements are recorded here after executing the 10,000- and 100,000-record
commands. No performance number is assumed or copied from another machine.

| Requested records | Generation seconds | Pipeline seconds | Throughput (records/s) | Accepted | Rejected | Duplicates | Inserted |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.131763 | 0.714829 | 13,989.36 | 9,520 | 480 | 219 | 9,301 |
| 100,000 | 1.268620 | 15.541835 | 6,434.25 | 95,063 | 4,937 | 2,046 | 93,017 |

## Environment and limitations

Measured with Python 3.12.12 on
`Linux-6.18.59-x86_64-with-glibc2.40`, 4 reported CPUs; processor model was not
reported. A single run is sensitive to CPU scheduling, filesystem cache, and
local storage. It is not a cross-machine guarantee.

## Optimization and trade-off

File input is processed line by line. Database writes share a single explicit
transaction rather than committing each row independently, reducing repeated
connection/commit overhead while preserving rollback. In-memory validated rows
and summary groups simplify deterministic duplicate checks and percentile
calculation; memory use grows with batch size. The implementation is intended
for the requested 100,000-record assessment workload, not unlimited files.

The 100,000-line run completed in 15.541835 seconds at 6,434.25 input records
per second in this environment. The benchmark uses fresh temporary input,
database, and report locations. The full measurements and exact count
reconciliation are stored in `benchmark_10000.json` and
`benchmark_100000.json`.
