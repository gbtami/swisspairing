# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from py4swiss.engines.common.float import Float as PyFloat
from py4swiss.engines.dutch.player import get_player_infos_from_trf
from py4swiss.trf import TrfParser

from swisspairing.benchmarking import (
    build_pythonpath_env,
    build_trf_had_full_point_unplayed_round_by_player_id,
    build_trf_unplayed_games_by_player_id,
    discover_bbp_executable,
    py4swiss_runtime_probe,
)
from swisspairing.chess_results import (
    ChessResultsPairingRecord,
    ChessResultsPlayerRecord,
    ChessResultsRoundRecord,
    ChessResultsTournamentRecord,
    _validate_round_player_numbers,
    build_chess_results_float_history,
    build_chess_results_snapshot,
    parse_chess_results_points,
    parse_chess_results_round,
    published_pairings_for_round,
)
from swisspairing.dutch import BracketContext, pair_bracket
from swisspairing.model import FloatKind, PlayerState
from swisspairing.tournament import _group_residents_by_score

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
        if right is None:
            normalized.append((left, None))
            continue
        first, second = sorted((left, right))
        normalized.append((first, second))
    normalized.sort(key=lambda pair: (pair[1] is None, pair[0], pair[1] or ""))
    return tuple(normalized)


def _aeroflot_manifest_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "benchmarks"
        / "fixtures"
        / "chess_results"
        / "aeroflot_open_2026"
        / "published_pairings.json"
    )


def _load_aeroflot_manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_aeroflot_manifest_path().read_text(encoding="utf-8")))


def _aeroflot_round_entry(round_number: int) -> dict[str, Any]:
    payload = _load_aeroflot_manifest()
    return cast(
        dict[str, Any],
        next(item for item in payload["rounds"] if item["round_number"] == round_number),
    )


def _aeroflot_states_for_round(round_number: int) -> tuple[PlayerState, ...]:
    manifest_path = _aeroflot_manifest_path()
    round_entry = _aeroflot_round_entry(round_number)
    trf = TrfParser.parse(manifest_path.parent / cast(str, round_entry["trf"]))
    py4swiss_players = get_player_infos_from_trf(trf)
    top_ids = {player.id for player in py4swiss_players if player.top_scorer}
    forbidden_map: dict[int, set[int]] = {}
    for left_id, right_id in trf.x_section.forbidden_pairs:
        forbidden_map.setdefault(left_id, set()).add(right_id)
        forbidden_map.setdefault(right_id, set()).add(left_id)
    unplayed_games_by_id = build_trf_unplayed_games_by_player_id(trf)
    full_point_unplayed_round_by_id = build_trf_had_full_point_unplayed_round_by_player_id(trf)

    def to_float_kind(float_value: PyFloat) -> FloatKind:
        if float_value == PyFloat.UP:
            return FloatKind.UP
        if float_value == PyFloat.DOWN:
            return FloatKind.DOWN
        return FloatKind.NONE

    states = tuple(
        PlayerState(
            player_id=str(player.id),
            pairing_no=player.number,
            score=player.points_with_acceleration,
            opponents=frozenset(str(opponent_id) for opponent_id in player.opponents),
            forbidden_opponents=frozenset(
                str(opponent_id) for opponent_id in forbidden_map.get(player.id, set())
            ),
            color_history=tuple("white" if is_white else "black" for is_white in player.colors),
            unplayed_games=unplayed_games_by_id.get(player.id, 0),
            had_full_point_bye=player.bye_received,
            had_full_point_unplayed_round=full_point_unplayed_round_by_id.get(player.id, False),
            is_top_scorer=player.top_scorer,
            is_topscorer_or_opponent=player.top_scorer or bool(player.opponents & top_ids),
            float_history=(
                to_float_kind(player.float_2),
                to_float_kind(player.float_1),
            ),
        )
        for player in py4swiss_players
    )
    return tuple(sorted(states, key=lambda player: (-player.score, player.pairing_no)))


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


