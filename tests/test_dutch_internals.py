# pyright: reportPrivateUsage=false
"""Targeted internal regressions for Dutch pairing helpers."""

from __future__ import annotations

from swisspairing.dutch import (
    BracketContext,
    _CandidateInternal,
    _choose_color_order,
    _heterogeneous_exact_candidate_upper_bound,
    _heterogeneous_structural_tie_key,
    _homogeneous_article_order_key,
    _homogeneous_exact_candidate_upper_bound,
    _pair_color_quality,
    _select_best_candidate,
    _use_heterogeneous_exact_search,
    _use_homogeneous_exact_search,
)
from swisspairing.model import Color, PlayerState


def _player(
    *,
    player_id: str,
    pairing_no: int,
    score: int,
    color_history: tuple[Color, ...],
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        pairing_no=pairing_no,
        score=score,
        color_history=color_history,
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

    assert (white.player_id, black.player_id) == ("s1", "a1")
    assert _pair_color_quality(white=white, black=black) == (0, 0, 1, 1)


def test_homogeneous_article_order_key_prefers_zero_exchange_candidate() -> None:
    players = tuple(
        _player(player_id=f"p{i}", pairing_no=i, score=3, color_history=())
        for i in range(1, 6)
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
        _player(player_id=f"p{i}", pairing_no=i, score=0, color_history=())
        for i in range(8, 14)
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


def test_homogeneous_exact_search_budget_skips_10_player_explosion() -> None:
    assert _homogeneous_exact_candidate_upper_bound(8) == 1680
    assert _homogeneous_exact_candidate_upper_bound(9) == 15120
    assert _homogeneous_exact_candidate_upper_bound(10) == 30240
    assert _homogeneous_exact_candidate_upper_bound(12) == 665280

    assert _use_homogeneous_exact_search(8, sequential_search_max_players=12) is True
    assert _use_homogeneous_exact_search(9, sequential_search_max_players=12) is False
    assert _use_homogeneous_exact_search(10, sequential_search_max_players=12) is False
    assert _use_homogeneous_exact_search(12, sequential_search_max_players=12) is False

    assert _heterogeneous_exact_candidate_upper_bound(9, 2) == 2520
    assert _heterogeneous_exact_candidate_upper_bound(11, 1) == 151200
    assert _use_heterogeneous_exact_search(
        9,
        mdp_count=2,
        sequential_search_max_players=12,
    ) is True
    assert _use_heterogeneous_exact_search(
        9,
        mdp_count=1,
        sequential_search_max_players=12,
    ) is False
    assert _use_heterogeneous_exact_search(
        11,
        mdp_count=1,
        sequential_search_max_players=12,
    ) is False
