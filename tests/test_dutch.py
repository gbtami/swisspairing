# pyright: reportPrivateUsage=false
"""Unit tests for the stage-1 Dutch bracket pairing."""

from __future__ import annotations

from typing import Any

import pytest

import swisspairing.dutch as dutch
from swisspairing.dutch import BracketContext, NextBracketKey, NextBracketLocalKey, pair_bracket
from swisspairing.exceptions import PairingError
from swisspairing.model import Color, FloatKind, Pairing, PlayerState


def _player(
    *,
    player_id: str,
    pairing_no: int,
    score: int,
    opponents: frozenset[str] | None = None,
    forbidden_opponents: frozenset[str] | None = None,
    color_history: tuple[Color, ...] = (),
    unplayed_games: int = 0,
    had_full_point_bye: bool = False,
    had_full_point_unplayed_round: bool = False,
    is_top_scorer: bool = False,
    is_topscorer_or_opponent: bool = False,
    float_history: tuple[FloatKind, ...] = (),
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        pairing_no=pairing_no,
        score=score,
        opponents=opponents or frozenset(),
        forbidden_opponents=forbidden_opponents or frozenset(),
        color_history=color_history,
        unplayed_games=unplayed_games,
        had_full_point_bye=had_full_point_bye,
        had_full_point_unplayed_round=had_full_point_unplayed_round,
        is_top_scorer=is_top_scorer,
        is_topscorer_or_opponent=is_topscorer_or_opponent,
        float_history=float_history,
    )


def _to_pairs(result_pairings: tuple[Pairing, ...]) -> set[tuple[str, str | None]]:
    return {(pairing.white_id, pairing.black_id) for pairing in result_pairings}


def _normalized_pairs(result_pairings: tuple[Pairing, ...]) -> set[tuple[str, str | None]]:
    normalized: set[tuple[str, str | None]] = set()
    for pairing in result_pairings:
        if pairing.black_id is None:
            normalized.add((pairing.white_id, None))
            continue
        left, right = sorted((pairing.white_id, pairing.black_id))
        normalized.add((left, right))
    return normalized


def test_pair_bracket_empty_returns_empty_result() -> None:
    result = pair_bracket(())
    assert result.pairings == ()
    assert result.unpaired_ids == ()


def test_pair_bracket_even_pairs_all_players_when_legal_edges_exist() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=2),
        _player(player_id="p4", pairing_no=4, score=2),
    )
    result = pair_bracket(players)

    assert len(result.pairings) == 2
    assert result.unpaired_ids == ()
    seen_ids = {pairing.white_id for pairing in result.pairings} | {
        pairing.black_id for pairing in result.pairings if pairing.black_id is not None
    }
    assert seen_ids == {"p1", "p2", "p3", "p4"}


def test_pair_bracket_prevents_rematch_under_c0401_rule_2() -> None:
    # C.04.1 rule 2: players shall not meet the same opponent twice.
    players = (
        _player(player_id="p1", pairing_no=1, score=3, opponents=frozenset({"p2"})),
        _player(player_id="p2", pairing_no=2, score=3, opponents=frozenset({"p1"})),
    )
    result = pair_bracket(players)
    assert result.pairings == ()
    assert result.unpaired_ids == ("p1", "p2")


def test_pair_bracket_prevents_forbidden_pair_under_c0402_organizer_constraint() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, forbidden_opponents=frozenset({"p2"})),
        _player(player_id="p2", pairing_no=2, score=3, forbidden_opponents=frozenset({"p1"})),
    )
    result = pair_bracket(players)
    assert result.pairings == ()
    assert result.unpaired_ids == ("p1", "p2")


def test_pair_bracket_blocks_same_absolute_pref_for_non_topscorers() -> None:
    # C.04.3 [C3]: non-topscorers with same absolute color preference cannot be paired.
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=3,
            color_history=("black", "white", "white"),
        ),
        _player(
            player_id="p2",
            pairing_no=2,
            score=3,
            color_history=("black", "white", "white"),
        ),
    )
    result = pair_bracket(players)
    assert result.pairings == ()
    assert result.unpaired_ids == ("p1", "p2")


def test_pair_bracket_allows_c3_exception_for_topscorers() -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=4,
            color_history=("black", "white", "white"),
            is_top_scorer=True,
        ),
        _player(
            player_id="p2",
            pairing_no=2,
            score=4,
            color_history=("black", "white", "white"),
        ),
    )
    result = pair_bracket(players)
    assert len(result.pairings) == 1
    assert result.unpaired_ids == ()


def test_pair_bracket_color_order_respects_absolute_white_preference() -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=3,
            color_history=("black", "black", "white"),
        ),
        _player(
            player_id="p2",
            pairing_no=2,
            score=3,
            color_history=(),
        ),
    )
    result = pair_bracket(players)
    assert len(result.pairings) == 1
    assert result.pairings[0].white_id == "p1"
    assert result.pairings[0].black_id == "p2"


