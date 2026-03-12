from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from _pytest.monkeypatch import MonkeyPatch

from swisspairing.benchmarking import (
    RECURRING_SYNTHETIC_SLA_PRESETS,
    BenchmarkSLA,
    build_benchmark_summary,
    build_player_states_from_trf,
    build_trf_float_history_by_player_id,
    build_trf_had_full_point_unplayed_round_by_player_id,
    build_trf_initial_color,
    build_trf_unplayed_games_by_player_id,
    discover_bbp_executable,
    discover_javafo_jar,
    evaluate_benchmark_sla,
    normalize_lenient_trf16_text,
    parse_bbp_pairings_output,
    parse_javafo_pairings_output,
    portable_path_str,
    sort_pairings_for_compare,
)
from swisspairing.model import FloatKind


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
            "swisspairing": _timed_result(ok=True, timings_ms=[2.0]),
            "pairings_equal": True,
        },
        {
            "py4swiss": _timed_result(ok=True, timings_ms=[1.5]),
            "swisspairing": _timed_result(ok=True, timings_ms=[2.5]),
            "pairings_equal": False,
        },
        {
            "runner_error": "runner failed",
        },
    ]

    summary = build_benchmark_summary(payloads, total_cases=3)

    assert summary["cases_executed"] == 2
    assert summary["cases_runner_error"] == 1
    assert summary["cases_both_ok"] == 2
    assert summary["pairing_equal_rate_when_both_ok"] == 0.5
    assert summary["pairing_equal_rate_over_all_cases"] == 1 / 3


def test_evaluate_benchmark_sla_checks_equality_rate() -> None:
    summary = {
        "swisspairing_success_rate": 1.0,
        "runner_error_rate": 0.0,
        "swisspairing_p95_ms": 25.0,
        "p50_ratio_swisspairing_over_py4swiss": 0.5,
        "pairing_equal_rate_when_both_ok": 0.75,
    }
    sla = BenchmarkSLA(min_equality_rate_when_both_ok=0.9)

    failures = evaluate_benchmark_sla(summary, sla)

    assert failures == ["equality rate when both ok 0.750 is below minimum 0.900"]


def test_current_recurring_sla_preset_covers_default_profiles() -> None:
    preset = RECURRING_SYNTHETIC_SLA_PRESETS["post-bounded-c8-20260311"]
    assert set(preset) == {16, 32, 64, 128, 256, 512}

    for size, sla in preset.items():
        assert size > 0
        assert sla.min_success_rate == 1.0
        assert sla.max_runner_error_rate == 0.0
        assert sla.max_p95_ms is not None and sla.max_p95_ms > 0.0
        assert sla.max_p50_ratio is not None and sla.max_p50_ratio > 0.0
        assert sla.min_equality_rate_when_both_ok is not None
        assert 0.0 <= sla.min_equality_rate_when_both_ok <= 1.0


def test_exact_runtime_manifest_references_existing_trfs() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[1] / "benchmarks" / "fixtures" / "exact_runtime_cases.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels = [entry["label"] for entry in payload["cases"]]

    assert labels
    assert len(labels) == len(set(labels))
    for entry in payload["cases"]:
        trf_path = Path(__file__).resolve().parents[1] / entry["trf"]
        assert trf_path.is_file(), trf_path


def test_sort_pairings_for_compare_preserves_color_orientation() -> None:
    pairings = [["3", "1"], ["6", None], ["4", "2"]]

    normalized = sort_pairings_for_compare(pairings)

    assert normalized == [["3", "1"], ["4", "2"], ["6", None]]


def test_build_trf_initial_color_reads_trf_configuration() -> None:
    white_first = SimpleNamespace(
        x_section=SimpleNamespace(configuration=SimpleNamespace(first_round_color=True))
    )
    black_first = SimpleNamespace(
        x_section=SimpleNamespace(configuration=SimpleNamespace(first_round_color=False))
    )

    assert build_trf_initial_color(white_first) == "white"
    assert build_trf_initial_color(black_first) == "black"


def test_build_trf_initial_color_defaults_to_white_when_missing() -> None:
    assert build_trf_initial_color(SimpleNamespace()) == "white"


def test_parse_bbp_pairings_output_preserves_byes_and_colors() -> None:
    output_text = "\n".join(("6", "3 1", "4 2", "6 0"))

    pairings = parse_bbp_pairings_output(output_text)

    assert pairings == [["3", "1"], ["4", "2"], ["6", None]]


