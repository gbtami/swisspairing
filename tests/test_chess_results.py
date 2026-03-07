from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from swisspairing.benchmarking import (
    build_pythonpath_env,
    discover_bbp_executable,
    py4swiss_runtime_probe,
)
from swisspairing.chess_results import (
    ChessResultsPairingRecord,
    ChessResultsPlayerRecord,
    ChessResultsRoundRecord,
    ChessResultsTournamentRecord,
    build_chess_results_snapshot,
    parse_chess_results_points,
    published_pairings_for_round,
)

RUNNER_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "reference_compare_case_runner.py"
)


def _build_runner_env() -> dict[str, str]:
    return build_pythonpath_env(Path(__file__).parent.parent / "src")


def _has_py4swiss_runtime() -> bool:
    ok, _ = py4swiss_runtime_probe(sys.executable, env=_build_runner_env())
    return ok


def _bbp_executable() -> Path:
    discovered = discover_bbp_executable()
    if discovered is None:
        return Path("~/bbpPairings/bbpPairings.exe").expanduser()
    return discovered


def _has_bbp_executable() -> bool:
    return _bbp_executable().exists()


def _run_reference_compare(trf_path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--trf",
            str(trf_path),
            "--warmup",
            "0",
            "--repeats",
            "1",
            "--swisspairing-mode",
            "fast",
            "--bbp-executable",
            str(_bbp_executable()),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        env=_build_runner_env(),
    )
    return json.loads(completed.stdout)


def _normalize_manifest_pairings(
    raw_pairings: list[list[str | None]],
) -> tuple[tuple[str, str | None], ...]:
    normalized: list[tuple[str, str | None]] = []
    for left, right in raw_pairings:
        if left is None:
            raise AssertionError("published pairings must always include a first player id")
        normalized.append((left, right))
    normalized.sort(key=lambda pair: (pair[1] is None, pair[0], pair[1] or ""))
    return tuple(normalized)


def _player(
    starting_number: int,
    *,
    rating: int,
) -> ChessResultsPlayerRecord:
    return ChessResultsPlayerRecord(
        starting_number=starting_number,
        title="",
        name=f"Player {starting_number}",
        fide_id="",
        federation="",
        rating=rating,
        sex="",
    )


def test_parse_chess_results_points_handles_half_points() -> None:
    assert parse_chess_results_points("") == 0
    assert parse_chess_results_points("0") == 0
    assert parse_chess_results_points("1") == 10
    assert parse_chess_results_points("2\u00bd") == 25
    assert parse_chess_results_points("\u00bd") == 5


def test_published_pairings_for_round_normalizes_games_and_byes() -> None:
    round_record = ChessResultsRoundRecord(
        round_number=3,
        label="Round 3 on 2026/03/01 at 17:00",
        pairings=(
            ChessResultsPairingRecord(
                round_number=3,
                board_number=1,
                white_starting_number=9,
                white_name="Player 9",
                white_rating=2400,
                white_points_times_ten=20,
                result_text="1 - 0",
                black_points_times_ten=20,
                black_name="Player 1",
                black_rating=2500,
                black_starting_number=1,
                seat_kind="game",
            ),
            ChessResultsPairingRecord(
                round_number=3,
                board_number=2,
                white_starting_number=10,
                white_name="Player 10",
                white_rating=2300,
                white_points_times_ten=0,
                result_text="1",
                black_points_times_ten=None,
                black_name="bye",
                black_rating=None,
                black_starting_number=None,
                seat_kind="bye",
            ),
        ),
    )

    assert published_pairings_for_round(round_record) == (("1", "9"), ("10", None))


