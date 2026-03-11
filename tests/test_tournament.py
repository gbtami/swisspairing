"""Tournament-level Dutch pairing tests."""

from __future__ import annotations

import pytest

import swisspairing.tournament as tournament
from swisspairing.exceptions import PairingError
from swisspairing.model import FloatAssignment, FloatKind, Pairing, PlayerState
from swisspairing.tournament import (
    pair_round_dutch,
    pair_round_dutch_exact,
    pair_round_dutch_fast,
)


def _player(
    *,
    player_id: str,
    pairing_no: int,
    score: int,
    had_full_point_bye: bool = False,
    had_full_point_unplayed_round: bool = False,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        pairing_no=pairing_no,
        score=score,
        had_full_point_bye=had_full_point_bye,
        had_full_point_unplayed_round=had_full_point_unplayed_round,
    )


def _normalized_pairs(result: tuple[Pairing, ...]) -> set[tuple[str, str | None]]:
    normalized: set[tuple[str, str | None]] = set()
    for pairing in result:
        if pairing.black_id is None:
            normalized.add((pairing.white_id, None))
            continue
        left, right = sorted((pairing.white_id, pairing.black_id))
        normalized.add((left, right))
    return normalized


def test_pair_round_dutch_empty_input() -> None:
    result = pair_round_dutch(())
    assert result.pairings == ()
    assert result.unpaired_ids == ()


def test_pair_round_dutch_exact_matches_small_exact_round() -> None:
    players = (
        _player(player_id="a1", pairing_no=1, score=3),
        _player(player_id="a2", pairing_no=2, score=3),
        _player(player_id="b1", pairing_no=3, score=2),
        _player(player_id="b2", pairing_no=4, score=2),
    )

    assert pair_round_dutch_exact(players) == pair_round_dutch(players)


def test_pair_round_dutch_exact_uses_bracket_size_when_no_explicit_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=0) for index in range(1, 14)
    )
    captured: dict[str, int | bool | None] = {}

    def fake_pair_bracket(
        bracket_players: tuple[PlayerState, ...],
        *,
        context: object | None = None,
        allow_bye: bool = True,
        sequential_search_max_players: int = 12,
        initial_color: str = "white",
        allow_heuristic_fallback: bool = True,
    ) -> tournament.PairingResult:
        del context, allow_bye, initial_color
        captured["count"] = len(bracket_players)
        captured["limit"] = sequential_search_max_players
        captured["allow_heuristic_fallback"] = allow_heuristic_fallback
        return tournament.PairingResult(
            pairings=tuple(
                Pairing(white_id=f"p{index}", black_id=f"p{index + 6}") for index in range(1, 7)
            )
            + (Pairing(white_id="p13", black_id=None),),
            unpaired_ids=(),
            float_assignments=(),
        )

    monkeypatch.setattr(tournament, "pair_bracket", fake_pair_bracket)

    result = pair_round_dutch_exact(players)

    assert result.unpaired_ids == ()
    assert captured == {
        "count": 13,
        "limit": 13,
        "allow_heuristic_fallback": False,
    }


def test_pair_round_dutch_exact_expands_medium_even_budget() -> None:
    players = (
        PlayerState(
            player_id="p1",
            pairing_no=1,
            score=3,
            opponents=frozenset({"p6", "p7", "p8", "p9", "p10"}),
        ),
        *tuple(
            PlayerState(player_id=f"p{index}", pairing_no=index, score=3) for index in range(2, 11)
        ),
    )

    result = pair_round_dutch_exact(players)

    assert result.unpaired_ids == ()
    p1_pair = next(
        pairing for pairing in result.pairings if "p1" in {pairing.white_id, pairing.black_id}
    )
    assert p1_pair.black_id is not None
    assert {p1_pair.white_id, p1_pair.black_id} & {"p2", "p3", "p4", "p5"}


