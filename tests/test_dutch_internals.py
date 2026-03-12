# pyright: reportPrivateUsage=false
"""Targeted internal regressions for Dutch pairing helpers."""

from __future__ import annotations

import pytest

import swisspairing.dutch as dutch_module
from swisspairing.dutch import (
    BracketContext,
    _candidate_local_quality_key,
    _CandidateInternal,
    _choose_color_order,
    _collect_mdp_quality,
    _collect_pair_quality_counts,
    _edge_penalty_components,
    _extend_next_bracket_validator,
    _heterogeneous_exact_candidate_upper_bound,
    _heterogeneous_structural_tie_key,
    _homogeneous_article_order_key,
    _homogeneous_exact_candidate_upper_bound,
    _iter_homogeneous_candidates,
    _iter_pairable_mdp_sets,
    _iter_s2_transpositions,
    _pair_color_quality,
    _select_best_candidate,
    _select_best_homogeneous_odd_candidate,
    _use_heterogeneous_exact_search,
    _use_homogeneous_exact_search,
    pairing_result_next_bracket_local_key,
)
from swisspairing.model import Color, FloatKind, Pairing, PairingResult, PlayerState


def _player(
    *,
    player_id: str,
    pairing_no: int,
    score: int,
    color_history: tuple[Color, ...],
    opponents: frozenset[str] = frozenset(),
    float_history: tuple[FloatKind, ...] = (),
    is_top_scorer: bool = False,
    is_topscorer_or_opponent: bool = False,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        pairing_no=pairing_no,
        score=score,
        color_history=color_history,
        opponents=opponents,
        float_history=float_history,
        is_top_scorer=is_top_scorer,
        is_topscorer_or_opponent=is_topscorer_or_opponent,
    )


def test_pair_color_quality_counts_absolute_preference_as_strong() -> None:
    strong_white = _player(
        player_id="s1",
        pairing_no=1,
        score=3,
        color_history=("black", "white", "black"),
    )
    absolute_white = _player(
        player_id="a1",
        pairing_no=2,
        score=3,
        color_history=("black", "black", "black"),
    )

    white, black = _choose_color_order(strong_white, absolute_white)

    assert (white.player_id, black.player_id) == ("a1", "s1")
    assert _pair_color_quality(white=white, black=black) == (0, 0, 1, 1)


def test_choose_color_order_uses_article_5_2_3_alternation() -> None:
    first = _player(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("white", "black", "black", "white"),
    )
    second = _player(
        player_id="p2",
        pairing_no=2,
        score=3,
        color_history=("black", "white", "black", "white"),
    )

    white, black = _choose_color_order(first, second)

    assert (white.player_id, black.player_id) == ("p1", "p2")


def test_choose_color_order_uses_article_5_2_4_higher_ranked_preference() -> None:
    higher = _player(
        player_id="higher",
        pairing_no=1,
        score=3,
        color_history=("black", "white"),
    )
    lower = _player(
        player_id="lower",
        pairing_no=2,
        score=3,
        color_history=("white", "black", "black", "white"),
    )

    white, black = _choose_color_order(higher, lower)

    assert (white.player_id, black.player_id) == ("lower", "higher")


def test_choose_color_order_uses_article_5_2_5_initial_color_tie_break() -> None:
    first = _player(player_id="p1", pairing_no=1, score=3, color_history=())
    second = _player(player_id="p2", pairing_no=2, score=3, color_history=())

    white, black = _choose_color_order(first, second, initial_color="black")

    assert (white.player_id, black.player_id) == ("p2", "p1")