def test_pair_bracket_color_order_respects_absolute_black_preference() -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=3,
            color_history=("white", "white", "white"),
        ),
        _player(
            player_id="p2",
            pairing_no=2,
            score=3,
            color_history=(),
        ),
    )
    result = pair_bracket(players)
    assert len(result.pairings) == 1
    assert result.pairings[0].white_id == "p2"
    assert result.pairings[0].black_id == "p1"


def test_pair_bracket_odd_excludes_previous_full_point_bye_candidates() -> None:
    # C.04.3 [C2]: repeated pairing-allocated byes are forbidden.
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=1, had_full_point_bye=True),
    )
    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)
    assert ("p3", None) not in pairs


def test_pair_bracket_odd_excludes_previous_full_point_unplayed_round_candidates() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(
            player_id="p3",
            pairing_no=3,
            score=1,
            had_full_point_unplayed_round=True,
        ),
    )

    result = pair_bracket(players)

    assert ("p3", None) not in _to_pairs(result.pairings)


def test_pair_bracket_odd_raises_when_no_legal_bye_candidate_exists() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, had_full_point_bye=True),
        _player(player_id="p2", pairing_no=2, score=2, had_full_point_bye=True),
        _player(player_id="p3", pairing_no=3, score=1, had_full_point_bye=True),
    )
    try:
        pair_bracket(players)
    except PairingError as exc:
        assert "C2" in str(exc)
    else:
        raise AssertionError("expected PairingError when no legal bye candidate exists")


def test_pair_bracket_odd_prioritizes_bye_score_before_quality_criteria() -> None:
    # C.04.3 [C5] outranks all quality criteria [C6]-[C21].
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=1),
    )
    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)
    assert ("p3", None) in pairs


def test_pair_bracket_publication_sort_is_deterministic() -> None:
    # C.04.2 section 3.6: pairings are sorted by highest-ranked paired player.
    players = (
        _player(player_id="p1", pairing_no=1, score=3, opponents=frozenset({"p2", "p3"})),
        _player(player_id="p2", pairing_no=2, score=3, opponents=frozenset({"p1", "p4"})),
        _player(player_id="p3", pairing_no=3, score=2, opponents=frozenset({"p1"})),
        _player(player_id="p4", pairing_no=4, score=2, opponents=frozenset({"p2"})),
    )
    result = pair_bracket(players)
    ranking_order = {player.player_id: player.pairing_no for player in players}
    publication_heads = [
        min((pairing.white_id, pairing.black_id), key=lambda player_id: ranking_order[player_id])
        for pairing in result.pairings
        if pairing.black_id is not None
    ]
    assert publication_heads == ["p1", "p2"]


def test_pair_bracket_is_deterministic_for_same_input() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=2),
        _player(player_id="p4", pairing_no=4, score=2),
    )
    first = pair_bracket(players)
    second = pair_bracket(players)
    assert first == second


def test_pair_bracket_uses_c8_next_bracket_validator() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )

    def validator(downfloaters: tuple[PlayerState, ...]) -> bool:
        # Reject candidates that downfloat p1.
        return all(player.player_id != "p1" for player in downfloaters)

    result = pair_bracket(players, context=BracketContext(next_bracket_validator=validator))
    pairs = _to_pairs(result.pairings)
    assert ("p1", None) not in pairs


def test_pair_bracket_uses_c8_next_bracket_key_tie_break() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=3),
    )

    def validator(_: tuple[PlayerState, ...]) -> bool:
        return True

    def next_bracket_key(
        downfloaters: tuple[PlayerState, ...],
    ) -> NextBracketKey:
        downfloater_id = downfloaters[0].player_id
        if downfloater_id == "p1":
            return NextBracketKey(local=NextBracketLocalKey(c5=-1))
        return NextBracketKey(local=NextBracketLocalKey(c7=(0,)))

    result = pair_bracket(
        players,
        context=BracketContext(
            next_bracket_validator=validator,
            next_bracket_key=next_bracket_key,
        ),
        allow_bye=False,
    )
    pairs = _to_pairs(result.pairings)
    assert ("p1", None) not in pairs


def test_pair_bracket_uses_c9_unplayed_games_for_bye_tie_break() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, unplayed_games=3),
        _player(player_id="p2", pairing_no=2, score=2, unplayed_games=1),
        _player(player_id="p3", pairing_no=3, score=2, unplayed_games=2),
    )
    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)
    assert ("p2", None) in pairs