def test_build_chess_results_snapshot_reconstructs_game_bye_and_not_paired() -> None:
    tournament = ChessResultsTournamentRecord(
        name="Sample Event",
        last_update="Last update 2026-03-07",
        players=(
            _player(1, rating=2500),
            _player(2, rating=2400),
            _player(3, rating=2300),
            _player(4, rating=2200),
        ),
        rounds=(
            ChessResultsRoundRecord(
                round_number=1,
                label="Round 1 on 2026/03/01 at 12:00",
                pairings=(
                    ChessResultsPairingRecord(
                        round_number=1,
                        board_number=1,
                        white_starting_number=1,
                        white_name="Player 1",
                        white_rating=2500,
                        white_points_times_ten=0,
                        result_text="1 - 0",
                        black_points_times_ten=0,
                        black_name="Player 2",
                        black_rating=2400,
                        black_starting_number=2,
                        seat_kind="game",
                    ),
                    ChessResultsPairingRecord(
                        round_number=1,
                        board_number=2,
                        white_starting_number=3,
                        white_name="Player 3",
                        white_rating=2300,
                        white_points_times_ten=0,
                        result_text="1",
                        black_points_times_ten=None,
                        black_name="bye",
                        black_rating=None,
                        black_starting_number=None,
                        seat_kind="bye",
                    ),
                    ChessResultsPairingRecord(
                        round_number=1,
                        board_number=3,
                        white_starting_number=4,
                        white_name="Player 4",
                        white_rating=2200,
                        white_points_times_ten=0,
                        result_text="0",
                        black_points_times_ten=None,
                        black_name="not paired",
                        black_rating=None,
                        black_starting_number=None,
                        seat_kind="not_paired",
                    ),
                ),
            ),
            ChessResultsRoundRecord(
                round_number=2,
                label="Round 2 on 2026/03/01 at 17:00",
                pairings=(
                    ChessResultsPairingRecord(
                        round_number=2,
                        board_number=1,
                        white_starting_number=1,
                        white_name="Player 1",
                        white_rating=2500,
                        white_points_times_ten=10,
                        result_text="\u00bd - \u00bd",
                        black_points_times_ten=10,
                        black_name="Player 3",
                        black_rating=2300,
                        black_starting_number=3,
                        seat_kind="game",
                    ),
                    ChessResultsPairingRecord(
                        round_number=2,
                        board_number=2,
                        white_starting_number=2,
                        white_name="Player 2",
                        white_rating=2400,
                        white_points_times_ten=0,
                        result_text="0",
                        black_points_times_ten=None,
                        black_name="not paired",
                        black_rating=None,
                        black_starting_number=None,
                        seat_kind="not_paired",
                    ),
                    ChessResultsPairingRecord(
                        round_number=2,
                        board_number=3,
                        white_starting_number=4,
                        white_name="Player 4",
                        white_rating=2200,
                        white_points_times_ten=0,
                        result_text="0",
                        black_points_times_ten=None,
                        black_name="not paired",
                        black_rating=None,
                        black_starting_number=None,
                        seat_kind="not_paired",
                    ),
                ),
            ),
        ),
        first_round_color_white1=True,
    )

    snapshot = build_chess_results_snapshot(tournament, target_round_number=2)

    assert snapshot.target_round_number == 2
    assert [player.player.starting_number for player in snapshot.players] == [1, 2, 3, 4]

    player_one = snapshot.players[0]
    player_two = snapshot.players[1]
    player_three = snapshot.players[2]
    player_four = snapshot.players[3]

    assert player_one.points_times_ten == 10
    assert player_two.points_times_ten == 0
    assert player_three.points_times_ten == 10
    assert player_four.points_times_ten == 0

    assert player_one.rank == 1
    assert player_three.rank == 2
    assert player_two.rank == 3
    assert player_four.rank == 4

    assert tuple(
        (token.opponent_starting_number, token.color, token.result)
        for token in player_one.results
    ) == (
        (2, "w", "1"),
    )
    assert tuple(
        (token.opponent_starting_number, token.color, token.result)
        for token in player_two.results
    ) == (
        (1, "b", "0"),
    )
    assert tuple(
        (token.opponent_starting_number, token.color, token.result)
        for token in player_three.results
    ) == (
        (0, "-", "U"),
    )
    assert tuple(
        (token.opponent_starting_number, token.color, token.result)
        for token in player_four.results
    ) == (
        (0, "-", "Z"),
    )


def test_checked_in_aeroflot_manifest_references_existing_trfs() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "benchmarks"
        / "fixtures"
        / "chess_results"
        / "aeroflot_open_2026"
        / "published_pairings.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    rounds = payload["rounds"]
    assert len(rounds) == 9
    assert payload["first_round_color"] == "black1"

    for round_entry in rounds:
        trf_path = manifest_path.parent / round_entry["trf"]
        assert trf_path.exists()


@pytest.mark.skipif(
    not (_has_py4swiss_runtime() and _has_bbp_executable()),
    reason=(
        "active Python interpreter or bbpPairings runtime unavailable for Aeroflot "
        "reference checks"
    ),
)
@pytest.mark.parametrize("round_number", [2, 3])
def test_aeroflot_fast_pairing_matches_published_round(round_number: int) -> None:
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "benchmarks"
        / "fixtures"
        / "chess_results"
        / "aeroflot_open_2026"
        / "published_pairings.json"
    )
    payload = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    round_entry = next(item for item in payload["rounds"] if item["round_number"] == round_number)

    compare = _run_reference_compare(manifest_path.parent / round_entry["trf"])
    swisspairing = cast(dict[str, Any], compare["swisspairing"])
    assert isinstance(swisspairing, dict)
    pairings = cast(list[list[str | None]], swisspairing["pairings"])
    assert isinstance(pairings, list)
    assert _normalize_manifest_pairings(pairings) == _normalize_manifest_pairings(
        round_entry["published_pairings"]
    )
