from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from swisspairing.dutch import BracketContext, pair_bracket
from swisspairing.exceptions import PairingError
from swisspairing.model import Color, FloatKind, PairingResult, PlayerState
from swisspairing.tournament import pair_round_dutch

type RuleStatus = Literal[
    "tested",
    "partially_tested",
    "input_contract",
    "process_only",
    "not_represented",
    "xfail",
]


@dataclass(frozen=True, slots=True)
class RuleGroup:
    status: RuleStatus
    reason: str
    clauses: tuple[str, ...]
    tests: tuple[str, ...] = ()


_DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"
_RULEBOOK_PATHS = {
    "C0401": _DOCS_ROOT / "C0401_Basic_rules_for_Swiss_Systems_from_2026_02_01.md",
    "C0402": _DOCS_ROOT / "C0402_General_handling_rules_for_Swiss_Tournaments_from_2026_02_01.md",
    "C0403": _DOCS_ROOT / "C0403_FIDE_Dutch_System_from_2026_02_01.md",
}
_CLAUSE_PATTERNS = {
    "C0401": re.compile(r"^(?:\*\*)?([1-9])\.\s"),
    "C0402": re.compile(r"^(?:\*\*)?(\d+\.\d+(?:\.\d+)*)\b"),
    "C0403": re.compile(r"^(?:\*\*)?(\d+\.\d+(?:\.\d+)*)\b"),
}


def _doc_rule_ids() -> tuple[str, ...]:
    ids: list[str] = []
    for chapter, path in _RULEBOOK_PATHS.items():
        pattern = _CLAUSE_PATTERNS[chapter]
        for line in path.read_text().splitlines():
            match = pattern.match(line)
            if match is not None:
                ids.append(f"{chapter}.{match.group(1)}")
    return tuple(ids)


DOC_RULE_IDS = _doc_rule_ids()


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


def _normalized_pairs(result: PairingResult) -> set[tuple[str, str | None]]:
    normalized: set[tuple[str, str | None]] = set()
    for pairing in result.pairings:
        if pairing.black_id is None:
            normalized.add((pairing.white_id, None))
            continue
        left, right = sorted((pairing.white_id, pairing.black_id))
        normalized.add((left, right))
    return normalized


def test_c0403_model_derives_color_difference_and_preferences() -> None:
    absolute_by_imbalance = _player(
        player_id="abs-imbalance",
        pairing_no=1,
        score=0,
        color_history=("black", "black"),
    )
    absolute_by_repetition = _player(
        player_id="abs-repetition",
        pairing_no=2,
        score=0,
        color_history=("white", "black", "black"),
    )
    strong = _player(
        player_id="strong",
        pairing_no=3,
        score=0,
        color_history=("white",),
    )
    mild = _player(
        player_id="mild",
        pairing_no=4,
        score=0,
        color_history=("black", "white"),
    )
    none = _player(player_id="none", pairing_no=5, score=0)

    assert absolute_by_imbalance.color_difference == -2
    assert absolute_by_imbalance.absolute_color_preference == "white"
    assert absolute_by_imbalance.color_preference == "white"

    assert absolute_by_repetition.color_difference == -1
    assert absolute_by_repetition.absolute_color_preference == "white"
    assert absolute_by_repetition.strong_color_preference == "white"
    assert absolute_by_repetition.color_preference == "white"

    assert strong.color_difference == 1
    assert strong.absolute_color_preference is None
    assert strong.strong_color_preference == "black"
    assert strong.color_preference == "black"

    assert mild.color_difference == 0
    assert mild.mild_color_preference == "black"
    assert mild.color_preference == "black"

    assert none.color_difference == 0
    assert none.color_preference is None


def test_c0402_1_4_is_reproducible_for_identical_input() -> None:
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


def test_c0401_rule_2_and_c0403_c1_forbid_rematches() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, opponents=frozenset({"p2"})),
        _player(player_id="p2", pairing_no=2, score=3, opponents=frozenset({"p1"})),
    )

    result = pair_bracket(players)

    assert result.pairings == ()
    assert result.unpaired_ids == ("p1", "p2")


def test_c0401_rules_3_and_4_assign_a_single_legal_pairing_allocated_bye() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, had_full_point_bye=True),
        _player(player_id="p2", pairing_no=2, score=1),
        _player(player_id="p3", pairing_no=3, score=1),
    )

    result = pair_bracket(players)

    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]
    assert len(bye_pairings) == 1
    assert bye_pairings[0].white_id != "p1"
    assert len(result.pairings) == 2
    assert result.unpaired_ids == ()