def test_candidate_local_quality_key_matches_pair_and_mdp_helpers() -> None:
    mdp = _player(
        player_id="p1",
        pairing_no=1,
        score=12,
        color_history=("black", "white", "black"),
        float_history=(FloatKind.DOWN, FloatKind.DOWN),
        is_top_scorer=True,
        is_topscorer_or_opponent=True,
    )
    resident = _player(
        player_id="p2",
        pairing_no=2,
        score=10,
        color_history=("white", "white"),
        float_history=(FloatKind.UP, FloatKind.UP),
        is_top_scorer=True,
        is_topscorer_or_opponent=True,
    )
    left = _player(
        player_id="p3",
        pairing_no=3,
        score=12,
        color_history=("white",),
        is_topscorer_or_opponent=True,
    )
    right = _player(
        player_id="p4",
        pairing_no=4,
        score=12,
        color_history=("black",),
        is_topscorer_or_opponent=True,
    )
    downfloater = _player(
        player_id="p5",
        pairing_no=5,
        score=10,
        color_history=("black",),
        float_history=(FloatKind.DOWN, FloatKind.DOWN),
    )
    candidate = _CandidateInternal(
        pairings=((mdp, resident), (left, right)),
        unresolved=(downfloater,),
        bye_player=None,
        sequence_no=7,
    )
    context = BracketContext(mdp_ids=frozenset({"p1"}), initial_color="white")
    pair_components = tuple(
        _edge_penalty_components(player_a, player_b, context=context)
        for player_a, player_b in candidate.pairings
    )

    local_key = _candidate_local_quality_key(candidate, context.mdp_ids, context.initial_color)
    c10, c11, c12, c13 = _collect_pair_quality_counts(pair_components)
    c15, c17, c18, c19, c20, c21 = _collect_mdp_quality(pair_components=pair_components)
    c14 = sum(
        int(player.had_float(rounds_ago=1, kind=FloatKind.DOWN)) for player in candidate.unresolved
    )
    c16 = sum(
        int(player.had_float(rounds_ago=2, kind=FloatKind.DOWN)) for player in candidate.unresolved
    )

    assert local_key[4] == 0
    assert local_key[5:9] == (c10, c11, c12, c13)
    assert local_key[9] == c14
    assert local_key[10] == c15
    assert local_key[11] == c16
    assert local_key[12] == c17
    assert local_key[13:17] == (c18, c19, c20, c21)


def test_homogeneous_article_order_key_prefers_zero_exchange_candidate() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=()) for i in range(1, 6)
    )
    by_id = {player.player_id: player for player in players}

    zero_exchange = _CandidateInternal(
        pairings=((by_id["p1"], by_id["p3"]), (by_id["p2"], by_id["p4"])),
        unresolved=(by_id["p5"],),
        bye_player=None,
        sequence_no=1,
    )
    one_exchange = _CandidateInternal(
        pairings=((by_id["p1"], by_id["p4"]), (by_id["p3"], by_id["p5"])),
        unresolved=(by_id["p2"],),
        bye_player=None,
        sequence_no=0,
    )

    assert _homogeneous_article_order_key(
        players=players,
        candidate=zero_exchange,
    ) < _homogeneous_article_order_key(
        players=players,
        candidate=one_exchange,
    )


def test_extend_next_bracket_validator_flattens_fixed_downfloaters() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=()) for i in range(1, 5)
    )
    seen: list[tuple[str, ...]] = []

    def validator(downfloaters: tuple[PlayerState, ...]) -> bool:
        seen.append(tuple(player.player_id for player in downfloaters))
        return True

    wrapped_once = _extend_next_bracket_validator(validator, fixed_downfloaters=(players[2],))
    wrapped_twice = _extend_next_bracket_validator(
        wrapped_once,
        fixed_downfloaters=(players[0],),
    )
    direct = _extend_next_bracket_validator(
        validator,
        fixed_downfloaters=(players[0], players[2]),
    )

    assert wrapped_twice == direct
    assert hash(wrapped_twice) == hash(direct)
    assert wrapped_twice((players[1],)) is True
    assert seen == [("p1", "p2", "p3")]


def test_iter_homogeneous_candidates_deduplicates_pair_orientation() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=()) for i in range(1, 4)
    )

    candidates = _iter_homogeneous_candidates(players)

    assert len(candidates) == 3
    assert {
        (
            tuple(
                sorted(
                    tuple(sorted((left.player_id, right.player_id)))
                    for left, right in candidate.pairings
                )
            ),
            tuple(player.player_id for player in candidate.unresolved),
        )
        for candidate in candidates
    } == {
        ((("p1", "p2"),), ("p3",)),
        ((("p1", "p3"),), ("p2",)),
        ((("p2", "p3"),), ("p1",)),
    }


def test_iter_s2_transpositions_preserves_article_prefix_order() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=()) for i in range(1, 6)
    )

    transpositions = _iter_s2_transpositions(
        s1=(players[0], players[1]),
        s2=(players[2], players[3], players[4]),
        bsn_by_player_id={player.player_id: player.pairing_no for player in players},
    )

    assert [
        tuple(player.player_id for player in transposition) for transposition in transpositions
    ] == [
        ("p3", "p4", "p5"),
        ("p3", "p5", "p4"),
        ("p4", "p3", "p5"),
        ("p4", "p5", "p3"),
        ("p5", "p3", "p4"),
        ("p5", "p4", "p3"),
    ]