def test_parse_chess_results_round_handles_legacy_compact_layout() -> None:
    round_record = parse_chess_results_round(
        (
            ("Round 2 on 2026/03/01 at 17:00",),
            (
                "Bo.",
                "No.",
                "",
                "",
                "White",
                "Rtg",
                "Pts.",
                "Result ",
                "Pts.",
                "",
                "Black",
                "Rtg",
                "",
                "No.",
            ),
            (
                "1",
                "7",
                "            ",
                "GM",
                "Alpha, A",
                "2500",
                "1",
                "\u00bd - \u00bd",
                "1",
                "IM",
                "Beta, B",
                "2400",
                "            ",
                "19",
            ),
        )
    )

    assert round_record.round_number == 2
    assert round_record.pairings == (
        ChessResultsPairingRecord(
            round_number=2,
            board_number=1,
            white_starting_number=7,
            white_name="Alpha, A",
            white_rating=2500,
            white_points_times_ten=10,
            result_text="\u00bd - \u00bd",
            black_points_times_ten=10,
            black_name="Beta, B",
            black_rating=2400,
            black_starting_number=19,
            seat_kind="game",
        ),
    )


def test_parse_chess_results_round_handles_prague_federation_layout() -> None:
    round_record = parse_chess_results_round(
        (
            ("Round 1 on 2026/02/26 at 15.00",),
            (
                "Bo.",
                "No.",
                "",
                "",
                "White",
                "FED",
                "Rtg",
                "Pts.",
                "Result ",
                "Pts.",
                "",
                "Black",
                "FED",
                "Rtg",
                "",
                "No.",
            ),
            (
                "1",
                "1",
                "            ",
                "GM",
                "Moroni, Luca Jr",
                "ITA",
                "2563",
                "0",
                "1 - 0",
                "0",
                "CM",
                "Gokturk, Murat Kutay",
                "TUR",
                "2047",
                "            ",
                "177",
            ),
        )
    )

    assert round_record.round_number == 1
    assert round_record.pairings == (
        ChessResultsPairingRecord(
            round_number=1,
            board_number=1,
            white_starting_number=1,
            white_name="Moroni, Luca Jr",
            white_rating=2563,
            white_points_times_ten=0,
            result_text="1 - 0",
            black_points_times_ten=0,
            black_name="Gokturk, Murat Kutay",
            black_rating=2047,
            black_starting_number=177,
            seat_kind="game",
        ),
    )


def test_validate_round_player_numbers_rejects_paginated_starting_list_inputs() -> None:
    players = (_player(1, rating=2500), _player(2, rating=2400))
    rounds = (
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
                    black_name="Player 3",
                    black_rating=2300,
                    black_starting_number=3,
                    seat_kind="game",
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="Show complete list|zeilen=99999"):
        _validate_round_player_numbers(players=players, rounds=rounds)


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
        (token.opponent_starting_number, token.color, token.result) for token in player_one.results
    ) == ((2, "w", "1"),)
    assert tuple(
        (token.opponent_starting_number, token.color, token.result) for token in player_two.results
    ) == ((1, "b", "0"),)
    assert tuple(
        (token.opponent_starting_number, token.color, token.result)
        for token in player_three.results
    ) == ((0, "-", "U"),)
    assert tuple(
        (token.opponent_starting_number, token.color, token.result) for token in player_four.results
    ) == ((0, "-", "Z"),)


def test_build_chess_results_float_history_covers_forfeit_and_non_game_downfloats() -> None:
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
                        result_text="+ - -",
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
                        result_text="1",
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
                        result_text="1 - 0",
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
                        white_points_times_ten=10,
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

    assert build_chess_results_float_history(snapshot) == {
        1: (FloatKind.DOWN,),
        2: (FloatKind.NONE,),
        3: (FloatKind.DOWN,),
        4: (FloatKind.DOWN,),
    }


def test_checked_in_aeroflot_manifest_references_existing_trfs() -> None:
    manifest_path = _aeroflot_manifest_path()
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
        "active Python interpreter or bbpPairings runtime unavailable for Aeroflot reference checks"
    ),
)
@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_aeroflot_fast_pairing_matches_published_round(round_number: int) -> None:
    manifest_path = _aeroflot_manifest_path()
    round_entry = _aeroflot_round_entry(round_number)

    compare = _run_reference_compare(manifest_path.parent / cast(str, round_entry["trf"]))
    swisspairing = cast(dict[str, Any], compare["swisspairing"])
    assert isinstance(swisspairing, dict)
    pairings = cast(list[list[str | None]], swisspairing["pairings"])
    assert isinstance(pairings, list)
    assert _normalize_manifest_pairings(pairings) == _normalize_manifest_pairings(
        round_entry["published_pairings"]
    )