def test_c0401_rule_4_and_c0403_c2_exclude_previous_full_point_unplayed_rounds_from_pab() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, had_full_point_unplayed_round=True),
        _player(player_id="p2", pairing_no=2, score=1),
        _player(player_id="p3", pairing_no=3, score=1),
    )

    result = pair_bracket(players)

    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]
    assert len(bye_pairings) == 1
    assert bye_pairings[0].white_id != "p1"
    assert result.unpaired_ids == ()


def test_c0401_rule_5_pairs_players_on_the_same_score_when_possible() -> None:
    players = (
        _player(player_id="a1", pairing_no=1, score=3),
        _player(player_id="a2", pairing_no=2, score=3),
        _player(player_id="b1", pairing_no=3, score=2),
        _player(player_id="b2", pairing_no=4, score=2),
    )

    result = pair_round_dutch(players)

    assert _normalized_pairs(result) == {("a1", "a2"), ("b1", "b2")}


def test_c0402_3_6_sorts_pairings_for_publication() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, opponents=frozenset({"p2", "p3"})),
        _player(player_id="p2", pairing_no=2, score=3, opponents=frozenset({"p1", "p4"})),
        _player(player_id="p3", pairing_no=3, score=2, opponents=frozenset({"p1"})),
        _player(player_id="p4", pairing_no=4, score=2, opponents=frozenset({"p2"})),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 2
    assert "p1" in {result.pairings[0].white_id, result.pairings[0].black_id}
    assert "p2" in {result.pairings[1].white_id, result.pairings[1].black_id}


def test_c0403_1_4_1_and_c6_downfloat_the_single_unavoidable_player() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=1),
    )

    result = pair_bracket(players, allow_bye=False)

    assert len(result.pairings) == 1
    assert all(pairing.black_id is not None for pairing in result.pairings)
    assert result.unpaired_ids == ("p3",)


def test_c0403_1_3_2_and_1_9_2_carry_mdps_into_the_next_scoregroup() -> None:
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
    scores = {player.player_id: player.score for player in players}

    cross_score_pairs = [
        pairing
        for pairing in result.pairings
        if pairing.black_id is not None and scores[pairing.white_id] != scores[pairing.black_id]
    ]
    bye_pairings = [pairing for pairing in result.pairings if pairing.black_id is None]

    assert len(cross_score_pairs) == 1
    assert len(bye_pairings) == 1
    assert result.unpaired_ids == ()


def test_c0403_1_9_1_and_c4_raise_on_impossible_round_pairing() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, opponents=frozenset({"p2"})),
        _player(player_id="p2", pairing_no=2, score=2, opponents=frozenset({"p1"})),
    )

    with pytest.raises(PairingError):
        pair_round_dutch(players)


def test_c0403_c3_blocks_non_topscorers_with_the_same_absolute_preference() -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=3,
            color_history=("white", "white"),
        ),
        _player(
            player_id="p2",
            pairing_no=2,
            score=3,
            color_history=("white", "white"),
        ),
    )

    result = pair_bracket(players)

    assert result.pairings == ()
    assert result.unpaired_ids == ("p1", "p2")


def test_c0403_c3_allows_the_topscorer_exception() -> None:
    players = (
        _player(
            player_id="p1",
            pairing_no=1,
            score=4,
            color_history=("white", "white"),
            is_top_scorer=True,
        ),
        _player(
            player_id="p2",
            pairing_no=2,
            score=4,
            color_history=("white", "white"),
        ),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.unpaired_ids == ()


def test_c0403_5_2_1_grants_both_compatible_color_preferences() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, color_history=("white",)),
        _player(player_id="p2", pairing_no=2, score=3, color_history=("black",)),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.pairings[0].white_id == "p2"
    assert result.pairings[0].black_id == "p1"


def test_c0403_c7_prefers_lower_scoring_limbo_players() -> None:
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

    assert _normalized_pairs(result) == {("m1", "r1")}
    assert result.unpaired_ids == ("m2", "m3")


def test_c0403_c8_uses_next_bracket_lookahead() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )

    def validator(downfloaters: tuple[PlayerState, ...]) -> bool:
        return all(player.player_id != "p1" for player in downfloaters)

    result = pair_bracket(players, context=BracketContext(next_bracket_validator=validator))

    assert ("p1", None) not in _normalized_pairs(result)