def test_pair_bracket_uses_generation_order_when_criteria_are_equal() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, unplayed_games=0),
        _player(player_id="p2", pairing_no=2, score=2, unplayed_games=0),
        _player(player_id="p3", pairing_no=3, score=2, unplayed_games=0),
    )
    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)
    assert ("p3", None) in pairs


def test_pair_bracket_weighted_fallback_uses_generation_order_when_criteria_are_equal() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, unplayed_games=0),
        _player(player_id="p2", pairing_no=2, score=2, unplayed_games=0),
        _player(player_id="p3", pairing_no=3, score=2, unplayed_games=0),
    )
    result = pair_bracket(players, sequential_search_max_players=0)
    pairs = _to_pairs(result.pairings)
    assert ("p3", None) in pairs


def test_pair_bracket_uses_odd_sequence_order_after_c9_rejects_first_bye() -> None:
    players = (
        _player(player_id="p3", pairing_no=3, score=0, color_history=("black",), unplayed_games=1),
        _player(player_id="p4", pairing_no=4, score=0, color_history=("white",), unplayed_games=1),
        _player(player_id="p5", pairing_no=5, score=0, unplayed_games=2),
    )

    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)

    assert ("p3", "p5") in pairs
    assert ("p4", None) in pairs


def test_pair_bracket_weighted_fallback_uses_odd_sequence_order_after_c9_rejects_first_bye() -> (
    None
):
    players = (
        _player(player_id="p3", pairing_no=3, score=0, color_history=("black",), unplayed_games=1),
        _player(player_id="p4", pairing_no=4, score=0, color_history=("white",), unplayed_games=1),
        _player(player_id="p5", pairing_no=5, score=0, unplayed_games=2),
    )

    result = pair_bracket(players, sequential_search_max_players=0)
    pairs = _to_pairs(result.pairings)

    assert ("p3", "p5") in pairs
    assert ("p4", None) in pairs


def test_pair_bracket_large_weighted_final_bye_avoids_scanning_every_legal_bye(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=0) for index in range(1, 22)
    )

    call_count = 0
    original_solve_even_players = dutch._solve_even_players

    def wrapped_solve_even_players(*args: Any, **kwargs: Any):
        nonlocal call_count
        call_count += 1
        return original_solve_even_players(*args, **kwargs)

    monkeypatch.setattr(dutch, "_solve_even_players", wrapped_solve_even_players)

    result = dutch.pair_bracket(players, sequential_search_max_players=0)

    assert ("p21", None) in _to_pairs(result.pairings)
    assert call_count == 1


def test_pair_bracket_uses_c14_for_resident_downfloat_history() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, float_history=(FloatKind.DOWN,)),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )
    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)
    assert ("p1", None) not in pairs


def test_pair_bracket_uses_c15_for_mdp_opponent_upfloat_history() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=3, had_full_point_bye=True),
        _player(player_id="r2", pairing_no=2, score=3, float_history=(FloatKind.NONE,)),
        _player(player_id="r1", pairing_no=3, score=3, float_history=(FloatKind.UP,)),
    )
    result = pair_bracket(players, context=BracketContext(mdp_ids=frozenset({"m1"})))
    pairs = _to_pairs(result.pairings)

    # Best candidate assigns bye to r1 so the MDP plays r2 (without previous upfloat).
    assert ("r1", None) in pairs


def test_pair_bracket_small_homogeneous_uses_article42_transposition_order() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=3),
        _player(player_id="p4", pairing_no=4, score=3),
    )
    result = pair_bracket(players)
    pairs = _normalized_pairs(result.pairings)
    assert ("p1", "p3") in pairs
    assert ("p2", "p4") in pairs


def test_pair_bracket_small_homogeneous_uses_article43_exchanges_when_needed() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, opponents=frozenset({"p3", "p4"})),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=3),
        _player(player_id="p4", pairing_no=4, score=3, opponents=frozenset({"p1"})),
    )
    result = pair_bracket(players)
    pairs = _to_pairs(result.pairings)
    assert ("p1", "p2") in pairs
    assert ("p3", "p4") in pairs


def test_pair_bracket_without_bye_downfloats_on_odd_nonfinal_bracket() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=1),
    )
    result = pair_bracket(players, allow_bye=False)
    assert all(pairing.black_id is not None for pairing in result.pairings)
    assert result.unpaired_ids == ("p3",)


def test_pair_bracket_heterogeneous_limbo_follows_c7_preference() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=5),
        _player(player_id="m2", pairing_no=2, score=4),
        _player(player_id="m3", pairing_no=3, score=1),
        _player(player_id="r1", pairing_no=4, score=3),
    )
    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2", "m3"})),
        allow_bye=False,
    )
    pairs = _to_pairs(result.pairings)
    assert ("m1", "r1") in pairs or ("r1", "m1") in pairs
    assert result.unpaired_ids == ("m2", "m3")


