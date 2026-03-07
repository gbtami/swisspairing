from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from _pytest.monkeypatch import MonkeyPatch

from swisspairing.benchmarking import (
    RECURRING_SYNTHETIC_SLA_PRESETS,
    BenchmarkSLA,
    build_benchmark_summary,
    build_trf_unplayed_games_by_player_id,
    discover_bbp_executable,
    evaluate_benchmark_sla,
    parse_bbp_pairings_output,
    portable_path_str,
)


def _timed_result(*, ok: bool, timings_ms: list[float]) -> dict[str, object]:
    return {
        "ok": ok,
        "error": None if ok else "PairingError",
        "timings_ms": timings_ms,
        "p50_ms": timings_ms[0] if timings_ms else 0.0,
        "p95_ms": timings_ms[-1] if timings_ms else 0.0,
        "pairings": [],
    }


def test_build_benchmark_summary_uses_both_ok_denominator() -> None:
    payloads = [
        {
            "py4swiss": _timed_result(ok=True, timings_ms=[1.0]),
            "swisspairing_fast": _timed_result(ok=True, timings_ms=[2.0]),
            "swisspairing_strict": _timed_result(ok=True, timings_ms=[3.0]),
            "pairings_equal_fast": True,
            "pairings_equal_strict": True,
        },
        {
            "py4swiss": _timed_result(ok=True, timings_ms=[1.5]),
            "swisspairing_fast": _timed_result(ok=True, timings_ms=[2.5]),
            "runner_error_strict": "strict runner failed",
            "pairings_equal_fast": False,
        },
        {
            "runner_error_fast": "fast runner failed",
            "runner_error_strict": "strict runner failed",
        },
    ]

    summary = build_benchmark_summary(payloads, total_cases=3)

    assert summary["cases_executed"] == 1
    assert summary["cases_executed_fast"] == 2
    assert summary["cases_executed_strict"] == 1
    assert summary["cases_runner_error"] == 2
    assert summary["cases_runner_error_fast"] == 1
    assert summary["cases_runner_error_strict"] == 2
    assert summary["cases_both_ok_fast"] == 2
    assert summary["cases_both_ok_strict"] == 1
    assert summary["pairing_equal_rate_fast_when_both_ok"] == 0.5
    assert summary["pairing_equal_rate_fast_over_all_cases"] == 1 / 3
    assert summary["pairing_equal_rate_strict_when_both_ok"] == 1.0
    assert summary["pairing_equal_rate_strict_over_all_cases"] == 1 / 3


def test_evaluate_benchmark_sla_checks_fast_equality_rate() -> None:
    summary = {
        "swisspairing_fast_success_rate": 1.0,
        "runner_error_rate": 0.0,
        "swisspairing_fast_p95_ms": 25.0,
        "p50_ratio_fast_over_py4swiss": 0.5,
        "pairing_equal_rate_fast_when_both_ok": 0.75,
    }
    sla = BenchmarkSLA(min_fast_equality_rate_when_both_ok=0.9)

    failures = evaluate_benchmark_sla(summary, sla)

    assert failures == ["fast equality rate when both ok 0.750 is below minimum 0.900"]


def test_current_recurring_sla_preset_matches_checked_in_baseline() -> None:
    run_summary_path = (
        Path(__file__).resolve().parents[1]
        / "benchmarks"
        / "results"
        / "recurring"
        / "post-fast-cap-6-plus-512-20260306"
        / "run_summary.json"
    )
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    preset = RECURRING_SYNTHETIC_SLA_PRESETS["post-fast-cap-6-plus-512-20260306"]

    for result in run_summary["results"]:
        size = int(result["size"])
        failures = evaluate_benchmark_sla(result["benchmark_summary"], preset[size])
        assert failures == []


def test_parse_bbp_pairings_output_normalizes_byes_and_colors() -> None:
    output_text = "\n".join(("6", "3 1", "4 2", "6 0"))

    pairings = parse_bbp_pairings_output(output_text)

    assert pairings == [["1", "3"], ["2", "4"], ["6", None]]


def test_parse_bbp_pairings_output_rejects_invalid_lines() -> None:
    output_text = "\n".join(("6", "1 3", "oops"))

    try:
        parse_bbp_pairings_output(output_text)
    except ValueError as exc:
        assert "invalid bbpPairings pairing line" in str(exc)
    else:
        raise AssertionError("expected invalid bbpPairings output to raise ValueError")


def test_discover_bbp_executable_prefers_explicit_env(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "bbpPairings.exe"
    executable.write_text("", encoding="utf-8")

    monkeypatch.setenv("SWISSPAIRING_BBP_EXECUTABLE", str(executable))
    monkeypatch.delenv("BBP_PAIRINGS_EXE", raising=False)

    assert discover_bbp_executable() == executable


def test_portable_path_str_rewrites_home_paths() -> None:
    assert portable_path_str(Path.home() / "bbpPairings" / "bbpPairings.exe") == (
        "~/bbpPairings/bbpPairings.exe"
    )


def test_portable_path_str_preserves_non_home_paths(tmp_path: Path) -> None:
    assert portable_path_str(tmp_path / "example.json") == str(tmp_path / "example.json")


def test_build_trf_unplayed_games_by_player_id_counts_played_vs_unplayed() -> None:
    def _result(token: str) -> SimpleNamespace:
        return SimpleNamespace(result=SimpleNamespace(value=token))

    trf = SimpleNamespace(
        x_section=SimpleNamespace(number_of_rounds=3),
        player_sections=(
            SimpleNamespace(starting_number=1, results=(_result("1"),)),
            SimpleNamespace(starting_number=2, results=(_result("Z"),)),
            SimpleNamespace(starting_number=3, results=(_result("W"), _result("="))),
            SimpleNamespace(starting_number=4, results=()),
        ),
    )

    counts = build_trf_unplayed_games_by_player_id(trf)

    assert counts == {1: 1, 2: 2, 3: 0, 4: 2}