def test_pair_round_dutch_exact_uses_immediate_next_bracket_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(player_id="t1", pairing_no=1, score=3),
        _player(player_id="t2", pairing_no=2, score=3),
        _player(player_id="t3", pairing_no=3, score=3),
        _player(player_id="m1", pairing_no=4, score=2),
        _player(player_id="m2", pairing_no=5, score=2),
        _player(player_id="m3", pairing_no=6, score=2),
        _player(player_id="b1", pairing_no=7, score=1),
        _player(player_id="b2", pairing_no=8, score=1),
    )
    observed: dict[str, tuple[int, ...] | None] = {}

    def fake_pair_bracket(
        bracket_players: tuple[PlayerState, ...],
        *,
        context: tournament.BracketContext | None = None,
        allow_bye: bool = True,
        sequential_search_max_players: int = 12,
        initial_color: str = "white",
        allow_heuristic_fallback: bool = True,
    ) -> tournament.PairingResult:
        del allow_bye, sequential_search_max_players, initial_color
        ids = tuple(player.player_id for player in bracket_players)
        if ids == ("t1", "t2", "t3"):
            assert context is not None
            assert context.next_bracket_key is not None
            by_id = {player.player_id: player for player in bracket_players}
            next_key = context.next_bracket_key((by_id["t3"],))
            observed["future_game_counts"] = (
                None if next_key is None else next_key.future_game_counts
            )
            return tournament.PairingResult(
                pairings=(Pairing(white_id="t1", black_id="t2"),),
                unpaired_ids=("t3",),
                float_assignments=(),
            )
        if ids == ("t3", "m1", "m2", "m3"):
            return tournament.PairingResult(
                pairings=(Pairing(white_id="t3", black_id="m1"),),
                unpaired_ids=("m2", "m3"),
                float_assignments=(),
            )
        if ids == ("m2", "m3", "b1", "b2"):
            return tournament.PairingResult(
                pairings=(
                    Pairing(white_id="m2", black_id="b1"),
                    Pairing(white_id="m3", black_id="b2"),
                ),
                unpaired_ids=(),
                float_assignments=(),
            )
        raise AssertionError(
            "unexpected bracket call: "
            f"ids={ids}, allow_heuristic_fallback={allow_heuristic_fallback}"
        )

    monkeypatch.setattr(tournament, "pair_bracket", fake_pair_bracket)

    result = pair_round_dutch_exact(players)

    assert result.unpaired_ids == ()
    assert observed["future_game_counts"] == ()


def test_pair_round_dutch_exact_handles_collapsed_tail_c8_key() -> None:
    scores = [70, 65, *([60] * 11), 55, *([50] * 3), *([45] * 4), 40, 35]
    players = tuple(
        PlayerState(player_id=str(index), pairing_no=index, score=score)
        for index, score in enumerate(scores, start=1)
    )

    result = pair_round_dutch_exact(players)

    assert result.unpaired_ids == ()


def test_pair_round_dutch_raises_when_last_bracket_cannot_be_fully_paired() -> None:
    blocked_players = (
        PlayerState(
            player_id="p1",
            pairing_no=1,
            score=2,
            opponents=frozenset({"p2"}),
        ),
        PlayerState(
            player_id="p2",
            pairing_no=2,
            score=2,
            opponents=frozenset({"p1"}),
        ),
    )
    with pytest.raises(PairingError):
        pair_round_dutch(blocked_players)


def test_pair_round_dutch_carries_mdps_between_scoregroups() -> None:
    players = (
        _player(player_id="a1", pairing_no=1, score=3),
        _player(player_id="a2", pairing_no=2, score=3),
        _player(player_id="a3", pairing_no=3, score=3),
        _player(player_id="b1", pairing_no=4, score=2),
        _player(player_id="b2", pairing_no=5, score=2),
        _player(player_id="b3", pairing_no=6, score=2),
        _player(player_id="b4", pairing_no=7, score=2),
    )
    result = pair_round_dutch(players)

    assert len(result.pairings) == 4
    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]
    assert len(bye_pairings) == 1

    game_player_ids = {
        player_id
        for pairing in result.pairings
        for player_id in (pairing.white_id, pairing.black_id)
        if player_id is not None
    }
    bye_player_ids = {pairing.white_id for pairing in bye_pairings}
    assert game_player_ids | bye_player_ids == {player.player_id for player in players}


def test_pair_round_dutch_respects_c2_for_last_bracket_bye() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, had_full_point_bye=True),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )
    result = pair_round_dutch(players)
    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]
    assert len(bye_pairings) == 1
    assert bye_pairings[0].white_id != "p1"


def test_pair_round_dutch_respects_c2_for_previous_full_point_unplayed_round() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, had_full_point_unplayed_round=True),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )

    result = pair_round_dutch(players)
    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]

    assert len(bye_pairings) == 1
    assert bye_pairings[0].white_id != "p1"