def test_select_best_homogeneous_odd_candidate_skips_article_order_for_losing_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=()) for i in range(1, 4)
    )
    candidate_a = _CandidateInternal(
        pairings=((players[0], players[1]),),
        unresolved=(players[2],),
        bye_player=None,
        sequence_no=0,
    )
    candidate_b = _CandidateInternal(
        pairings=((players[0], players[2]),),
        unresolved=(players[1],),
        bye_player=None,
        sequence_no=1,
    )
    seen_article_order_candidates: list[str] = []

    def fake_candidate_quality_key(
        *,
        candidate: _CandidateInternal,
        context: BracketContext,
    ) -> tuple[int, int]:
        del context
        return (
            (0, candidate.sequence_no) if candidate is candidate_a else (1, candidate.sequence_no)
        )

    def fake_homogeneous_article_order_key(
        *,
        players: tuple[PlayerState, ...],
        candidate: _CandidateInternal,
    ) -> tuple[int]:
        del players
        seen_article_order_candidates.append(candidate.pairings[0][1].player_id)
        return (candidate.sequence_no,)

    monkeypatch.setattr(dutch_module, "_candidate_quality_key", fake_candidate_quality_key)
    monkeypatch.setattr(
        dutch_module,
        "_homogeneous_article_order_key",
        fake_homogeneous_article_order_key,
    )

    result = _select_best_homogeneous_odd_candidate(
        players,
        (candidate_a, candidate_b),
        context=BracketContext(initial_color="white"),
    )

    assert result is candidate_a
    assert seen_article_order_candidates == ["p2"]


def test_heterogeneous_structural_tie_key_prefers_tighter_resident_remainder() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=score, color_history=())
        for i, score in (
            (1, 105),
            (8, 95),
            (9, 80),
            (13, 80),
            (14, 80),
            (15, 80),
            (16, 80),
            (18, 80),
            (20, 75),
            (22, 80),
            (23, 75),
            (24, 80),
            (25, 80),
            (29, 75),
        )
    )
    by_id = {player.player_id: player for player in players}
    mdp_ids = frozenset({"p1", "p8"})

    current_exact = _CandidateInternal(
        pairings=(
            (by_id["p1"], by_id["p9"]),
            (by_id["p8"], by_id["p14"]),
            (by_id["p13"], by_id["p25"]),
            (by_id["p15"], by_id["p23"]),
            (by_id["p16"], by_id["p20"]),
            (by_id["p18"], by_id["p29"]),
            (by_id["p22"], by_id["p24"]),
        ),
        unresolved=(),
        bye_player=None,
        sequence_no=3237,
    )
    bbp_reference = _CandidateInternal(
        pairings=(
            (by_id["p1"], by_id["p15"]),
            (by_id["p8"], by_id["p14"]),
            (by_id["p9"], by_id["p16"]),
            (by_id["p13"], by_id["p25"]),
            (by_id["p18"], by_id["p29"]),
            (by_id["p20"], by_id["p23"]),
            (by_id["p22"], by_id["p24"]),
        ),
        unresolved=(),
        bye_player=None,
        sequence_no=68718,
    )

    assert _heterogeneous_structural_tie_key(
        candidate=bbp_reference,
        mdp_ids=mdp_ids,
    ) < _heterogeneous_structural_tie_key(
        candidate=current_exact,
        mdp_ids=mdp_ids,
    )


def test_single_mdp_heterogeneous_tie_keeps_article_sequence_order() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=0, color_history=()) for i in range(8, 14)
    )
    mdp = _player(player_id="p2", pairing_no=2, score=20, color_history=())
    by_id = {player.player_id: player for player in (*players, mdp)}

    article_first = _CandidateInternal(
        pairings=(
            (by_id["p2"], by_id["p8"]),
            (by_id["p9"], by_id["p11"]),
            (by_id["p10"], by_id["p12"]),
        ),
        unresolved=(),
        bye_player=by_id["p13"],
        sequence_no=0,
    )
    structural_later = _CandidateInternal(
        pairings=(
            (by_id["p2"], by_id["p8"]),
            (by_id["p9"], by_id["p10"]),
            (by_id["p11"], by_id["p12"]),
        ),
        unresolved=(),
        bye_player=by_id["p13"],
        sequence_no=6,
    )

    assert (
        _select_best_candidate(
            (structural_later, article_first),
            context=BracketContext(mdp_ids=frozenset({"p2"})),
        )
        == article_first
    )