def test_pair_bracket_large_heterogeneous_fallback_avoids_mdp_vs_mdp() -> None:
    mdp_ids = {f"m{i}" for i in range(1, 10)}
    residents = [f"r{i}" for i in range(1, 6)]
    players = tuple(
        _player(
            player_id=player_id,
            pairing_no=index,
            score=3 if player_id.startswith("m") else 2,
        )
        for index, player_id in enumerate([*sorted(mdp_ids), *residents], start=1)
    )
    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset(mdp_ids)),
        allow_bye=False,
    )

    assert len(result.pairings) == 5
    assert len(result.unpaired_ids) == 4
    assert set(result.unpaired_ids).issubset(mdp_ids)

    for pairing in result.pairings:
        assert pairing.black_id is not None
        assert not ({pairing.white_id, pairing.black_id} <= mdp_ids)


def test_pair_bracket_large_heterogeneous_fallback_prefers_lowest_bsn_residents() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=5),
        _player(player_id="m2", pairing_no=2, score=5),
        _player(player_id="m3", pairing_no=3, score=5),
        _player(player_id="r1", pairing_no=4, score=4),
        _player(player_id="r2", pairing_no=5, score=4),
        _player(player_id="r3", pairing_no=6, score=4),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2", "m3"})),
        allow_bye=False,
        sequential_search_max_players=2,
    )

    assert result.unpaired_ids == ()
    assert _normalized_pairs(result.pairings) == {("m1", "r1"), ("m2", "r2"), ("m3", "r3")}


def test_pair_bracket_small_odd_heterogeneous_exact_sequence_matches_resident_remainder_order() -> (
    None
):
    players = (
        _player(
            player_id="m1",
            pairing_no=58,
            score=40,
            color_history=("black", "black", "white", "white"),
        ),
        _player(
            player_id="r1",
            pairing_no=22,
            score=30,
            opponents=frozenset({"r2", "r3"}),
            color_history=("white", "black", "black", "white"),
            float_history=(FloatKind.UP, FloatKind.NONE),
        ),
        _player(
            player_id="r2",
            pairing_no=33,
            score=30,
            opponents=frozenset({"r1"}),
            color_history=("black", "white", "black", "black"),
        ),
        _player(
            player_id="r3",
            pairing_no=43,
            score=30,
            opponents=frozenset({"r1"}),
            color_history=("black", "white", "black", "white"),
        ),
        _player(
            player_id="r4",
            pairing_no=45,
            score=30,
            opponents=frozenset({"r5"}),
            color_history=("black", "white", "white", "black"),
        ),
        _player(
            player_id="r5",
            pairing_no=51,
            score=30,
            opponents=frozenset({"r4", "r6"}),
            color_history=("black", "black", "white", "white"),
        ),
        _player(
            player_id="r6",
            pairing_no=56,
            score=30,
            opponents=frozenset({"r5"}),
            color_history=("black", "white", "black", "black"),
        ),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1"})),
        allow_bye=False,
        sequential_search_max_players=8,
    )

    assert result.unpaired_ids == ("r5",)
    assert _to_pairs(result.pairings) == {("r2", "m1"), ("r4", "r1"), ("r6", "r3")}


def test_pair_bracket_large_homogeneous_fallback_stays_in_s1_s2_space() -> None:
    players = tuple(_player(player_id=f"p{i}", pairing_no=i, score=3) for i in range(1, 15))
    result = pair_bracket(players, sequential_search_max_players=2)

    assert result.unpaired_ids == ()
    top_half = {f"p{i}" for i in range(1, 8)}
    bottom_half = {f"p{i}" for i in range(8, 15)}

    for pairing in result.pairings:
        assert pairing.black_id is not None
        pair_ids = {pairing.white_id, pairing.black_id}
        assert len(pair_ids & top_half) == 1
        assert len(pair_ids & bottom_half) == 1


def test_pair_bracket_large_homogeneous_fallback_uses_one_exchange_when_needed() -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=3,
            opponents=frozenset({"p5", "p6", "p7", "p8"}),
        ),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=3),
        _player(player_id="p4", pairing_no=4, score=3),
        _player(player_id="p5", pairing_no=5, score=3),
        _player(player_id="p6", pairing_no=6, score=3),
        _player(player_id="p7", pairing_no=7, score=3),
        _player(player_id="p8", pairing_no=8, score=3),
    )

    result = pair_bracket(players, sequential_search_max_players=2)

    assert result.unpaired_ids == ()
    p1_pair = next(
        pairing for pairing in result.pairings if "p1" in {pairing.white_id, pairing.black_id}
    )
    assert p1_pair.black_id is not None
    assert {p1_pair.white_id, p1_pair.black_id} & {"p2", "p3", "p4"}