def test_pair_round_dutch_reports_float_assignments_for_cross_score_pairs_and_byes() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=1),
    )

    result = pair_round_dutch(players)

    assert result.float_assignments == (
        FloatAssignment(player_id="p1", kind=FloatKind.DOWN),
        FloatAssignment(player_id="p2", kind=FloatKind.UP),
        FloatAssignment(player_id="p3", kind=FloatKind.DOWN),
    )


def test_pair_round_dutch_uses_c8_lookahead_for_next_bracket_viability() -> None:
    players = (
        _player(player_id="t1", pairing_no=1, score=3, had_full_point_bye=True),
        _player(player_id="t2", pairing_no=2, score=3, had_full_point_bye=False),
        _player(player_id="t3", pairing_no=3, score=3, had_full_point_bye=True),
        _player(player_id="b1", pairing_no=4, score=2, had_full_point_bye=True),
        _player(player_id="b2", pairing_no=5, score=2, had_full_point_bye=True),
    )
    result = pair_round_dutch(players)
    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]
    assert len(bye_pairings) == 1
    assert bye_pairings[0].white_id == "t2"


def test_pair_round_dutch_is_deterministic() -> None:
    players = (
        _player(player_id="a1", pairing_no=1, score=3),
        _player(player_id="a2", pairing_no=2, score=3),
        _player(player_id="a3", pairing_no=3, score=3),
        _player(player_id="b1", pairing_no=4, score=2),
        _player(player_id="b2", pairing_no=5, score=2),
        _player(player_id="b3", pairing_no=6, score=2),
    )
    first = pair_round_dutch(players)
    second = pair_round_dutch(players)
    assert first == second


def test_pair_round_dutch_uses_initial_color_when_article_5_2_5_breaks_the_tie() -> None:
    players = (
        _player(player_id="odd", pairing_no=1, score=3),
        _player(player_id="even", pairing_no=2, score=3),
    )

    strict_result = pair_round_dutch(players, initial_color="black")
    fast_result = pair_round_dutch_fast(players, initial_color="black")

    assert strict_result.pairings == (Pairing(white_id="even", black_id="odd"),)
    assert strict_result.unpaired_ids == ()
    assert fast_result == strict_result


def test_pair_round_dutch_large_fixture_pairs_all_players_once() -> None:
    players = tuple(
        _player(
            player_id=f"p{index:03d}",
            pairing_no=index,
            score=4 if index <= 18 else 3 if index <= 36 else 2 if index <= 54 else 1,
        )
        for index in range(1, 61)
    )
    result = pair_round_dutch(players)

    assert len(result.pairings) == 30
    assert result.unpaired_ids == ()
    assert all(pairing.black_id is not None for pairing in result.pairings)

    paired_ids = {
        player_id
        for pairing in result.pairings
        for player_id in (pairing.white_id, pairing.black_id)
        if player_id is not None
    }
    assert paired_ids == {player.player_id for player in players}


def test_pair_round_dutch_very_large_fixture_pairs_all_players_once() -> None:
    players = tuple(
        _player(
            player_id=f"p{index:03d}",
            pairing_no=index,
            score=5
            if index <= 24
            else 4
            if index <= 48
            else 3
            if index <= 72
            else 2
            if index <= 96
            else 1,
        )
        for index in range(1, 121)
    )
    result = pair_round_dutch(players)

    assert len(result.pairings) == 60
    assert result.unpaired_ids == ()
    assert all(pairing.black_id is not None for pairing in result.pairings)