def test_select_best_candidate_deduplicates_canonical_pair_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _player(player_id="p1", pairing_no=1, score=3, color_history=())
    second = _player(player_id="p2", pairing_no=2, score=3, color_history=())
    third = _player(player_id="p3", pairing_no=3, score=3, color_history=())

    earlier_duplicate = _CandidateInternal(
        pairings=((first, second),),
        unresolved=(third,),
        bye_player=None,
        sequence_no=1,
    )
    later_duplicate = _CandidateInternal(
        pairings=((second, first),),
        unresolved=(third,),
        bye_player=None,
        sequence_no=4,
    )
    scored_sequences: list[int] = []
    original_quality_key = _candidate_local_quality_key

    def tracking_quality_key(
        candidate: _CandidateInternal,
        mdp_ids: frozenset[str],
        initial_color: Color,
    ) -> tuple[
        tuple[PlayerState, ...],
        int,
        int,
        tuple[int, ...],
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        tuple[int, ...],
        tuple[int, ...],
        tuple[int, ...],
        tuple[int, ...],
        int,
    ]:
        scored_sequences.append(candidate.sequence_no)
        return original_quality_key(candidate, mdp_ids, initial_color)

    monkeypatch.setattr(
        "swisspairing.dutch._candidate_local_quality_key",
        tracking_quality_key,
    )

    assert (
        _select_best_candidate(
            (later_duplicate, earlier_duplicate),
            context=BracketContext(),
        )
        == earlier_duplicate
    )
    assert scored_sequences == [1]


def test_homogeneous_exact_search_budget_obeys_candidate_cap() -> None:
    assert _homogeneous_exact_candidate_upper_bound(8) == 1680
    assert _homogeneous_exact_candidate_upper_bound(9) == 15120
    assert _homogeneous_exact_candidate_upper_bound(10) == 30240
    assert _homogeneous_exact_candidate_upper_bound(12) == 665280

    assert _use_homogeneous_exact_search(8, sequential_search_max_players=12) is True
    assert _use_homogeneous_exact_search(9, sequential_search_max_players=12) is True
    assert _use_homogeneous_exact_search(10, sequential_search_max_players=12) is True
    assert _use_homogeneous_exact_search(12, sequential_search_max_players=12) is False
    assert (
        _use_homogeneous_exact_search(
            10,
            sequential_search_max_players=12,
            exact_candidate_max=30_000,
        )
        is False
    )

    assert _heterogeneous_exact_candidate_upper_bound(9, 2) == 2520
    assert _heterogeneous_exact_candidate_upper_bound(11, 1) == 151200
    assert (
        _use_heterogeneous_exact_search(
            9,
            mdp_count=2,
            sequential_search_max_players=12,
        )
        is True
    )
    assert (
        _use_heterogeneous_exact_search(
            9,
            mdp_count=1,
            sequential_search_max_players=12,
            exact_candidate_max=5_000,
        )
        is False
    )
    assert (
        _use_heterogeneous_exact_search(
            9,
            mdp_count=1,
            sequential_search_max_players=12,
        )
        is True
    )
    assert (
        _use_heterogeneous_exact_search(
            11,
            mdp_count=1,
            sequential_search_max_players=12,
        )
        is False
    )
    assert (
        _use_heterogeneous_exact_search(
            13,
            mdp_count=9,
            sequential_search_max_players=13,
            exact_candidate_max=50_000,
        )
        is True
    )