def test_parse_bbp_pairings_output_rejects_invalid_lines() -> None:
    output_text = "\n".join(("6", "1 3", "oops"))

    try:
        parse_bbp_pairings_output(output_text)
    except ValueError as exc:
        assert "invalid bbpPairings pairing line" in str(exc)
    else:
        raise AssertionError("expected invalid bbpPairings output to raise ValueError")


def test_parse_javafo_pairings_output_preserves_byes_and_colors() -> None:
    output_text = "\n".join(("3", "3 1", "4 2", "6 0"))

    pairings = parse_javafo_pairings_output(output_text)

    assert pairings == [["3", "1"], ["4", "2"], ["6", None]]


def test_parse_javafo_pairings_output_rejects_mismatched_pair_count() -> None:
    output_text = "\n".join(("2", "1 3", "4 2", "6 0"))

    try:
        parse_javafo_pairings_output(output_text)
    except ValueError as exc:
        assert "expected 2 pairs" in str(exc)
    else:
        raise AssertionError("expected invalid JaVaFo output to raise ValueError")


def test_discover_bbp_executable_prefers_explicit_env(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "bbpPairings.exe"
    executable.write_text("", encoding="utf-8")

    monkeypatch.setenv("SWISSPAIRING_BBP_EXECUTABLE", str(executable))
    monkeypatch.delenv("BBP_PAIRINGS_EXE", raising=False)

    assert discover_bbp_executable() == executable


def test_discover_javafo_jar_prefers_explicit_env(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    jar_path = tmp_path / "javafo.jar"
    jar_path.write_text("", encoding="utf-8")

    monkeypatch.setenv("SWISSPAIRING_JAVAFO_JAR", str(jar_path))
    monkeypatch.delenv("JAVAFO_JAR", raising=False)

    assert discover_javafo_jar() == jar_path


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


def test_build_trf_had_full_point_unplayed_round_by_player_id_detects_non_pab_full_points() -> None:
    def _result(token: str) -> SimpleNamespace:
        return SimpleNamespace(result=SimpleNamespace(value=token))

    trf = SimpleNamespace(
        player_sections=(
            SimpleNamespace(starting_number=1, results=(_result("F"),)),
            SimpleNamespace(starting_number=2, results=(_result("+"),)),
            SimpleNamespace(starting_number=3, results=(_result("U"),)),
            SimpleNamespace(starting_number=4, results=(_result("H"),)),
            SimpleNamespace(starting_number=5, results=(_result("1"),)),
        ),
    )

    flags = build_trf_had_full_point_unplayed_round_by_player_id(trf)

    assert flags == {1: True, 2: True, 3: False, 4: False, 5: False}


def test_build_trf_float_history_by_player_id_counts_only_positive_nonplayed_rounds() -> None:
    def _result(opponent_id: int, color: str, result: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=opponent_id,
            color=SimpleNamespace(value=color),
            result=SimpleNamespace(
                value=result,
                is_played=lambda: result in {"1", "=", "0", "W", "D", "L"},
            ),
        )

    def _points(round_result: SimpleNamespace) -> int:
        token = round_result.result.value
        if token in {"1", "W", "+", "F", "U"}:
            return 10
        if token in {"=", "D", "H"}:
            return 5
        return 0

    trf = SimpleNamespace(
        x_section=SimpleNamespace(
            number_of_rounds=3,
            scoring_point_system=SimpleNamespace(get_points_times_ten=_points),
        ),
        player_sections=(
            SimpleNamespace(
                starting_number=1,
                results=(
                    _result(2, "w", "1"),
                    _result(2, "w", "1"),
                ),
            ),
            SimpleNamespace(
                starting_number=2,
                results=(
                    _result(1, "b", "0"),
                    _result(1, "b", "0"),
                ),
            ),
            SimpleNamespace(
                starting_number=3,
                results=(
                    _result(0, "-", "F"),
                    _result(1, "b", "0"),
                ),
            ),
        ),
    )

    assert build_trf_float_history_by_player_id(trf) == {
        1: (FloatKind.NONE, FloatKind.DOWN),
        2: (FloatKind.NONE, FloatKind.UP),
        3: (FloatKind.DOWN, FloatKind.NONE),
    }


def test_build_trf_float_history_by_player_id_ignores_budapest_forfeit_loss_and_zero_byes() -> None:
    from py4swiss.trf import TrfParser

    trf = TrfParser.parse(
        Path(
            "benchmarks/fixtures/chess_results/"
            "budapest_spring_festival_2026_group_a_2200/"
            "budapest_spring_festival_2026_group_a_2200_r05.trf"
        )
    )

    history_by_id = build_trf_float_history_by_player_id(trf)

    assert history_by_id[82] == (
        FloatKind.NONE,
        FloatKind.NONE,
        FloatKind.NONE,
        FloatKind.UP,
    )
    assert history_by_id[96] == (
        FloatKind.NONE,
        FloatKind.NONE,
        FloatKind.NONE,
        FloatKind.NONE,
    )


def test_build_player_states_from_trf_preserves_forbidden_pairs_and_initial_markers() -> None:
    from py4swiss.trf import TrfParser

    trf = TrfParser.parse(Path("tests/golden/fixtures/dutch_d2_criterion_d.trf"))

    states = build_player_states_from_trf(trf)
    by_id = {state.player_id: state for state in states}
    left_id, right_id = next(iter(trf.x_section.forbidden_pairs))

    assert states
    assert str(right_id) in by_id[str(left_id)].forbidden_opponents
    assert str(left_id) in by_id[str(right_id)].forbidden_opponents
    assert len(by_id) == len(states)


def _lenient_player_line(
    *,
    starting_number: int,
    name: str,
    rating: int,
    points: str,
    result_blob: str,
) -> str:
    return (
        f"001 {starting_number:>4} {'':1}{'':>3} {name:<33}{rating:>5} {'':<3} {'':>11} "
        f"{'':<10} {points:>4} {'':>4}  {result_blob}"
    )


def test_normalize_lenient_trf16_text_handles_blank_rank_and_single_tokens() -> None:
    input_text = "\n".join(
        (
            _lenient_player_line(
                starting_number=1,
                name="Alpha",
                rating=2100,
                points="0.5",
                result_blob="H    2 b 1",
            ),
            _lenient_player_line(
                starting_number=2,
                name="Beta",
                rating=1900,
                points="0.0",
                result_blob="1 w 0    -",
            ),
            "XXR 2",
            "XXC white1",
        )
    )

    normalized = normalize_lenient_trf16_text(input_text)
    lines = normalized.splitlines()
    first = lines[0]
    second = lines[1]

    assert first[85:89] == "   1"
    assert second[85:89] == "   2"
    assert first[91:99] == "0000 - H"
    assert first[101:109] == "   2 b 1"
    assert second[91:99] == "   1 w 0"
    assert second[101:109] == "0000 - Z"


def test_normalize_lenient_trf16_text_rejects_unknown_result_token() -> None:
    input_text = "\n".join(
        (
            _lenient_player_line(
                starting_number=1,
                name="Alpha",
                rating=2100,
                points="0.5",
                result_blob="Q",
            ),
            "XXR 1",
            "XXC white1",
        )
    )

    try:
        normalize_lenient_trf16_text(input_text)
    except ValueError as exc:
        assert "unsupported TRF result token" in str(exc)
    else:
        raise AssertionError("expected unknown result token to raise ValueError")


def test_normalize_lenient_trf16_text_supports_bbp_next_round_xxr_mode() -> None:
    input_text = "\n".join(
        (
            _lenient_player_line(
                starting_number=1,
                name="Alpha",
                rating=2100,
                points="0.5",
                result_blob="H    2 b 1",
            ),
            _lenient_player_line(
                starting_number=2,
                name="Beta",
                rating=1900,
                points="0.0",
                result_blob="1 w 0    -",
            ),
            "XXR 2",
            "XXC white1",
        )
    )

    normalized = normalize_lenient_trf16_text(input_text, xxr_mode="bbp-next-round")
    lines = normalized.splitlines()

    assert lines[2] == "XXR 3"
    assert lines[0][91:99] == "0000 - H"
    assert lines[1][101:109] == "0000 - Z"


def test_normalize_lenient_trf16_text_rejects_unknown_xxr_mode() -> None:
    input_text = "\n".join(
        (
            _lenient_player_line(
                starting_number=1,
                name="Alpha",
                rating=2100,
                points="0.5",
                result_blob="H",
            ),
            "XXR 1",
            "XXC white1",
        )
    )

    try:
        normalize_lenient_trf16_text(input_text, xxr_mode="bad-mode")
    except ValueError as exc:
        assert "xxr_mode must be one of" in str(exc)
    else:
        raise AssertionError("expected unknown xxr_mode to raise ValueError")