def test_pair_round_dutch_fast_cap_keeps_late_entry_fixture_parity() -> None:
    players = (
        PlayerState(
            player_id="1",
            pairing_no=1,
            score=20,
            opponents=frozenset({"2", "4", "7"}),
            color_history=("black", "white", "black"),
            had_full_point_bye=True,
            float_history=(FloatKind.NONE, FloatKind.DOWN),
        ),
        PlayerState(
            player_id="2",
            pairing_no=2,
            score=20,
            opponents=frozenset({"1", "3", "5", "6"}),
            color_history=("white", "black", "white", "black"),
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.NONE, FloatKind.UP),
        ),
        PlayerState(
            player_id="3",
            pairing_no=3,
            score=25,
            opponents=frozenset({"2", "5", "6", "7"}),
            color_history=("black", "white", "black", "white"),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.DOWN, FloatKind.DOWN),
        ),
        PlayerState(
            player_id="4",
            pairing_no=4,
            score=20,
            opponents=frozenset({"1", "5", "6"}),
            color_history=("white", "black", "black"),
            had_full_point_bye=True,
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.DOWN, FloatKind.NONE),
        ),
        PlayerState(
            player_id="5",
            pairing_no=5,
            score=35,
            opponents=frozenset({"2", "3", "4", "7"}),
            color_history=("black", "white", "white", "black"),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.UP, FloatKind.DOWN),
        ),
        PlayerState(
            player_id="6",
            pairing_no=6,
            score=20,
            opponents=frozenset({"2", "3", "4"}),
            color_history=("white", "black", "white"),
            had_full_point_bye=True,
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.NONE, FloatKind.NONE),
        ),
        PlayerState(
            player_id="7",
            pairing_no=7,
            score=20,
            opponents=frozenset({"1", "3", "5"}),
            color_history=("black", "white", "white"),
            had_full_point_bye=True,
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.NONE, FloatKind.UP),
        ),
        PlayerState(
            player_id="8",
            pairing_no=8,
            score=0,
            float_history=(FloatKind.DOWN, FloatKind.DOWN),
        ),
        PlayerState(
            player_id="9",
            pairing_no=9,
            score=0,
            float_history=(FloatKind.DOWN, FloatKind.DOWN),
        ),
        PlayerState(
            player_id="10",
            pairing_no=10,
            score=0,
            float_history=(FloatKind.DOWN, FloatKind.DOWN),
        ),
    )

    result = pair_round_dutch(players, sequential_search_max_players=6)

    assert _normalized_pairs(result.pairings) == {
        ("1", "3"),
        ("2", "8"),
        ("4", "7"),
        ("5", "6"),
        ("10", "9"),
    }


def test_pair_round_dutch_collapses_for_lower_score_bye_candidate() -> None:
    players = (
        PlayerState(
            player_id="1",
            pairing_no=1,
            score=20,
            opponents=frozenset({"2", "4"}),
            color_history=("white", "black"),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
        ),
        PlayerState(
            player_id="2",
            pairing_no=2,
            score=10,
            opponents=frozenset({"1", "5"}),
            color_history=("black", "white"),
            is_topscorer_or_opponent=True,
        ),
        PlayerState(
            player_id="3",
            pairing_no=3,
            score=20,
            opponents=frozenset({"4", "6"}),
            color_history=("white", "black"),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
            float_history=(FloatKind.NONE, FloatKind.DOWN),
        ),
        PlayerState(
            player_id="5",
            pairing_no=5,
            score=10,
            opponents=frozenset({"2", "6"}),
            color_history=("white", "black"),
        ),
        PlayerState(
            player_id="6",
            pairing_no=6,
            score=0,
            opponents=frozenset({"3", "5"}),
            color_history=("black", "white"),
            is_topscorer_or_opponent=True,
        ),
    )

    result = pair_round_dutch(players, sequential_search_max_players=6)

    assert _normalized_pairs(result.pairings) == {
        ("1", "5"),
        ("2", "3"),
        ("6", None),
    }


def test_pair_round_dutch_pause_like_state_keeps_lowest_score_bye() -> None:
    # Mid-event withdrawals are represented by omitting the paused player from the
    # waiting set while keeping the completed-round opponent history intact.
    players = (
        PlayerState(
            player_id="1",
            pairing_no=1,
            score=0,
            opponents=frozenset({"4"}),
            color_history=("white",),
            is_topscorer_or_opponent=True,
        ),
        PlayerState(
            player_id="2",
            pairing_no=2,
            score=10,
            opponents=frozenset({"5"}),
            color_history=("black",),
        ),
        PlayerState(
            player_id="3",
            pairing_no=3,
            score=20,
            opponents=frozenset({"6"}),
            color_history=("white",),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
        ),
        PlayerState(
            player_id="4",
            pairing_no=4,
            score=20,
            opponents=frozenset({"1"}),
            color_history=("black",),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
        ),
        PlayerState(
            player_id="5",
            pairing_no=5,
            score=10,
            opponents=frozenset({"2"}),
            color_history=("white",),
        ),
    )

    result = pair_round_dutch(players, sequential_search_max_players=6)

    assert _normalized_pairs(result.pairings) == {
        ("1", None),
        ("2", "3"),
        ("4", "5"),
    }
