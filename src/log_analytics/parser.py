"""Safe parsers for the two supported line-oriented input formats."""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable, Iterator
from pathlib import Path

from log_analytics.models import SourceRecord

_TEXT_PREFIX = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T]"
    r"(?P<clock>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(?P<zone>Z|[+-]\d{2}:\d{2})?\s+"
    r"(?P<severity>[A-Za-z]+)\s+"
    r"(?P<service>[A-Za-z0-9_.-]+)\s+(?P<attributes>.+)$"
)


def parse_line(raw_line: str, source_file: str, source_line: int) -> SourceRecord | None:
    """Parse one nonblank line; return None for a blank line."""
    raw = raw_line.rstrip("\r\n")
    if not raw.strip():
        return None

    if raw.lstrip().startswith("{"):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            return SourceRecord(raw, source_file, source_line, None, f"malformed JSON: {exc.msg}")
        if not isinstance(value, dict):
            return SourceRecord(raw, source_file, source_line, None, "JSON record must be an object")
        return SourceRecord(raw, source_file, source_line, value)

    match = _TEXT_PREFIX.fullmatch(raw)
    if not match:
        return SourceRecord(raw, source_file, source_line, None, "unrecognized plain-text log format")

    timestamp = f"{match.group('date')}T{match.group('clock')}{match.group('zone') or '+00:00'}"
    try:
        tokens = shlex.split(match.group("attributes"), posix=True)
    except ValueError as exc:
        return SourceRecord(raw, source_file, source_line, None, f"malformed quoted text field: {exc}")

    fields: dict[str, object] = {
        "timestamp": timestamp,
        "severity": match.group("severity"),
        "service_name": match.group("service"),
    }
    for token in tokens:
        key, separator, value = token.partition("=")
        if not separator or not key:
            return SourceRecord(raw, source_file, source_line, None, f"invalid text attribute: {token!r}")
        if key in fields:
            return SourceRecord(raw, source_file, source_line, None, f"duplicate text attribute: {key}")
        if value.casefold() in {"null", "-", "none"}:
            fields[key] = None
        elif key == "status_code" and value.isdigit():
            fields[key] = int(value)
        elif key == "latency_ms":
            try:
                fields[key] = float(value)
            except ValueError:
                fields[key] = value
        else:
            fields[key] = value

    if "message" not in fields:
        return SourceRecord(raw, source_file, source_line, None, "plain-text record is missing message")
    return SourceRecord(raw, source_file, source_line, fields)


def iter_source_records(path: Path) -> Iterator[SourceRecord]:
    """Yield records in file order, keeping path and physical line number."""
    source_name = path.as_posix()
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, start=1):
            record = parse_line(line, source_name, line_number)
            if record is not None:
                yield record


def discover_files(inputs: Iterable[Path]) -> list[Path]:
    """Expand files and directories deterministically; reject unsupported inputs."""
    found: list[Path] = []
    supported_suffixes = {".jsonl", ".log", ".txt"}
    for item in inputs:
        if not item.exists():
            raise FileNotFoundError(f"input does not exist: {item}")
        if item.is_file():
            if item.suffix.lower() not in supported_suffixes:
                raise ValueError(f"unsupported input extension: {item}")
            found.append(item)
            continue
        if item.is_dir():
            found.extend(
                child
                for child in sorted(item.rglob("*"))
                if child.is_file() and child.suffix.lower() in supported_suffixes
            )
            continue
        raise ValueError(f"input must be a file or directory: {item}")
    return sorted(set(found), key=lambda path: path.as_posix())
