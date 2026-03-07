"""Tournament-level Dutch pairing tests."""

from __future__ import annotations

import pytest

from swisspairing.exceptions import PairingError
from swisspairing.model import FloatKind, Pairing, PlayerState
from swisspairing.tournament import pair_round_dutch


def _player(
    *,
    player_id: str,
    pairing_no: int,
    score: int,
    had_full_point_bye: bool = False,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        pairing_no=pairing_no,
        score=score,
        had_full_point_bye=had_full_point_bye,
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
