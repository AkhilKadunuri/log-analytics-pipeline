from __future__ import annotations

from pathlib import Path

from log_analytics.generator import generate_jsonl


def test_generator_is_reproducible_for_fixed_configuration(tmp_path: Path):
    first = tmp_path / "one.jsonl"
    second = tmp_path / "two.jsonl"
    counts_one = generate_jsonl(first, 100, seed=7, invalid_ratio=0.2, duplicate_ratio=0.1)
    counts_two = generate_jsonl(second, 100, seed=7, invalid_ratio=0.2, duplicate_ratio=0.1)
    assert counts_one == counts_two
    assert first.read_bytes() == second.read_bytes()
    assert counts_one["generated"] == 100
    assert counts_one["planned_invalid"] > 0
    assert counts_one["planned_duplicates"] > 0


def test_generator_supports_empty_output(tmp_path: Path):
    output = tmp_path / "empty.jsonl"
    result = generate_jsonl(output, 0)
    assert result == {"generated": 0, "planned_invalid": 0, "planned_duplicates": 0}
    assert output.read_text(encoding="utf-8") == ""