def test_c0403_c9_breaks_pab_ties_by_unplayed_games() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, unplayed_games=3),
        _player(player_id="p2", pairing_no=2, score=2, unplayed_games=1),
        _player(player_id="p3", pairing_no=3, score=2, unplayed_games=2),
    )

    result = pair_bracket(players)

    assert ("p2", None) in _normalized_pairs(result)


def test_c0403_c10_and_c11_keep_a_topscorer_on_their_absolute_color() -> None:
    players = (
        _player(
            player_id="top",
            pairing_no=1,
            score=3,
            color_history=("white", "white"),
            is_top_scorer=True,
            is_topscorer_or_opponent=True,
        ),
        _player(
            player_id="other",
            pairing_no=2,
            score=3,
            color_history=("white", "white"),
        ),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.pairings[0].black_id == "top"


def test_c0403_c12_and_c13_prefer_fulfilling_the_stronger_color_preference() -> None:
    players = (
        _player(player_id="strong", pairing_no=1, score=3, color_history=("white",)),
        _player(player_id="mild", pairing_no=2, score=3, color_history=("black", "white")),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.pairings[0].black_id == "strong"


@pytest.mark.parametrize(
    ("float_history", "label"),
    [
        ((FloatKind.DOWN,), "previous round"),
        ((FloatKind.DOWN, FloatKind.NONE), "two rounds ago"),
    ],
)
def test_c0403_c14_and_c16_avoid_repeat_resident_downfloaters(
    float_history: tuple[FloatKind, ...],
    label: str,
) -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=2, float_history=float_history),
        _player(player_id="p2", pairing_no=2, score=2),
        _player(player_id="p3", pairing_no=3, score=2),
    )

    result = pair_bracket(players)

    assert ("p1", None) not in _normalized_pairs(result), label


@pytest.mark.parametrize(
    ("resident_history", "label"),
    [
        ((FloatKind.UP,), "previous round"),
        ((FloatKind.UP, FloatKind.NONE), "two rounds ago"),
    ],
)
def test_c0403_c15_and_c17_avoid_repeat_upfloat_opponents_for_mdps(
    resident_history: tuple[FloatKind, ...],
    label: str,
) -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=3, had_full_point_bye=True),
        _player(player_id="safe", pairing_no=2, score=3),
        _player(player_id="repeat", pairing_no=3, score=3, float_history=resident_history),
    )

    result = pair_bracket(players, context=BracketContext(mdp_ids=frozenset({"m1"})))

    assert ("repeat", None) in _normalized_pairs(result), label


def test_c0403_c18_prefers_the_smaller_previous_downfloat_score_gap() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=4, float_history=(FloatKind.DOWN,)),
        _player(player_id="m2", pairing_no=2, score=4),
        _player(player_id="r1", pairing_no=3, score=3),
        _player(player_id="r2", pairing_no=4, score=2),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2"})),
        allow_bye=False,
    )

    assert _normalized_pairs(result) == {("m1", "r1"), ("m2", "r2")}


def test_c0403_c19_prefers_the_smaller_previous_upfloat_score_gap() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=5),
        _player(player_id="m2", pairing_no=2, score=4),
        _player(player_id="r1", pairing_no=3, score=4, float_history=(FloatKind.UP,)),
        _player(player_id="r2", pairing_no=4, score=3, float_history=(FloatKind.UP,)),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2"})),
        allow_bye=False,
    )

    assert _normalized_pairs(result) == {("m1", "r1"), ("m2", "r2")}


def test_c0403_c20_prefers_the_smaller_two_round_old_downfloat_score_gap() -> None:
    players = (
        _player(
            player_id="m1",
            pairing_no=1,
            score=4,
            float_history=(FloatKind.DOWN, FloatKind.NONE),
        ),
        _player(player_id="m2", pairing_no=2, score=4),
        _player(player_id="r1", pairing_no=3, score=3),
        _player(player_id="r2", pairing_no=4, score=2),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2"})),
        allow_bye=False,
    )

    assert _normalized_pairs(result) == {("m1", "r1"), ("m2", "r2")}


