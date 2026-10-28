from __future__ import annotations

from pathlib import Path

from log_analytics.parser import iter_source_records, parse_line


def test_valid_jsonl_record():
    record = parse_line(
        '{"event_id":"a","timestamp":"2026-10-28T09:30:00Z","service_name":"api","severity":"INFO","message":"ok"}',
        "logs.jsonl",
        1,
    )
    assert record is not None
    assert record.fields is not None
    assert record.fields["event_id"] == "a"


def test_valid_plain_text_and_unicode_message():
    record = parse_line(
        '2026-10-28 09:30:00 WARN api request_id=req-1 status_code=503 latency_ms=12.5 message="café down"',
        "app.log",
        7,
    )
    assert record is not None and record.fields is not None
    assert record.fields["timestamp"] == "2026-10-28T09:30:00+00:00"
    assert record.fields["message"] == "café down"


def test_malformed_json_is_a_record_error_not_an_exception():
    record = parse_line('{"event_id":', "logs.jsonl", 3)
    assert record is not None
    assert record.fields is None
    assert record.parse_error.startswith("malformed JSON:")


def test_unrecognized_text_format_is_rejected():
    record = parse_line("something happened but no timestamp exists", "app.log", 1)
    assert record is not None
    assert record.parse_error == "unrecognized plain-text log format"


def test_extra_fields_remain_visible_for_validation():
    record = parse_line('{"event_id":"a","surprise":true}', "logs.jsonl", 1)
    assert record is not None and record.fields is not None
    assert record.fields["surprise"] is True


def test_blank_lines_are_ignored():
    assert parse_line(" \t\r\n", "logs.jsonl", 1) is None


def test_empty_file_yields_no_records(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert list(iter_source_records(path)) == []
