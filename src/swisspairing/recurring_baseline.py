"""Helpers for recurring benchmark baseline reporting."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, cast

TREND_COLUMNS = (
    "run_id",
    "timestamp_utc",
    "profile",
    "players_min",
    "players_max",
    "seed",
    "requested_tournaments",
    "exported_tournaments",
    "exported_files",
    "cases_total",
    "cases_executed",
    "cases_executed_fast",
    "cases_executed_strict",
    "cases_runner_error",
    "cases_runner_error_fast",
    "cases_runner_error_strict",
    "cases_both_ok_fast",
    "cases_both_ok_strict",
    "runner_error_rate",
    "runner_error_rate_fast",
    "runner_error_rate_strict",
    "py4swiss_success_rate",
    "swisspairing_success_rate",
    "swisspairing_fast_success_rate",
    "swisspairing_strict_success_rate",
    "pairing_equal_rate_when_both_ok",
    "pairing_equal_rate_fast_when_both_ok",
    "pairing_equal_rate_strict_when_both_ok",
    "pairing_equal_rate_fast_over_all_cases",
    "pairing_equal_rate_strict_over_all_cases",
    "py4swiss_p50_ms",
    "py4swiss_p95_ms",
    "swisspairing_p50_ms",
    "swisspairing_p95_ms",
    "swisspairing_fast_p50_ms",
    "swisspairing_fast_p95_ms",
    "swisspairing_strict_p50_ms",
    "swisspairing_strict_p95_ms",
    "p50_ratio_swisspairing_over_py4swiss",
    "p50_ratio_fast_over_py4swiss",
    "p50_ratio_strict_over_py4swiss",
    "sla_preset",
    "sla_passed",
    "sla_failures",
    "git_commit",
    "git_dirty",
)


def parse_profile_sizes(raw: str) -> tuple[int, ...]:
    """Parse comma-separated player-size profiles."""
    items = [item.strip() for item in raw.split(",")]
    if any(not item for item in items):
        raise ValueError("profiles must be a comma-separated list of integers")

    parsed: list[int] = []
    for item in items:
        try:
            value = int(item)
        except ValueError as exc:
            raise ValueError(f"invalid profile size: {item!r}") from exc
        if value < 2:
            raise ValueError(f"profile size must be >= 2: {value}")
        if value not in parsed:
            parsed.append(value)
    if not parsed:
        raise ValueError("at least one profile size is required")
    return tuple(parsed)


def append_trend_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Append baseline rows to CSV, creating header when needed."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.exists()
    needs_header = True
    if file_exists:
        needs_header = path.stat().st_size == 0

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TREND_COLUMNS)
        if needs_header:
            writer.writeheader()
        for row in rows:
            normalized = {column: row.get(column, "") for column in TREND_COLUMNS}
            writer.writerow(cast(Any, normalized))