def test_pairable_mdp_sets_skip_infeasible_high_score_selection() -> None:
    mdps = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=105,
            color_history=(),
            opponents=frozenset({"p2", "p10"}),
        ),
        _player(
            player_id="p3",
            pairing_no=3,
            score=100,
            color_history=(),
            opponents=frozenset({"p10"}),
        ),
        _player(
            player_id="p7",
            pairing_no=7,
            score=95,
            color_history=(),
            opponents=frozenset({"p2"}),
        ),
        _player(
            player_id="p8",
            pairing_no=8,
            score=95,
            color_history=(),
            opponents=frozenset({"p2"}),
        ),
    )
    residents = (
        _player(player_id="p2", pairing_no=2, score=85, color_history=()),
        _player(player_id="p10", pairing_no=10, score=85, color_history=()),
    )
    bsn_by_player_id = {
        player.player_id: index + 1 for index, player in enumerate((*mdps, *residents))
    }

    mdp_sets = _iter_pairable_mdp_sets(
        mdps=mdps,
        residents=residents,
        bsn_by_player_id=bsn_by_player_id,
    )

    assert tuple(tuple(player.player_id for player in mdp_set) for mdp_set in mdp_sets) == (
        ("p3", "p7"),
        ("p3", "p8"),
    )


def test_multi_mdp_incomplete_tie_keeps_article_sequence_order() -> None:
    by_id = {
        player.player_id: player
        for player in (
            _player(
                player_id="p1",
                pairing_no=1,
                score=105,
                color_history=(),
                opponents=frozenset({"p2", "p10"}),
            ),
            _player(
                player_id="p3",
                pairing_no=3,
                score=100,
                color_history=(),
                opponents=frozenset({"p10"}),
            ),
            _player(
                player_id="p7",
                pairing_no=7,
                score=95,
                color_history=(),
                opponents=frozenset({"p2"}),
            ),
            _player(
                player_id="p8",
                pairing_no=8,
                score=95,
                color_history=(),
                opponents=frozenset({"p2"}),
            ),
            _player(player_id="p2", pairing_no=2, score=85, color_history=()),
            _player(player_id="p10", pairing_no=10, score=85, color_history=()),
        )
    }
    article_first = _CandidateInternal(
        pairings=((by_id["p3"], by_id["p2"]), (by_id["p7"], by_id["p10"])),
        unresolved=(by_id["p1"], by_id["p8"]),
        bye_player=None,
        sequence_no=0,
    )
    structural_later = _CandidateInternal(
        pairings=((by_id["p3"], by_id["p2"]), (by_id["p8"], by_id["p10"])),
        unresolved=(by_id["p1"], by_id["p7"]),
        bye_player=None,
        sequence_no=1,
    )

    assert (
        _select_best_candidate(
            (structural_later, article_first),
            context=BracketContext(mdp_ids=frozenset({"p1", "p3", "p7", "p8"})),
        )
        == article_first
    )


def test_pairing_result_next_bracket_local_key_uses_only_c5_to_c7() -> None:
    players = tuple(
        _player(
            player_id=player_id,
            pairing_no=pairing_no,
            score=score,
            color_history=(),
        )
        for player_id, pairing_no, score in (
            ("p1", 1, 4),
            ("p2", 2, 4),
            ("p3", 3, 3),
            ("p4", 4, 3),
            ("p5", 5, 2),
        )
    )
    result = PairingResult(
        pairings=(
            Pairing(white_id="p2", black_id="p1"),
            Pairing(white_id="p4", black_id="p3"),
            Pairing(white_id="p5", black_id=None),
        ),
        unpaired_ids=("p3",),
        float_assignments=(),
    )

    key = pairing_result_next_bracket_local_key(
        players=players,
        result=result,
        context=BracketContext(mdp_ids=frozenset({"p1"}), initial_color="black"),
    )

    assert key == dutch_module.NextBracketLocalKey(c5=2, c6=-2, c7=(3,))


def test_candidate_quality_key_skips_next_bracket_key_when_c8_already_fails() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=()) for i in range(1, 5)
    )
    candidate = _CandidateInternal(
        pairings=((players[0], players[1]),),
        unresolved=(players[2], players[3]),
        bye_player=None,
        sequence_no=0,
    )
    key_calls = 0

    def next_bracket_validator(_: tuple[PlayerState, ...]) -> bool:
        return False

    def next_bracket_key(_: tuple[PlayerState, ...]) -> dutch_module.NextBracketKey:
        nonlocal key_calls
        key_calls += 1
        return dutch_module.NextBracketKey(local=dutch_module.NextBracketLocalKey(c5=-1))

    key = dutch_module._candidate_quality_key(
        candidate=candidate,
        context=BracketContext(
            initial_color="white",
            next_bracket_validator=next_bracket_validator,
            next_bracket_key=next_bracket_key,
        ),
    )

    assert key[3] == 1
    assert key[4] == dutch_module.NextBracketKey()
    assert key_calls == 0
