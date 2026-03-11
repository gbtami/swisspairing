# pyright: reportPrivateUsage=false
"""Unit tests for the stage-1 Dutch bracket pairing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

import swisspairing.dutch as dutch
from swisspairing.dutch import (
    BracketContext,
    NextBracketKey,
    NextBracketLocalKey,
    pair_bracket,
    pair_bracket_exact,
)
from swisspairing.exceptions import PairingError
from swisspairing.model import Color, FloatAssignment, FloatKind, Pairing, PlayerState


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


def test_pair_bracket_exact_matches_small_exact_bracket() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=2),
        _player(player_id="p4", pairing_no=4, score=2),
    )

    assert pair_bracket_exact(players) == pair_bracket(players)


def test_pair_bracket_exact_raises_when_current_solver_needs_heuristic_fallback() -> None:
    players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=score)
        for index, score in enumerate(
            [65, *([60] * 11), 55, *([50] * 3), *([45] * 4), 40, 35],
            start=1,
        )
    )
    with pytest.raises(PairingError, match="heuristic fallback"):
        pair_bracket_exact(
            players,
            context=BracketContext(mdp_ids=frozenset({"p1", "p2"})),
            allow_bye=True,
        )


def test_pair_bracket_exact_ignores_public_sequence_cap_by_default() -> None:
    players = tuple(
        _player(
            player_id=f"p{index}",
            pairing_no=index,
            score=3 if index <= 9 else 2,
        )
        for index in range(1, 14)
    )
    context = BracketContext(mdp_ids=frozenset({f"p{index}" for index in range(1, 10)}))

    exact_result = pair_bracket_exact(
        players,
        context=context,
        allow_bye=False,
    )
    explicit_result = pair_bracket(
        players,
        context=context,
        allow_bye=False,
        sequential_search_max_players=13,
        allow_heuristic_fallback=False,
    )

    assert exact_result == explicit_result


def test_pair_bracket_exact_expands_medium_even_budget_without_weighted_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=3,
            opponents=frozenset({"p6", "p7", "p8", "p9", "p10"}),
        ),
        *tuple(_player(player_id=f"p{index}", pairing_no=index, score=3) for index in range(2, 11)),
    )

    def fail_weighted_fallback(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("exact mode should not use the homogeneous weighted fallback")

    monkeypatch.setattr(
        dutch,
        "_solve_homogeneous_even_players_via_bipartite_fallback",
        fail_weighted_fallback,
    )

    result = pair_bracket_exact(players)

    assert result.unpaired_ids == ()
    p1_pair = next(
        pairing for pairing in result.pairings if "p1" in {pairing.white_id, pairing.black_id}
    )
    assert p1_pair.black_id is not None
    assert {p1_pair.white_id, p1_pair.black_id} & {"p2", "p3", "p4", "p5"}


def test_pair_bracket_exact_solves_large_homogeneous_even_zero_exchange_optimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = tuple(
        _player(
            player_id=f"p{index}",
            pairing_no=index,
            score=3,
            color_history=("white",) if index <= 7 else ("black",),
        )
        for index in range(1, 15)
    )

    def fail_weighted_fallback(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("exact mode should not use the homogeneous weighted fallback")

    monkeypatch.setattr(
        dutch,
        "_solve_homogeneous_even_players_via_bipartite_fallback",
        fail_weighted_fallback,
    )

    result = pair_bracket_exact(players)

    assert result.unpaired_ids == ()
    assert len(result.pairings) == 7


def test_pair_bracket_exact_solves_large_single_mdp_even_bracket() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=4),
        *tuple(_player(player_id=f"p{index}", pairing_no=index, score=3) for index in range(2, 49)),
    )

    result = pair_bracket_exact(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1"})),
        allow_bye=False,
    )

    assert result.unpaired_ids == ()
    mdp_pair = next(
        pairing for pairing in result.pairings if "m1" in {pairing.white_id, pairing.black_id}
    )
    assert mdp_pair.black_id is not None


def test_pair_bracket_exact_single_mdp_even_honors_next_bracket_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(
            player_id="m",
            pairing_no=1,
            score=2,
            forbidden_opponents=frozenset({"c", "d", "e"}),
        ),
        _player(
            player_id="a",
            pairing_no=2,
            score=1,
            forbidden_opponents=frozenset({"c", "d", "e"}),
        ),
        _player(
            player_id="b",
            pairing_no=3,
            score=1,
            forbidden_opponents=frozenset({"c", "d", "e"}),
        ),
        _player(
            player_id="c",
            pairing_no=4,
            score=1,
            forbidden_opponents=frozenset({"a", "b", "m"}),
        ),
        _player(
            player_id="d",
            pairing_no=5,
            score=1,
            forbidden_opponents=frozenset({"a", "b", "m"}),
        ),
        _player(
            player_id="e",
            pairing_no=6,
            score=1,
            forbidden_opponents=frozenset({"a", "b", "m"}),
        ),
    )
    by_id = {player.player_id: player for player in players}

    def fake_solve_even(
        even_players: Sequence[PlayerState],
        *,
        context: BracketContext,
        sequential_search_max_players: int = 12,
        allow_heuristic_fallback: bool = True,
    ) -> dutch._EvenPairingInternal:
        del context, sequential_search_max_players, allow_heuristic_fallback
        ids = tuple(player.player_id for player in even_players)
        if ids == ("a", "c", "d", "e"):
            return dutch._EvenPairingInternal(
                pairings=((by_id["a"], by_id["e"]),),
                unresolved=(by_id["c"], by_id["d"]),
            )
        if ids == ("b", "c", "d", "e"):
            return dutch._EvenPairingInternal(
                pairings=((by_id["b"], by_id["c"]),),
                unresolved=(by_id["d"], by_id["e"]),
            )
        raise AssertionError(f"unexpected remainder ids: {ids}")

    monkeypatch.setattr(dutch, "_solve_even_players", fake_solve_even)

    def validator(downfloaters: tuple[PlayerState, ...]) -> bool:
        return tuple(player.player_id for player in downfloaters) == ("c", "d")

    result = dutch._solve_even_players_via_single_mdp_exact(
        players,
        context=BracketContext(
            mdp_ids=frozenset({"m"}),
            next_bracket_validator=validator,
        ),
    )

    assert result is not None
    assert tuple(player.player_id for player in result.unresolved) == ("c", "d")
    assert {frozenset({left.player_id, right.player_id}) for left, right in result.pairings} == {
        frozenset({"m", "b"}),
        frozenset({"a", "e"}),
    }


def test_pair_bracket_exact_odd_scan_stops_after_lowest_score_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=6),
        *tuple(_player(player_id=f"p{index}", pairing_no=index, score=5) for index in range(2, 8)),
        *tuple(_player(player_id=f"p{index}", pairing_no=index, score=4) for index in range(8, 15)),
        *tuple(
            _player(player_id=f"p{index}", pairing_no=index, score=3) for index in range(15, 21)
        ),
        _player(player_id="p21", pairing_no=21, score=2),
    )
    full_ids = frozenset(player.player_id for player in players)
    seen_downfloaters: list[str] = []
    original_solve_even = dutch._solve_even_players

    def wrapped_solve_even(
        even_players: Sequence[PlayerState],
        *,
        context: BracketContext,
        sequential_search_max_players: int = 12,
        allow_heuristic_fallback: bool = True,
    ) -> dutch._EvenPairingInternal:
        if len(even_players) == len(players) - 1:
            missing_id = next(iter(full_ids - {player.player_id for player in even_players}))
            seen_downfloaters.append(missing_id)
        return original_solve_even(
            even_players,
            context=context,
            sequential_search_max_players=sequential_search_max_players,
            allow_heuristic_fallback=allow_heuristic_fallback,
        )

    monkeypatch.setattr(dutch, "_solve_even_players", wrapped_solve_even)

    result = pair_bracket_exact(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1"})),
        allow_bye=False,
    )

    assert result.unpaired_ids == ("p21",)
    assert seen_downfloaters in ([], ["p21"])


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


def test_pair_bracket_reports_float_assignments_for_cross_score_pairs_and_byes() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=1),
    )

    result = pair_bracket(players)

    assert result.float_assignments == (
        FloatAssignment(player_id="p1", kind=FloatKind.DOWN),
        FloatAssignment(player_id="p2", kind=FloatKind.UP),
        FloatAssignment(player_id="p3", kind=FloatKind.DOWN),
    )


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


def test_homogeneous_odd_refinement_skips_feasibility_only_next_bracket_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )
    weighted_candidate = dutch._CandidateInternal(
        pairings=((players[0], players[1]),),
        unresolved=(players[2],),
        bye_player=None,
        sequence_no=0,
    )

    def _unexpected_even_solve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "feasibility-only C8 path should not rescan homogeneous odd candidates"
        )

    dutch._refine_weighted_homogeneous_odd_candidate.cache_clear()
    monkeypatch.setattr(dutch, "_solve_even_players", _unexpected_even_solve)
    try:
        refined = dutch._refine_weighted_homogeneous_odd_candidate(
            players,
            context=BracketContext(next_bracket_validator=lambda _: True),
            weighted_candidate=weighted_candidate,
            sequential_search_max_players=6,
        )
    finally:
        dutch._refine_weighted_homogeneous_odd_candidate.cache_clear()

    assert refined is weighted_candidate


def test_homogeneous_odd_refinement_scans_only_bounded_c8_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bracket_players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=2) for index in range(1, 12)
    )
    weighted_candidate = dutch._CandidateInternal(
        pairings=tuple(
            (bracket_players[index], bracket_players[index + 1]) for index in range(0, 10, 2)
        ),
        unresolved=(bracket_players[-1],),
        bye_player=None,
        sequence_no=0,
    )

    scanned_missing_ids: list[str] = []

    def _bounded_even_solve(
        players: Sequence[PlayerState],
        *,
        context: BracketContext,
        sequential_search_max_players: int,
    ) -> dutch._EvenPairingInternal:
        del context, sequential_search_max_players
        remaining_by_id = {player.player_id for player in players}
        missing_ids = sorted({player.player_id for player in bracket_players} - remaining_by_id)
        scanned_missing_ids.extend(missing_ids)
        return dutch._EvenPairingInternal(
            pairings=tuple(
                (players[index], players[index + 1]) for index in range(0, len(players), 2)
            ),
            unresolved=(),
        )

    dutch._refine_weighted_homogeneous_odd_candidate.cache_clear()
    monkeypatch.setattr(dutch, "_solve_even_players", _bounded_even_solve)
    try:
        refined = dutch._refine_weighted_homogeneous_odd_candidate(
            bracket_players,
            context=BracketContext(
                next_bracket_validator=lambda _: True,
                next_bracket_key=lambda _: NextBracketKey(),
            ),
            weighted_candidate=weighted_candidate,
            sequential_search_max_players=6,
        )
    finally:
        dutch._refine_weighted_homogeneous_odd_candidate.cache_clear()

    assert refined is not None
    assert scanned_missing_ids == ["p10"]


def test_heterogeneous_odd_refinement_uses_tighter_c8_candidate_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )
    weighted_candidate = dutch._CandidateInternal(
        pairings=((players[0], players[1]),),
        unresolved=(players[2],),
        bye_player=None,
        sequence_no=0,
    )
    over_budget = dutch._ODD_HETEROGENEOUS_REFINEMENT_MAX_CANDIDATES_WITH_NEXT_BRACKET + 1

    def _over_budget_candidates(
        players: Sequence[PlayerState],
        *,
        context: BracketContext,
    ) -> tuple[dutch._CandidateInternal, ...]:
        del players, context
        return (weighted_candidate,) * over_budget

    def _unexpected_selection(
        candidates: Sequence[dutch._CandidateInternal],
        *,
        context: BracketContext,
    ) -> dutch._CandidateInternal | None:
        del candidates, context
        raise AssertionError("over-budget C8 refinement should fall back before exact selection")

    dutch._refine_weighted_heterogeneous_odd_candidate.cache_clear()
    monkeypatch.setattr(dutch, "_iter_heterogeneous_candidates", _over_budget_candidates)
    monkeypatch.setattr(dutch, "_select_best_candidate", _unexpected_selection)
    try:
        refined = dutch._refine_weighted_heterogeneous_odd_candidate(
            players,
            context=BracketContext(
                mdp_ids=frozenset({"m1"}),
                next_bracket_validator=lambda _: True,
            ),
            weighted_candidate=weighted_candidate,
        )
    finally:
        dutch._refine_weighted_heterogeneous_odd_candidate.cache_clear()

    assert refined is weighted_candidate


def test_single_mdp_odd_refinement_skips_c8_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )

    def _unexpected_remainder_solve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("single-MDP C8 path should keep the existing weighted candidate")

    monkeypatch.setattr(dutch, "_solve_without_bye_candidate", _unexpected_remainder_solve)

    refined = dutch._refine_weighted_single_mdp_odd_candidate(
        players,
        context=BracketContext(
            mdp_ids=frozenset({"m1"}),
            next_bracket_validator=lambda _: True,
        ),
        sequential_search_max_players=6,
    )

    assert refined is None


def test_heterogeneous_odd_refinement_skips_single_mdp_without_next_bracket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )
    weighted_candidate = dutch._CandidateInternal(
        pairings=((players[0], players[1]),),
        unresolved=(players[2],),
        bye_player=None,
        sequence_no=0,
    )

    def _unexpected_exact_candidates(
        players: Sequence[PlayerState],
        *,
        context: BracketContext,
    ) -> tuple[dutch._CandidateInternal, ...]:
        del players, context
        raise AssertionError("single-MDP no-C8 refinement should keep the existing candidate")

    dutch._refine_weighted_heterogeneous_odd_candidate.cache_clear()
    monkeypatch.setattr(dutch, "_iter_heterogeneous_candidates", _unexpected_exact_candidates)
    try:
        refined = dutch._refine_weighted_heterogeneous_odd_candidate(
            players,
            context=BracketContext(mdp_ids=frozenset({"m1"})),
            weighted_candidate=weighted_candidate,
        )
    finally:
        dutch._refine_weighted_heterogeneous_odd_candidate.cache_clear()

    assert refined is weighted_candidate


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


def test_pair_bracket_initial_homogeneous_odd_uses_direct_s1_s2_pairing() -> None:
    players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=0) for index in range(1, 6)
    )

    result = pair_bracket(players)

    assert _normalized_pairs(result.pairings) == {
        ("p1", "p3"),
        ("p2", "p4"),
        ("p5", None),
    }
    assert result.unpaired_ids == ()


def test_pair_bracket_initial_homogeneous_odd_without_bye_downfloats_last_player() -> None:
    players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=0) for index in range(1, 6)
    )

    result = pair_bracket(players, allow_bye=False)

    assert _normalized_pairs(result.pairings) == {
        ("p1", "p3"),
        ("p2", "p4"),
    }
    assert result.unpaired_ids == ("p5",)


def test_pair_bracket_initial_homogeneous_allows_empty_float_history_markers() -> None:
    players = tuple(
        _player(
            player_id=f"p{index}",
            pairing_no=index,
            score=0,
            float_history=(FloatKind.NONE, FloatKind.NONE),
        )
        for index in range(1, 6)
    )

    result = pair_bracket(players)

    assert _normalized_pairs(result.pairings) == {
        ("p1", "p3"),
        ("p2", "p4"),
        ("p5", None),
    }
    assert result.unpaired_ids == ()


def test_pair_bracket_initial_homogeneous_large_odd_bypasses_weighted_bye_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = tuple(
        _player(player_id=f"p{index}", pairing_no=index, score=0) for index in range(1, 22)
    )

    def fail_weighted_bye(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("weighted large-bye path should not run for trivial round-1 brackets")

    monkeypatch.setattr(
        dutch,
        "_select_large_final_bye_candidate_via_weighted_steps",
        fail_weighted_bye,
    )

    result = pair_bracket(players, sequential_search_max_players=0)

    assert ("p21", None) in _to_pairs(result.pairings)
    assert result.unpaired_ids == ()


def test_pair_bracket_large_weighted_final_bye_avoids_scanning_every_legal_bye(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = tuple(
        _player(
            player_id=f"p{index}",
            pairing_no=index,
            score=0,
            float_history=(FloatKind.UP,) if index == 1 else (),
        )
        for index in range(1, 22)
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
