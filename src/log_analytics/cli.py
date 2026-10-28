"""Command-line interface for data generation, pipeline runs, and benchmarks."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

from log_analytics.config import PipelineConfig
from log_analytics.generator import generate_jsonl
from log_analytics.monitoring import configure_logging
from log_analytics.pipeline import run_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="log-analytics",
        description="Validate, store, and analyze JSONL or supported plain-text application logs.",
    )
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="create deterministic synthetic JSONL data")
    generate.add_argument("--records", type=int, default=1000)
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--invalid-ratio", type=float, default=0.05)
    generate.add_argument("--duplicate-ratio", type=float, default=0.02)
    generate.add_argument("--output", type=Path, default=Path("data/generated/logs.jsonl"))

    run = commands.add_parser("run", help="run the ingestion and analytics pipeline")
    run.add_argument("--input", type=Path, action="append", required=True, help="file or directory; repeatable")
    run.add_argument("--db", type=Path, default=Path("output/log_analytics.db"))
    run.add_argument("--output-dir", type=Path, default=Path("output"))
    run.add_argument("--window", choices=("hour", "day"), default="hour")

    benchmark = commands.add_parser("benchmark", help="measure generation and pipeline execution")
    benchmark.add_argument("--records", type=int, default=10_000)
    benchmark.add_argument("--seed", type=int, default=42)
    benchmark.add_argument("--invalid-ratio", type=float, default=0.05)
    benchmark.add_argument("--duplicate-ratio", type=float, default=0.02)
    benchmark.add_argument("--window", choices=("hour", "day"), default="hour")
    benchmark.add_argument("--report", type=Path, default=None)
    return parser


def _benchmark(args: argparse.Namespace) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="log-analytics-benchmark-") as temp:
        root = Path(temp)
        input_path = root / "logs.jsonl"
        db_path = root / "benchmark.db"
        output_dir = root / "output"

        generation_started = time.perf_counter()
        generated = generate_jsonl(
            input_path,
            args.records,
            args.seed,
            args.invalid_ratio,
            args.duplicate_ratio,
        )
        generation_seconds = time.perf_counter() - generation_started

        pipeline_started = time.perf_counter()
        result = run_pipeline(
            [input_path],
            PipelineConfig(database_path=db_path, output_dir=output_dir, window=args.window),
        )
        pipeline_seconds = time.perf_counter() - pipeline_started

    benchmark_result: dict[str, object] = {
        "records_requested": args.records,
        "generation": generated,
        "generation_seconds": round(generation_seconds, 6),
        "pipeline_seconds": round(pipeline_seconds, 6),
        "throughput_records_per_second": round(args.records / pipeline_seconds, 2)
        if pipeline_seconds > 0
        else None,
        "pipeline_counts": {
            key: result[key]
            for key in (
                "input_count",
                "parsed_count",
                "parse_error_count",
                "accepted_count",
                "rejected_count",
                "duplicate_count",
                "inserted_count",
            )
        },
        "run_status": result["status"],
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "not reported",
        "cpu_count": os.cpu_count(),
        "measurement_notes": [
            "Single local run; results vary with filesystem cache, CPU, and storage.",
            "Generation time is separate from pipeline time.",
            "Pipeline timing includes parsing, SQLite, analytics, reconciliation, and report writes.",
        ],
    }
    report_path = args.report or Path("reports") / f"benchmark_{args.records}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(benchmark_result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    benchmark_result["report_path"] = report_path.as_posix()
    return benchmark_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    try:
        if args.command == "generate":
            result = generate_jsonl(
                args.output,
                args.records,
                args.seed,
                args.invalid_ratio,
                args.duplicate_ratio,
            )
            print(json.dumps({**result, "output": args.output.as_posix()}, indent=2))
            return 0

        if args.command == "run":
            result = run_pipeline(
                args.input,
                PipelineConfig(args.db, args.output_dir, args.window),
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["status"] == "failed" else 0

        result = _benchmark(args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["run_status"] == "failed" else 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    sys.exit(main())