@pytest.mark.skipif(
    not (_has_py4swiss_runtime() and _has_bbp_executable()),
    reason=(
        "active Python interpreter or bbpPairings runtime unavailable for Aeroflot reference checks"
    ),
)
@pytest.mark.parametrize(
    ("round_number", "published_non_game_count"),
    [
        (4, 3),
        (6, 5),
        (7, 7),
        (8, 9),
        (9, 11),
    ],
)
def test_aeroflot_later_rounds_are_engine_consensus_vs_published_non_game_cases(
    round_number: int,
    published_non_game_count: int,
) -> None:
    manifest_path = _aeroflot_manifest_path()
    round_entry = _aeroflot_round_entry(round_number)

    compare = _run_reference_compare(manifest_path.parent / cast(str, round_entry["trf"]))
    swisspairing = cast(dict[str, Any], compare["swisspairing"])
    py4swiss = cast(dict[str, Any], compare["py4swiss"])
    bbp = cast(dict[str, Any], compare["bbp"])

    swiss_pairings = _normalize_manifest_pairings(
        cast(list[list[str | None]], swisspairing["pairings"])
    )
    py4swiss_pairings = _normalize_manifest_pairings(
        cast(list[list[str | None]], py4swiss["pairings"])
    )
    bbp_pairings = _normalize_manifest_pairings(cast(list[list[str | None]], bbp["pairings"]))
    published_pairings = _normalize_manifest_pairings(round_entry["published_pairings"])

    assert swiss_pairings == py4swiss_pairings
    assert swiss_pairings == bbp_pairings
    assert swiss_pairings != published_pairings
    assert sum(int(right is None) for _, right in published_pairings) == published_non_game_count


@pytest.mark.skipif(
    not _has_py4swiss_runtime(),
    reason="active Python interpreter unavailable for Aeroflot bracket checks",
)
def test_aeroflot_round_5_score_20_bracket_refines_weighted_downfloater() -> None:
    scoregroups = _group_residents_by_score(_aeroflot_states_for_round(5))

    result = pair_bracket(
        scoregroups[4],
        allow_bye=False,
        sequential_search_max_players=6,
    )

    assert result.unpaired_ids == ("160",)


@pytest.mark.skipif(
    not _has_py4swiss_runtime(),
    reason="active Python interpreter unavailable for Aeroflot bracket checks",
)
def test_aeroflot_round_5_score_10_bracket_refines_single_mdp_partner() -> None:
    scoregroups = _group_residents_by_score(_aeroflot_states_for_round(5))
    mdp = next(player for player in scoregroups[5] if player.pairing_no == 161)
    bracket_players = tuple(
        sorted(
            (mdp, *scoregroups[6]),
            key=lambda player: (-player.score, player.pairing_no),
        )
    )

    result = pair_bracket(
        bracket_players,
        context=BracketContext(mdp_ids=frozenset({mdp.player_id})),
        allow_bye=False,
        sequential_search_max_players=6,
    )

    paired_ids = {
        frozenset({pairing.white_id, pairing.black_id})
        for pairing in result.pairings
        if pairing.black_id is not None
    }
    assert result.unpaired_ids == ("158",)
    assert frozenset({"161", "63"}) in paired_ids


@pytest.mark.skipif(
    not (_has_py4swiss_runtime() and _has_bbp_executable()),
    reason=(
        "active Python interpreter or bbpPairings runtime unavailable for Aeroflot reference checks"
    ),
)
def test_aeroflot_fast_round_5_matches_bbp_reference() -> None:
    manifest_path = _aeroflot_manifest_path()
    round_entry = _aeroflot_round_entry(5)

    compare = _run_reference_compare(manifest_path.parent / round_entry["trf"])

    assert compare["pairings_equal_vs_bbp"] is True