def test_c0403_c21_prefers_the_smaller_two_round_old_upfloat_score_gap() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=5),
        _player(player_id="m2", pairing_no=2, score=4),
        _player(
            player_id="r1",
            pairing_no=3,
            score=4,
            float_history=(FloatKind.UP, FloatKind.NONE),
        ),
        _player(
            player_id="r2",
            pairing_no=4,
            score=3,
            float_history=(FloatKind.UP, FloatKind.NONE),
        ),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2"})),
        allow_bye=False,
    )

    assert _normalized_pairs(result) == {("m1", "r1"), ("m2", "r2")}


def test_c0403_articles_3_2_to_4_2_start_from_the_first_s1_s2_candidate() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=3),
        _player(player_id="p4", pairing_no=4, score=3),
    )

    result = pair_bracket(players)

    assert _normalized_pairs(result) == {("p1", "p3"), ("p2", "p4")}


def test_c0403_articles_3_5_to_4_3_use_resident_exchanges_when_transpositions_fail() -> None:
    players = (
        _player(player_id="p1", pairing_no=1, score=3, opponents=frozenset({"p3", "p4"})),
        _player(player_id="p2", pairing_no=2, score=3),
        _player(player_id="p3", pairing_no=3, score=3),
        _player(player_id="p4", pairing_no=4, score=3, opponents=frozenset({"p1"})),
    )

    result = pair_bracket(players)

    assert _normalized_pairs(result) == {("p1", "p2"), ("p3", "p4")}


def test_c0403_articles_3_2_2_and_4_4_start_from_the_first_pairable_mdp_set() -> None:
    players = (
        _player(player_id="m1", pairing_no=1, score=5),
        _player(player_id="m2", pairing_no=2, score=5),
        _player(player_id="m3", pairing_no=3, score=5),
        _player(player_id="r1", pairing_no=4, score=4),
        _player(player_id="r2", pairing_no=5, score=4),
    )

    result = pair_bracket(
        players,
        context=BracketContext(mdp_ids=frozenset({"m1", "m2", "m3"})),
        allow_bye=False,
    )

    assert result.unpaired_ids == ("m3",)
    assert _normalized_pairs(result) == {("m1", "r1"), ("m2", "r2")}


