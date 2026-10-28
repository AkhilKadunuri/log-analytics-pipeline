"""Configuration and UTC clock helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    database_path: Path
    output_dir: Path
    window: str = "hour"

    def __post_init__(self) -> None:
        if self.window not in {"hour", "day"}:
            raise ValueError("window must be 'hour' or 'day'")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
