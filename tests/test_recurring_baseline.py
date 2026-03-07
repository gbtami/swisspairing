from __future__ import annotations

from pathlib import Path

import pytest

from swisspairing.recurring_baseline import append_trend_rows, parse_profile_sizes


def test_parse_profile_sizes_accepts_comma_separated_integers() -> None:
    assert parse_profile_sizes("32,64,128,256") == (32, 64, 128, 256)


def test_parse_profile_sizes_rejects_invalid_entries() -> None:
    with pytest.raises(ValueError):
        parse_profile_sizes("32,,64")
    with pytest.raises(ValueError):
        parse_profile_sizes("foo,64")
    with pytest.raises(ValueError):
        parse_profile_sizes("1,64")


def test_append_trend_rows_writes_header_once(tmp_path: Path) -> None:
    target = tmp_path / "trend.csv"
    append_trend_rows(
        target,
        [
            {
                "run_id": "run1",
                "timestamp_utc": "2026-03-06T00:00:00Z",
                "profile": "p32",
                "players_min": 32,
                "players_max": 32,
                "seed": 20260338,
                "sla_preset": "preset-a",
                "sla_passed": 1,
            }
        ],
    )
    append_trend_rows(
        target,
        [
            {
                "run_id": "run2",
                "timestamp_utc": "2026-03-07T00:00:00Z",
                "profile": "p64",
                "players_min": 64,
                "players_max": 64,
                "seed": 20260370,
                "sla_preset": "preset-a",
                "sla_passed": 0,
                "sla_failures": "fast p95 exceeded",
            }
        ],
    )

    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("run_id,timestamp_utc,profile,players_min,players_max")
    assert "sla_preset" in lines[0]
    assert "sla_passed" in lines[0]
    assert lines[1].startswith("run1,2026-03-06T00:00:00Z,p32,32,32")
    assert lines[2].startswith("run2,2026-03-07T00:00:00Z,p64,64,64")