def test_c0403_5_2_2_grants_the_wider_absolute_preference_for_topscorers() -> None:
    players = (
        _player(
            player_id="wider",
            pairing_no=1,
            score=4,
            color_history=("white", "white", "white"),
            is_top_scorer=True,
        ),
        _player(
            player_id="narrower",
            pairing_no=2,
            score=4,
            color_history=("white", "white"),
            is_top_scorer=True,
        ),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.pairings[0].black_id == "wider"


def test_c0403_5_2_3_alternates_from_the_most_recent_opposite_colors() -> None:
    players = (
        _player(
            player_id="first",
            pairing_no=1,
            score=3,
            color_history=("white", "black", "black", "white"),
        ),
        _player(
            player_id="second",
            pairing_no=2,
            score=3,
            color_history=("black", "white", "black", "white"),
        ),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.pairings[0].white_id == "first"
    assert result.pairings[0].black_id == "second"


def test_c0403_5_2_4_prefers_the_higher_ranked_players_preference_when_other_steps_tie() -> None:
    players = (
        _player(player_id="higher", pairing_no=1, score=3, color_history=("black", "white")),
        _player(
            player_id="lower",
            pairing_no=2,
            score=3,
            color_history=("white", "black", "black", "white"),
        ),
    )

    result = pair_bracket(players)

    assert len(result.pairings) == 1
    assert result.pairings[0].black_id == "higher"


def test_c0403_5_1_and_5_2_5_use_the_initial_color_when_other_steps_tie() -> None:
    players = (
        _player(player_id="odd", pairing_no=1, score=3),
        _player(player_id="even", pairing_no=2, score=3),
    )

    white_first = pair_bracket(players, initial_color="white")
    black_first = pair_bracket(players, initial_color="black")

    assert len(white_first.pairings) == 1
    assert white_first.pairings[0].white_id == "odd"
    assert white_first.pairings[0].black_id == "even"

    assert len(black_first.pairings) == 1
    assert black_first.pairings[0].white_id == "even"
    assert black_first.pairings[0].black_id == "odd"


RULE_GROUPS = (
    RuleGroup(
        status="process_only",
        reason=(
            "These clauses are organizer or arbiter policy and are outside the "
            "pairing core's public API."
        ),
        clauses=(
            "C0401.1",
            "C0401.9",
            "C0402.1.1",
            "C0402.1.2",
            "C0402.1.2.1",
            "C0402.1.2.2",
            "C0402.1.3",
            "C0402.1.5",
            "C0402.4.1",
            "C0402.4.2",
            "C0402.4.4",
            "C0402.4.4.1",
            "C0402.4.4.2",
            "C0402.4.4.3",
            "C0402.4.4.4",
            "C0402.4.4.5",
            "C0403.1.9.3",
        ),
    ),
    RuleGroup(
        status="input_contract",
        reason=(
            "The pairing core consumes pre-normalized player state; these rules "
            "are enforced by caller-supplied inputs rather than by internal "
            "derivation."
        ),
        clauses=(
            "C0402.2.1",
            "C0402.2.2",
            "C0402.2.2.1",
            "C0402.2.2.2",
            "C0402.2.2.3",
            "C0402.2.3",
            "C0402.2.4",
            "C0402.2.5",
            "C0402.3.1",
            "C0402.3.2",
            "C0402.3.3",
            "C0402.3.4",
            "C0402.3.5",
            "C0402.4.3",
            "C0402.4.3.1",
            "C0402.4.3.2",
            "C0402.4.3.3",
            "C0403.1.1",
            "C0403.1.8",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The solver is deterministic for identical inputs, which is the "
            "directly observable part of this rule in the current API."
        ),
        clauses=("C0402.1.4",),
        tests=("test_c0402_1_4_is_reproducible_for_identical_input",),
    ),
    RuleGroup(
        status="tested",
        reason="No-rematch handling is directly enforced by `pair_bracket()`.",
        clauses=("C0401.2", "C0403.2.1", "C0403.2.1.1"),
        tests=("test_c0401_rule_2_and_c0403_c1_forbid_rematches",),
    ),
    RuleGroup(
        status="tested",
        reason="Pairing-allocated byes are emitted as a single pairing with `black_id=None`.",
        clauses=("C0401.3", "C0403.1.5"),
        tests=("test_c0401_rules_3_and_4_assign_a_single_legal_pairing_allocated_bye",),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The bye-eligibility path now excludes both previous pairing-"
            "allocated byes and previous non-PAB full-point unplayed rounds."
        ),
        clauses=("C0401.4", "C0403.2.1.2"),
        tests=(
            "test_c0401_rules_3_and_4_assign_a_single_legal_pairing_allocated_bye",
            "test_c0401_rule_4_and_c0403_c2_exclude_previous_full_point_unplayed_rounds_from_pab",
        ),
    ),
    RuleGroup(
        status="input_contract",
        reason=(
            "Whether a previous unplayed scoring round counts as a downfloat is "
            "consumed through caller-supplied `float_history`."
        ),
        clauses=("C0403.1.4.3",),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The round pipeline keeps same-score pairings when possible and uses "
            "score-plus-TPN ordering across brackets."
        ),
        clauses=(
            "C0401.5",
            "C0403.1.2",
            "C0403.1.2.1",
            "C0403.1.2.2",
            "C0403.1.3",
            "C0403.1.3.1",
            "C0403.1.3.2",
            "C0403.1.3.3",
            "C0403.1.3.4",
            "C0403.1.9",
            "C0403.1.9.1",
            "C0403.1.9.2",
        ),
        tests=(
            "test_c0401_rule_5_pairs_players_on_the_same_score_when_possible",
            "test_c0403_1_3_2_and_1_9_2_carry_mdps_into_the_next_scoregroup",
            "test_c0403_1_9_1_and_c4_raise_on_impossible_round_pairing",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "Color difference and the absolute, strong, mild, and absent "
            "preference classes are derived directly from "
            "`PlayerState.color_history`."
        ),
        clauses=(
            "C0401.6",
            "C0401.7",
            "C0401.8",
            "C0403.1.6",
            "C0403.1.7",
            "C0403.1.7.1",
            "C0403.1.7.2",
            "C0403.1.7.3",
            "C0403.1.7.4",
        ),
        tests=("test_c0403_model_derives_color_difference_and_preferences",),
    ),
    RuleGroup(
        status="tested",
        reason="Publication ordering is directly observable from the returned pairing sequence.",
        clauses=("C0402.3.6", "C0402.3.6.1", "C0402.3.6.2", "C0402.3.6.3"),
        tests=("test_c0402_3_6_sorts_pairings_for_publication",),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "Non-final brackets expose their downfloaters via `unpaired_ids`, "
            "and the solver maximizes the number of pairs before leaving one "
            "player unresolved."
        ),
        clauses=("C0403.1.4.1", "C0403.2.2", "C0403.2.4.1"),
        tests=("test_c0403_1_4_1_and_c6_downfloat_the_single_unavoidable_player",),
    ),
    RuleGroup(
        status="not_represented",
        reason=(
            "The public result type does not emit float assignments after a "
            "round, so these post-pairing float-definition clauses are not "
            "directly testable yet."
        ),
        clauses=("C0403.1.4", "C0403.1.4.2", "C0403.1.4.4"),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The absolute same-preference restriction and the topscorer "
            "exception are both observable through `pair_bracket()`."
        ),
        clauses=("C0403.2.1.3",),
        tests=(
            "test_c0403_c3_blocks_non_topscorers_with_the_same_absolute_preference",
            "test_c0403_c3_allows_the_topscorer_exception",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The round solver either returns a complete round pairing or raises "
            "when [C4] cannot be satisfied."
        ),
        clauses=("C0403.2.2.1",),
        tests=("test_c0403_1_9_1_and_c4_raise_on_impossible_round_pairing",),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The bye criterion is observable through minimal odd-bracket cases "
            "and round-level bracket collapse cases."
        ),
        clauses=("C0403.2.3", "C0403.2.3.1"),
        tests=(
            "test_c0401_rules_3_and_4_assign_a_single_legal_pairing_allocated_bye",
            "test_c0403_c9_breaks_pab_ties_by_unplayed_games",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The quality-criterion stack from [C6] to [C21] is covered with "
            "minimal constructed bracket cases."
        ),
        clauses=(
            "C0403.2.4",
            "C0403.2.4.2",
            "C0403.2.4.3",
            "C0403.2.4.4",
            "C0403.2.4.5",
            "C0403.2.4.6",
            "C0403.2.4.7",
            "C0403.2.4.8",
            "C0403.2.4.9",
            "C0403.2.4.10",
            "C0403.2.4.11",
            "C0403.2.4.12",
            "C0403.2.4.13",
            "C0403.2.4.14",
            "C0403.2.4.15",
            "C0403.2.4.16",
        ),
        tests=(
            "test_c0403_c7_prefers_lower_scoring_limbo_players",
            "test_c0403_c8_uses_next_bracket_lookahead",
            "test_c0403_c9_breaks_pab_ties_by_unplayed_games",
            "test_c0403_c10_and_c11_keep_a_topscorer_on_their_absolute_color",
            "test_c0403_c12_and_c13_prefer_fulfilling_the_stronger_color_preference",
            "test_c0403_c14_and_c16_avoid_repeat_resident_downfloaters",
            "test_c0403_c15_and_c17_avoid_repeat_upfloat_opponents_for_mdps",
            "test_c0403_c18_prefers_the_smaller_previous_downfloat_score_gap",
            "test_c0403_c19_prefers_the_smaller_previous_upfloat_score_gap",
            "test_c0403_c20_prefers_the_smaller_two_round_old_downfloat_score_gap",
            "test_c0403_c21_prefers_the_smaller_two_round_old_upfloat_score_gap",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The public bracket outcome exposes the M0 / MaxPairs / M1 concepts "
            "through which MDPs are paired and which players remain unresolved."
        ),
        clauses=("C0403.3.1", "C0403.3.1.1", "C0403.3.1.2", "C0403.3.1.3"),
        tests=(
            "test_c0403_1_4_1_and_c6_downfloat_the_single_unavoidable_player",
            "test_c0403_articles_3_2_2_and_4_4_start_from_the_first_pairable_mdp_set",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The initial S1/S2 split, Limbo handling, and first candidate "
            "construction are observable through small homogeneous and "
            "heterogeneous examples."
        ),
        clauses=(
            "C0403.3.2",
            "C0403.3.2.1",
            "C0403.3.2.2",
            "C0403.3.2.3",
            "C0403.3.2.4",
            "C0403.3.3",
            "C0403.3.3.1",
            "C0403.3.3.2",
            "C0403.3.3.3",
            "C0403.3.3.4",
        ),
        tests=(
            "test_c0403_articles_3_2_to_4_2_start_from_the_first_s1_s2_candidate",
            "test_c0403_articles_3_2_2_and_4_4_start_from_the_first_pairable_mdp_set",
            "test_c0403_c7_prefers_lower_scoring_limbo_players",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "Candidate evaluation, alteration, and best-candidate selection are "
            "exercised by transposition, exchange, and criteria-priority cases."
        ),
        clauses=(
            "C0403.3.4",
            "C0403.3.4.1",
            "C0403.3.5",
            "C0403.3.5.1",
            "C0403.3.5.2",
            "C0403.3.5.3",
            "C0403.3.6",
            "C0403.3.6.1",
            "C0403.3.7",
            "C0403.3.7.1",
            "C0403.3.7.2",
            "C0403.3.7.3",
            "C0403.3.8",
            "C0403.3.8.1",
        ),
        tests=(
            "test_c0403_articles_3_2_to_4_2_start_from_the_first_s1_s2_candidate",
            "test_c0403_articles_3_5_to_4_3_use_resident_exchanges_when_transpositions_fail",
            "test_c0403_c7_prefers_lower_scoring_limbo_players",
            "test_c0403_c18_prefers_the_smaller_previous_downfloat_score_gap",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "BSN-driven transposition, exchange, pairable-MDP selection, and "
            "next-element sequencing are observable through deterministic "
            "small-bracket outcomes."
        ),
        clauses=(
            "C0403.4.1",
            "C0403.4.1.1",
            "C0403.4.2",
            "C0403.4.2.1",
            "C0403.4.2.2",
            "C0403.4.3",
            "C0403.4.3.1",
            "C0403.4.3.2",
            "C0403.4.4",
            "C0403.4.4.1",
            "C0403.4.4.2",
            "C0403.4.5",
            "C0403.4.5.1",
        ),
        tests=(
            "test_c0403_articles_3_2_to_4_2_start_from_the_first_s1_s2_candidate",
            "test_c0403_articles_3_5_to_4_3_use_resident_exchanges_when_transpositions_fail",
            "test_c0403_articles_3_2_2_and_4_4_start_from_the_first_pairable_mdp_set",
        ),
    ),
    RuleGroup(
        status="partially_tested",
        reason=(
            "Color allocation is fully covered where the current package has a "
            "public input surface for it, but the parent article remains mixed "
            "with earlier input-contract rules."
        ),
        clauses=("C0403.5.2",),
        tests=(
            "test_c0403_5_2_1_grants_both_compatible_color_preferences",
            "test_c0403_c10_and_c11_keep_a_topscorer_on_their_absolute_color",
            "test_c0403_c12_and_c13_prefer_fulfilling_the_stronger_color_preference",
            "test_c0403_5_2_2_grants_the_wider_absolute_preference_for_topscorers",
            "test_c0403_5_2_3_alternates_from_the_most_recent_opposite_colors",
            "test_c0403_5_2_4_prefers_the_higher_ranked_players_preference_when_other_steps_tie",
            "test_c0403_5_1_and_5_2_5_use_the_initial_color_when_other_steps_tie",
        ),
    ),
    RuleGroup(
        status="tested",
        reason=(
            "The implemented color-order path now covers article 5.1 and the "
            "full article-5.2 tie-break chain."
        ),
        clauses=(
            "C0403.5.1",
            "C0403.5.2.1",
            "C0403.5.2.2",
            "C0403.5.2.3",
            "C0403.5.2.4",
            "C0403.5.2.5",
        ),
        tests=(
            "test_c0403_5_2_1_grants_both_compatible_color_preferences",
            "test_c0403_c10_and_c11_keep_a_topscorer_on_their_absolute_color",
            "test_c0403_c12_and_c13_prefer_fulfilling_the_stronger_color_preference",
            "test_c0403_5_2_2_grants_the_wider_absolute_preference_for_topscorers",
            "test_c0403_5_2_3_alternates_from_the_most_recent_opposite_colors",
            "test_c0403_5_2_4_prefers_the_higher_ranked_players_preference_when_other_steps_tie",
            "test_c0403_5_1_and_5_2_5_use_the_initial_color_when_other_steps_tie",
        ),
    ),
)


def test_rulebook_clause_accounting_matches_local_2026_markdown() -> None:
    grouped_ids = [clause for group in RULE_GROUPS for clause in group.clauses]
    grouped_set = set(grouped_ids)
    doc_set = set(DOC_RULE_IDS)

    assert len(grouped_ids) == len(grouped_set)
    assert grouped_set == doc_set

    available_tests = {
        name for name, value in globals().items() if name.startswith("test_") and callable(value)
    }
    for group in RULE_GROUPS:
        if group.status in {"tested", "partially_tested", "xfail"}:
            assert group.tests
            assert set(group.tests) <= available_tests
