"""Dutch-oriented bracket pairing with staged criteria evaluation.

The module still uses graph matching for candidate construction, but candidate
selection is evaluated with a C.04.3-inspired criterion key [C5]-[C21].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from itertools import combinations, permutations
from math import comb, perm
from typing import TYPE_CHECKING, cast

from swisspairing._matching import compute_maximum_weight_matching_total
from swisspairing.exceptions import ExactSearchUnavailableError, PairingError
from swisspairing.model import (
    Color,
    FloatAssignment,
    FloatKind,
    Pairing,
    PairingResult,
    PlayerState,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

type NextBracketValidator = Callable[[tuple[PlayerState, ...]], bool]


@dataclass(frozen=True, order=True, slots=True)
class NextBracketLocalKey:
    """Immediate next-bracket quality summary used for [C8] tie-breaks."""

    c5: int = 0
    c6: int = 0
    c7: tuple[int, ...] = ()
    c9: int = 0
    c10: int = 0
    c11: int = 0
    c12: int = 0
    c13: int = 0
    c14: int = 0
    c15: int = 0
    c16: int = 0
    c17: int = 0
    c18: tuple[int, ...] = ()
    c19: tuple[int, ...] = ()
    c20: tuple[int, ...] = ()
    c21: tuple[int, ...] = ()


@dataclass(frozen=True, order=True, slots=True)
class NextBracketKey:
    """Structured [C8] tie-break key with a fixed, recursively safe shape."""

    local: NextBracketLocalKey = field(default_factory=NextBracketLocalKey)
    future_game_counts: tuple[int, ...] = ()


_EMPTY_NEXT_BRACKET_KEY = NextBracketKey()


type NextBracketKeyFn = Callable[[tuple[PlayerState, ...]], NextBracketKey | None]


@dataclass(frozen=True, slots=True)
class _ExtendedNextBracketValidator:
    """Hashable validator wrapper that appends fixed downfloaters.

    This keeps equivalent [C8] validator shapes cacheable across repeated exact
    feasibility checks instead of creating identity-unique nested closures.
    """

    validator_fn: NextBracketValidator
    fixed_downfloaters: tuple[PlayerState, ...]

    def __call__(self, remainder_downfloaters: tuple[PlayerState, ...]) -> bool:
        full_downfloaters = tuple(
            sorted(
                (*remainder_downfloaters, *self.fixed_downfloaters),
                key=_player_rank_key,
            )
        )
        return self.validator_fn(full_downfloaters)


def _extend_next_bracket_validator(
    validator: NextBracketValidator,
    *,
    fixed_downfloaters: tuple[PlayerState, ...],
) -> NextBracketValidator:
    ordered_fixed = tuple(sorted(fixed_downfloaters, key=_player_rank_key))
    if isinstance(validator, _ExtendedNextBracketValidator):
        return _ExtendedNextBracketValidator(
            validator_fn=validator.validator_fn,
            fixed_downfloaters=tuple(
                sorted(
                    (*validator.fixed_downfloaters, *ordered_fixed),
                    key=_player_rank_key,
                )
            ),
        )
    return _ExtendedNextBracketValidator(
        validator_fn=validator,
        fixed_downfloaters=ordered_fixed,
    )


@dataclass(frozen=True, slots=True)
class BracketContext:
    """Optional context used by advanced Dutch quality criteria.

    Fields:
    - `mdp_ids`: moved-down players (MDPs) entering this bracket.
    - `initial_color`: TRF-configured article 5.2.5 first-round color.
    - `next_bracket_validator`: optional callback for [C8]. If provided,
      downfloaters are passed in ranking order. The callback should return
      `True` when the next-bracket [C1]-[C7] outlook is acceptable.
    - `next_bracket_key`: optional deterministic tie-break for [C8]. When the
      next bracket is feasible for multiple downfloater sets, this lets the
      round pipeline prefer the set that leads to the better downstream
      pairing outlook.
    """

    mdp_ids: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    initial_color: Color = "white"
    next_bracket_validator: NextBracketValidator | None = None
    next_bracket_key: NextBracketKeyFn | None = None


@dataclass(frozen=True, slots=True)
class _EvenPairingInternal:
    """Internal solve result for one even-sized player set."""

    pairings: tuple[tuple[PlayerState, PlayerState], ...]
    unresolved: tuple[PlayerState, ...]


@dataclass(frozen=True, slots=True)
class _CandidateInternal:
    """A candidate bracket pairing used for [C5]-[C21] comparison."""

    pairings: tuple[tuple[PlayerState, PlayerState], ...]
    unresolved: tuple[PlayerState, ...]
    bye_player: PlayerState | None
    sequence_no: int


def _player_rank_key(player: PlayerState) -> tuple[int, int]:
    """Ranking order per C.04.3 section 1.2 (score desc, TPN asc)."""
    return (-player.score, player.pairing_no)


def _context_with_initial_color(
    context: BracketContext | None,
    *,
    initial_color: Color,
) -> BracketContext:
    if context is None:
        return BracketContext(initial_color=initial_color)
    if context.initial_color == initial_color:
        return context
    return BracketContext(
        mdp_ids=context.mdp_ids,
        initial_color=initial_color,
        next_bracket_validator=context.next_bracket_validator,
        next_bracket_key=context.next_bracket_key,
    )


def _is_legal_pair(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    context: BracketContext | None = None,
) -> bool:
    """Return whether two players may be paired under implemented absolutes.

    Rule references:
    - C.04.1 rule 2 / C.04.3 [C1]: no rematch.
    - C.04.3 [C3]: non-topscorers with same absolute color preference shall not meet.
    """
    if player_b.player_id in player_a.opponents:
        return False
    if player_a.player_id in player_b.opponents:
        return False
    if player_b.player_id in player_a.forbidden_opponents:
        return False
    if player_a.player_id in player_b.forbidden_opponents:
        return False

    if context is not None and context.mdp_ids:
        if player_a.player_id in context.mdp_ids and player_b.player_id in context.mdp_ids:
            return False

    if not (player_a.is_top_scorer or player_b.is_top_scorer):
        pref_a = player_a.absolute_color_preference
        pref_b = player_b.absolute_color_preference
        if pref_a is not None and pref_a == pref_b:
            return False

    return True


def _applied_color_difference(player: PlayerState, *, gets_white: bool) -> int:
    """Compute color difference after assigning one more game color."""
    return player.color_difference + (1 if gets_white else -1)


def _would_get_three_in_row(player: PlayerState, assigned_color: str) -> bool:
    """Return whether assignment yields three equal colors in a row (C11)."""
    if len(player.color_history) < 2:
        return False
    return player.color_history[-1] == assigned_color and player.color_history[-2] == assigned_color


def _is_preference_missed(player: PlayerState, assigned_color: str) -> bool:
    preference = player.color_preference
    return preference is not None and preference != assigned_color


def _is_strong_preference_missed(player: PlayerState, assigned_color: str) -> bool:
    # C11 applies to strong-or-stronger preferences, so absolute preferences
    # must count here as well.
    strong_or_absolute_preference = (
        player.absolute_color_preference or player.strong_color_preference
    )
    return (
        strong_or_absolute_preference is not None
        and strong_or_absolute_preference != assigned_color
    )


@cache
def _pair_color_quality_cached(
    white: PlayerState,
    black: PlayerState,
) -> tuple[int, int, int, int]:
    """Return local [C10]-[C13] penalties for an oriented pair."""
    c10 = int(
        white.is_topscorer_or_opponent
        and abs(_applied_color_difference(white, gets_white=True)) > 2
    ) + int(
        black.is_topscorer_or_opponent
        and abs(_applied_color_difference(black, gets_white=False)) > 2
    )

    c11 = int(white.is_topscorer_or_opponent and _would_get_three_in_row(white, "white")) + int(
        black.is_topscorer_or_opponent and _would_get_three_in_row(black, "black")
    )

    c12 = int(_is_preference_missed(white, "white")) + int(_is_preference_missed(black, "black"))
    c13 = int(_is_strong_preference_missed(white, "white")) + int(
        _is_strong_preference_missed(black, "black")
    )
    return c10, c11, c12, c13


def _pair_color_quality(
    *,
    white: PlayerState,
    black: PlayerState,
) -> tuple[int, int, int, int]:
    return _pair_color_quality_cached(white, black)


def _preference_strength(player: PlayerState) -> int:
    if player.absolute_color_preference is not None:
        return 3
    if player.strong_color_preference is not None:
        return 2
    if player.mild_color_preference is not None:
        return 1
    return 0


def _preference_is_granted(player: PlayerState, assigned_color: Color) -> bool:
    preference = player.color_preference
    return preference is None or preference == assigned_color


def _missed_preference_strengths(
    *,
    white: PlayerState,
    black: PlayerState,
) -> tuple[int, ...]:
    missed_strengths: list[int] = []
    if not _preference_is_granted(white, "white"):
        missed_strengths.append(_preference_strength(white))
    if not _preference_is_granted(black, "black"):
        missed_strengths.append(_preference_strength(black))
    return tuple(sorted(missed_strengths, reverse=True))


def _granted_absolute_color_difference(
    *,
    white: PlayerState,
    black: PlayerState,
) -> int:
    if not (
        white.is_top_scorer
        and black.is_top_scorer
        and white.absolute_color_preference is not None
        and black.absolute_color_preference is not None
    ):
        return 0

    granted_differences: list[int] = []
    if white.absolute_color_preference == "white":
        granted_differences.append(abs(white.color_difference))
    if black.absolute_color_preference == "black":
        granted_differences.append(abs(black.color_difference))
    if not granted_differences:
        return 0
    return max(granted_differences)


def _alternating_assignment(
    player_a: PlayerState,
    player_b: PlayerState,
) -> tuple[Color, Color] | None:
    for color_a, color_b in zip(
        reversed(player_a.color_history),
        reversed(player_b.color_history),
        strict=False,
    ):
        if color_a == color_b:
            continue
        next_color_a: Color = "black" if color_a == "white" else "white"
        next_color_b: Color = "black" if color_b == "white" else "white"
        return next_color_a, next_color_b
    return None


def _higher_rank_preference_missed(
    *,
    white: PlayerState,
    black: PlayerState,
) -> int:
    higher_ranked, assigned_color = (
        (white, "white") if _player_rank_key(white) <= _player_rank_key(black) else (black, "black")
    )
    preference = higher_ranked.color_preference
    if preference is None:
        return 0
    return int(preference != assigned_color)


def _initial_color_tie_break_missed(
    *,
    white: PlayerState,
    black: PlayerState,
    initial_color: Color,
) -> int:
    higher_ranked, assigned_color = (
        (white, "white") if _player_rank_key(white) <= _player_rank_key(black) else (black, "black")
    )
    expected_color: Color = (
        initial_color
        if higher_ranked.pairing_no % 2 == 1
        else ("black" if initial_color == "white" else "white")
    )
    return int(assigned_color != expected_color)


@cache
def _color_allocation_key(
    white: PlayerState,
    black: PlayerState,
    initial_color: Color,
) -> tuple[int, tuple[int, ...], int, int, int, int]:
    both_preferences_granted = int(
        not (_preference_is_granted(white, "white") and _preference_is_granted(black, "black"))
    )
    missed_strengths = _missed_preference_strengths(white=white, black=black)
    wider_absolute_difference = -_granted_absolute_color_difference(white=white, black=black)

    alternating_assignment = _alternating_assignment(white, black)
    alternation_missed = 0
    if alternating_assignment is not None:
        alternation_missed = int(alternating_assignment != ("white", "black"))

    higher_rank_preference_missed = _higher_rank_preference_missed(white=white, black=black)
    initial_color_tie_break_missed = _initial_color_tie_break_missed(
        white=white,
        black=black,
        initial_color=initial_color,
    )

    return (
        both_preferences_granted,
        missed_strengths,
        wider_absolute_difference,
        alternation_missed,
        higher_rank_preference_missed,
        initial_color_tie_break_missed,
    )


@cache
def _choose_color_order_cached(
    player_a: PlayerState,
    player_b: PlayerState,
    initial_color: Color,
) -> tuple[PlayerState, PlayerState]:
    """Pick white/black order following C.04.3 article 5.2 tie-breaks."""
    rank_a = _player_rank_key(player_a)
    rank_b = _player_rank_key(player_b)
    first_key = (
        *_color_allocation_key(player_a, player_b, initial_color),
        rank_a,
        rank_b,
    )
    second_key = (
        *_color_allocation_key(player_b, player_a, initial_color),
        rank_b,
        rank_a,
    )
    if first_key <= second_key:
        return player_a, player_b
    return player_b, player_a


def _choose_color_order(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    initial_color: Color = "white",
) -> tuple[PlayerState, PlayerState]:
    return _choose_color_order_cached(player_a, player_b, initial_color)


def _mdp_and_opponent(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    context: BracketContext,
) -> tuple[PlayerState, PlayerState] | None:
    """Return `(mdp, opponent)` if the pair is MDP-vs-resident, else `None`."""
    a_is_mdp = player_a.player_id in context.mdp_ids
    b_is_mdp = player_b.player_id in context.mdp_ids
    if a_is_mdp == b_is_mdp:
        return None
    if a_is_mdp:
        return player_a, player_b
    return player_b, player_a


def _pair_score_difference(player_a: PlayerState, player_b: PlayerState) -> int:
    return abs(player_a.score - player_b.score)


def _edge_penalty_components(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    context: BracketContext,
) -> tuple[int, int, int, int, int, int, int, int, int, int]:
    return _edge_penalty_components_cached(
        player_a,
        player_b,
        context.mdp_ids,
        context.initial_color,
    )


@cache
def _edge_penalty_components_cached(
    player_a: PlayerState,
    player_b: PlayerState,
    mdp_ids: frozenset[str],
    initial_color: Color,
) -> tuple[int, int, int, int, int, int, int, int, int, int]:
    """Return local penalty components mapped to [C10]-[C13], [C15], [C17]-[C21]."""
    context = BracketContext(mdp_ids=mdp_ids, initial_color=initial_color)
    white, black = _choose_color_order(player_a, player_b, initial_color=initial_color)
    c10, c11, c12, c13 = _pair_color_quality(white=white, black=black)

    c15 = 0
    c17 = 0
    c18 = 0
    c19 = 0
    c20 = 0
    c21 = 0

    mdp_pair = _mdp_and_opponent(player_a, player_b, context=context)
    if mdp_pair is not None:
        mdp_player, opponent = mdp_pair
        score_difference = _pair_score_difference(mdp_player, opponent)

        # C15/C17: opponent-side upfloat history.
        c15 = int(opponent.had_float(rounds_ago=1, kind=FloatKind.UP))
        c17 = int(opponent.had_float(rounds_ago=2, kind=FloatKind.UP))

        # C18/C20: MDP-side downfloat history.
        c18 = score_difference if mdp_player.had_float(rounds_ago=1, kind=FloatKind.DOWN) else 0
        c20 = score_difference if mdp_player.had_float(rounds_ago=2, kind=FloatKind.DOWN) else 0

        # C19/C21: opponent-side upfloat history, weighted by score difference.
        c19 = score_difference if opponent.had_float(rounds_ago=1, kind=FloatKind.UP) else 0
        c21 = score_difference if opponent.had_float(rounds_ago=2, kind=FloatKind.UP) else 0

    return c10, c11, c12, c13, c15, c17, c18, c19, c20, c21


# Exact article-4.x sequence expansion grows factorially by S2 size.
_SEQUENTIAL_SEARCH_MAX_PLAYERS = 12
_MAX_EXACT_SEQUENCE_CANDIDATES = 50_000
_SINGLE_MDP_ODD_EXACT_MAX_PLAYERS = 24


@cache
def _homogeneous_exact_candidate_upper_bound(player_count: int) -> int:
    """Return an article-order upper bound for homogeneous exact candidates.

    Candidate generation combines every legal resident-exchange specification
    with every article-4.2 S2 prefix transposition for the resulting split.
    The exact count grows quickly:
    - 8 players -> 1,680 candidates
    - 9 players -> 15,120 candidates
    - 10 players -> 30,240 candidates
    - 12 players -> 665,280 candidates

    Keep the exact path only while the article-order candidate space stays
    within a tractable budget; larger homogeneous brackets currently require
    a more specialized exact solver.
    """
    if player_count <= 1:
        return 1
    split_size = player_count // 2
    s2_size = player_count - split_size
    return perm(s2_size, split_size) * comb(player_count, split_size)


@cache
def _heterogeneous_exact_candidate_upper_bound(
    player_count: int,
    mdp_count: int,
) -> int:
    """Return an article-order upper bound for heterogeneous exact candidates."""
    resident_count = player_count - mdp_count
    if mdp_count <= 0 or resident_count <= 0:
        return 0

    m1 = min(mdp_count, resident_count)
    return (
        comb(mdp_count, m1)
        * perm(resident_count, m1)
        * _homogeneous_exact_candidate_upper_bound(resident_count - m1)
    )


def _use_homogeneous_exact_search(
    player_count: int,
    *,
    sequential_search_max_players: int,
    exact_candidate_max: int = _MAX_EXACT_SEQUENCE_CANDIDATES,
) -> bool:
    return (
        player_count <= sequential_search_max_players
        and _homogeneous_exact_candidate_upper_bound(player_count) <= exact_candidate_max
    )


def _use_heterogeneous_exact_search(
    player_count: int,
    *,
    mdp_count: int,
    sequential_search_max_players: int,
    exact_candidate_max: int = _MAX_EXACT_SEQUENCE_CANDIDATES,
) -> bool:
    return (
        player_count <= sequential_search_max_players
        and _heterogeneous_exact_candidate_upper_bound(player_count, mdp_count)
        <= exact_candidate_max
    )


def _exchange_sort_key(
    *,
    s1_out_bsns: tuple[int, ...],
    s2_in_bsns: tuple[int, ...],
) -> tuple[int, int, tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Sort resident exchanges per C.04.3 article 4.3.2."""
    exchange_size = len(s1_out_bsns)
    sum_difference = abs(sum(s2_in_bsns) - sum(s1_out_bsns))
    s1_descending = tuple(sorted(s1_out_bsns, reverse=True))
    s2_ascending = tuple(sorted(s2_in_bsns))
    return (
        exchange_size,
        sum_difference,
        tuple(-bsn for bsn in s1_descending),
        s2_ascending,
        s1_descending,
        s2_in_bsns,
    )


@cache
def _iter_resident_exchanges_cached(
    players: tuple[PlayerState, ...],
    *,
    max_exchange_size: int | None = None,
) -> tuple[tuple[tuple[PlayerState, ...], tuple[PlayerState, ...]], ...]:
    """Yield `(S1, S2)` compositions in article-4.3 exchange order."""
    ordered_players = players
    split = len(ordered_players) // 2
    original_s1 = ordered_players[:split]
    original_s2 = ordered_players[split:]

    specs: list[
        tuple[
            tuple[int, int, tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]],
            tuple[int, ...],
            tuple[int, ...],
        ]
    ] = []
    exchange_size_limit = min(len(original_s1), len(original_s2))
    if max_exchange_size is not None:
        exchange_size_limit = min(exchange_size_limit, max_exchange_size)

    for exchange_size in range(exchange_size_limit + 1):
        for s1_out_indices in combinations(range(len(original_s1)), exchange_size):
            for s2_in_indices in combinations(range(len(original_s2)), exchange_size):
                s1_out_bsns = tuple(index + 1 for index in s1_out_indices)
                s2_in_bsns = tuple(split + index + 1 for index in s2_in_indices)
                sort_key = _exchange_sort_key(
                    s1_out_bsns=s1_out_bsns,
                    s2_in_bsns=s2_in_bsns,
                )
                specs.append((sort_key, s1_out_indices, s2_in_indices))

    specs.sort(key=lambda entry: entry[0])

    generated: list[tuple[tuple[PlayerState, ...], tuple[PlayerState, ...]]] = []
    for _, s1_out_indices, s2_in_indices in specs:
        s1_out_set = frozenset(s1_out_indices)
        s2_in_set = frozenset(s2_in_indices)

        new_s1 = [player for index, player in enumerate(original_s1) if index not in s1_out_set]
        new_s1.extend(original_s2[index] for index in s2_in_indices)
        new_s2 = [player for index, player in enumerate(original_s2) if index not in s2_in_set]
        new_s2.extend(original_s1[index] for index in s1_out_indices)

        generated.append(
            (
                tuple(sorted(new_s1, key=_player_rank_key)),
                tuple(sorted(new_s2, key=_player_rank_key)),
            )
        )

    return tuple(generated)


def _iter_resident_exchanges(
    players: Sequence[PlayerState],
    *,
    max_exchange_size: int | None = None,
) -> Sequence[tuple[tuple[PlayerState, ...], tuple[PlayerState, ...]]]:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    return _iter_resident_exchanges_cached(
        ordered_players,
        max_exchange_size=max_exchange_size,
    )


def _iter_s2_transpositions(
    *,
    s1: Sequence[PlayerState],
    s2: Sequence[PlayerState],
    bsn_by_player_id: dict[str, int],
) -> Sequence[tuple[PlayerState, ...]]:
    """Yield S2 transpositions in article-4.2 order.

    Article 4.2.2 orders transpositions by the first N1 BSNs only, where N1 is
    the number of players in S1. The remainder of S2 is kept in original order.
    """
    n1 = len(s1)
    s2_ordered = tuple(s2)
    s2_bsns = tuple(bsn_by_player_id[player.player_id] for player in s2_ordered)
    orderings = _iter_s2_transposition_orders(n1=n1, s2_bsns=s2_bsns)
    return [tuple(s2_ordered[index] for index in ordering) for ordering in orderings]


@cache
def _iter_s2_transposition_orders(
    *,
    n1: int,
    s2_bsns: tuple[int, ...],
) -> tuple[tuple[int, ...], ...]:
    """Return article-4.2 S2 transposition orders as index tuples."""

    transpositions: list[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = []
    s2_indices = tuple(range(len(s2_bsns)))

    for prefix in permutations(s2_indices, n1):
        prefix_set = frozenset(prefix)
        tail = tuple(index for index in s2_indices if index not in prefix_set)
        candidate = tuple((*prefix, *tail))
        prefix_key = tuple(s2_bsns[index] for index in prefix)
        full_key = tuple(s2_bsns[index] for index in candidate)
        transpositions.append((prefix_key, full_key, candidate))

    transpositions.sort(key=lambda entry: (entry[0], entry[1]))
    return tuple(entry[2] for entry in transpositions)


def _candidate_pair_sort_key(
    pair: tuple[PlayerState, PlayerState],
) -> tuple[tuple[int, int], tuple[int, int]]:
    return _player_rank_key(pair[0]), _player_rank_key(pair[1])


def _canonical_candidate_shape(
    candidate: _CandidateInternal,
) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], int | None]:
    canonical_pairs = tuple(
        sorted(
            (
                (left.pairing_no, right.pairing_no)
                if left.pairing_no <= right.pairing_no
                else (right.pairing_no, left.pairing_no)
            )
            for left, right in candidate.pairings
        )
    )
    unresolved_ids = tuple(player.pairing_no for player in candidate.unresolved)
    bye_id = None if candidate.bye_player is None else candidate.bye_player.pairing_no
    return canonical_pairs, unresolved_ids, bye_id


@cache
def _homogeneous_article_order_key(
    *,
    players: tuple[PlayerState, ...],
    candidate: _CandidateInternal,
) -> tuple[int, int, tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Approximate article-4.x candidate order for large homogeneous brackets.

    The order follows the same article-4.3 then article-4.2 structure used by
    the exact generator: fewer exchanges first, then better exchange
    composition, then earlier S2 transposition order. It is used only as a
    tie-break after all quality criteria except generation order are equal.
    """
    ordered_players = players
    split_size = len(ordered_players) // 2
    original_s1_ids = {player.player_id for player in ordered_players[:split_size]}
    original_s2_ids = {player.player_id for player in ordered_players[split_size:]}

    final_s1: list[PlayerState] = []
    final_s2_by_s1: list[tuple[PlayerState, PlayerState]] = []
    for left, right in candidate.pairings:
        high = left
        low = right
        if _player_rank_key(right) < _player_rank_key(left):
            high = right
            low = left
        final_s1.append(high)
        final_s2_by_s1.append((high, low))

    final_s1_ids = {player.player_id for player in final_s1}
    moved_from_s1 = tuple(
        sorted(
            (
                player
                for player in ordered_players
                if player.player_id in original_s1_ids and player.player_id not in final_s1_ids
            ),
            key=lambda player: player.pairing_no,
        )
    )
    moved_from_s2 = tuple(
        sorted(
            (
                player
                for player in ordered_players
                if player.player_id in original_s2_ids and player.player_id in final_s1_ids
            ),
            key=lambda player: player.pairing_no,
        )
    )
    final_s2_by_s1.sort(key=lambda pair: _player_rank_key(pair[0]))
    unresolved_tail = [player.pairing_no for player in candidate.unresolved]
    final_s2_order = tuple((*[low.pairing_no for _, low in final_s2_by_s1], *unresolved_tail))

    return (
        len(moved_from_s1),
        abs(
            sum(player.pairing_no for player in moved_from_s2)
            - sum(player.pairing_no for player in moved_from_s1)
        ),
        tuple(-player.pairing_no for player in reversed(moved_from_s1)),
        tuple(player.pairing_no for player in moved_from_s2),
        final_s2_order,
    )


def _heterogeneous_structural_tie_key(
    *,
    candidate: _CandidateInternal,
    mdp_ids: frozenset[str],
) -> tuple[
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[tuple[int, int], ...],
    tuple[int, ...],
]:
    """Approximate BBP/FIDE tie resolution inside equal-quality heterogeneous cohorts.

    When [C5]-[C21] still tie exactly, checked 2026 references tend to prefer
    the candidate whose resident remainder keeps score differences tighter
    before falling back to raw generation order. Using this structural key
    only inside already-equal heterogeneous cohorts closes the checked 2026
    reference gap without perturbing the main criterion ordering.
    """

    mdp_pairs: list[tuple[PlayerState, PlayerState]] = []
    resident_pairs: list[tuple[PlayerState, PlayerState]] = []
    for left, right in candidate.pairings:
        left_is_mdp = left.player_id in mdp_ids
        right_is_mdp = right.player_id in mdp_ids
        if left_is_mdp and not right_is_mdp:
            mdp_pairs.append((left, right))
            continue
        if right_is_mdp and not left_is_mdp:
            mdp_pairs.append((right, left))
            continue
        resident_pairs.append((left, right))

    mdp_pairs.sort(key=lambda pair: _player_rank_key(pair[0]))
    resident_pairs.sort(key=_candidate_pair_sort_key)

    resident_score_differences = tuple(
        sorted(
            (_pair_score_difference(left, right) for left, right in resident_pairs),
            reverse=True,
        )
    )
    mdp_opponent_bsns = tuple(opponent.pairing_no for _, opponent in mdp_pairs)
    mdp_score_differences = tuple(
        sorted((_pair_score_difference(mdp, opponent) for mdp, opponent in mdp_pairs), reverse=True)
    )
    resident_pair_bsns = tuple(
        sorted(
            cast(
                tuple[int, int],
                tuple(sorted((left.pairing_no, right.pairing_no))),
            )
            for left, right in resident_pairs
        )
    )
    unresolved_bsns = tuple(
        player.pairing_no for player in sorted(candidate.unresolved, key=_player_rank_key)
    )

    return (
        resident_score_differences,
        mdp_opponent_bsns,
        mdp_score_differences,
        resident_pair_bsns,
        unresolved_bsns,
    )


def _select_best_candidate(
    candidates: Sequence[_CandidateInternal],
    *,
    context: BracketContext,
    dedupe_shapes: bool = True,
) -> _CandidateInternal | None:
    candidate_values: Sequence[_CandidateInternal]
    if dedupe_shapes:
        unique_candidates: dict[
            tuple[tuple[tuple[int, int], ...], tuple[int, ...], int | None],
            _CandidateInternal,
        ] = {}
        for candidate in candidates:
            shape_key = _canonical_candidate_shape(candidate)
            current = unique_candidates.get(shape_key)
            if current is None or candidate.sequence_no < current.sequence_no:
                unique_candidates[shape_key] = candidate
        candidate_values = tuple(unique_candidates.values())
    else:
        candidate_values = candidates

    best_candidate: _CandidateInternal | None = None
    best_key: tuple[object, ...] | None = None

    for candidate in candidate_values:
        candidate_key = _candidate_quality_key(candidate=candidate, context=context)
        selection_key: tuple[object, ...]
        if len(context.mdp_ids) > 1 and not candidate.unresolved and candidate.bye_player is None:
            selection_key = (
                *candidate_key[:-1],
                _heterogeneous_structural_tie_key(
                    candidate=candidate,
                    mdp_ids=context.mdp_ids,
                ),
                candidate_key[-1],
            )
        else:
            selection_key = candidate_key

        if best_key is None or selection_key < best_key:
            best_key = selection_key
            best_candidate = candidate
    return best_candidate


def _select_best_homogeneous_odd_candidate(
    players: Sequence[PlayerState],
    candidates: Sequence[_CandidateInternal],
    *,
    context: BracketContext,
) -> _CandidateInternal | None:
    """Select one odd homogeneous candidate with article-order tie-breaks."""
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    best_candidate: _CandidateInternal | None = None
    best_key_without_generation: tuple[object, ...] | None = None
    best_article_order_key: tuple[object, ...] | None = None
    best_sequence_no: int | None = None

    for candidate in candidates:
        candidate_key = _candidate_quality_key(candidate=candidate, context=context)
        key_without_generation = candidate_key[:-1]
        sequence_no = candidate.sequence_no

        if (
            best_key_without_generation is None
            or key_without_generation < best_key_without_generation
        ):
            best_key_without_generation = key_without_generation
            best_article_order_key = _homogeneous_article_order_key(
                players=ordered_players,
                candidate=candidate,
            )
            best_sequence_no = sequence_no
            best_candidate = candidate
            continue

        if key_without_generation > best_key_without_generation:
            continue

        article_order_key = _homogeneous_article_order_key(
            players=ordered_players,
            candidate=candidate,
        )
        if best_article_order_key is None or article_order_key < best_article_order_key:
            best_article_order_key = article_order_key
            best_sequence_no = sequence_no
            best_candidate = candidate
            continue

        if article_order_key > best_article_order_key:
            continue

        if best_sequence_no is None or sequence_no < best_sequence_no:
            best_sequence_no = sequence_no
            best_candidate = candidate

    return best_candidate


def _iter_exact_final_bye_candidates(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int,
    exact_candidate_max: int = _MAX_EXACT_SEQUENCE_CANDIDATES,
) -> tuple[_CandidateInternal, ...]:
    """Generate exact odd-bracket bye candidates in article sequence order."""

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if not ordered_players or len(ordered_players) % 2 == 0:
        return ()

    raw_candidates: tuple[_CandidateInternal, ...] = ()
    if context.mdp_ids and _use_heterogeneous_exact_search(
        len(ordered_players),
        mdp_count=len(context.mdp_ids),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    ):
        raw_candidates = _iter_heterogeneous_candidates(ordered_players, context=context)
    elif (not context.mdp_ids) and _use_homogeneous_exact_search(
        len(ordered_players),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    ):
        raw_candidates = _iter_homogeneous_candidates(ordered_players)

    generated: list[_CandidateInternal] = []
    for candidate in raw_candidates:
        if len(candidate.unresolved) != 1:
            continue
        generated.append(
            _CandidateInternal(
                pairings=candidate.pairings,
                unresolved=(),
                bye_player=candidate.unresolved[0],
                sequence_no=candidate.sequence_no,
            )
        )
    return tuple(generated)


@cache
def _iter_homogeneous_candidates_cached(
    players: tuple[PlayerState, ...],
    sequence_start: int = 0,
) -> tuple[_CandidateInternal, ...]:
    """Generate homogeneous-bracket candidates in article 3.6 / 4.2 / 4.3 order."""
    ordered_players = players
    if not ordered_players:
        return (
            _CandidateInternal(
                pairings=(),
                unresolved=(),
                bye_player=None,
                sequence_no=sequence_start,
            ),
        )

    bsn_by_player_id = {player.player_id: index + 1 for index, player in enumerate(ordered_players)}
    legal_opponents_by_pairing_no: dict[int, set[int]] = {
        player.pairing_no: set() for player in ordered_players
    }
    for left, right in combinations(ordered_players, 2):
        if not _is_legal_pair(left, right):
            continue
        legal_opponents_by_pairing_no[left.pairing_no].add(right.pairing_no)
        legal_opponents_by_pairing_no[right.pairing_no].add(left.pairing_no)
    generated: list[_CandidateInternal] = []
    seen_shapes: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...], int | None]] = set()
    sequence_no = sequence_start

    for s1, s2 in _iter_resident_exchanges(ordered_players):
        for s2_transposition in _iter_s2_transpositions(
            s1=s1,
            s2=s2,
            bsn_by_player_id=bsn_by_player_id,
        ):
            raw_pairs = tuple(zip(s1, s2_transposition[: len(s1)], strict=True))
            illegal_pair_found = False
            for left, right in raw_pairs:
                if right.pairing_no not in legal_opponents_by_pairing_no[left.pairing_no]:
                    illegal_pair_found = True
                    break
            if illegal_pair_found:
                continue

            unresolved = s2_transposition[len(s1) :]
            shape_key = (
                tuple(
                    sorted(
                        (
                            (left.pairing_no, right.pairing_no)
                            if left.pairing_no <= right.pairing_no
                            else (right.pairing_no, left.pairing_no)
                        )
                        for left, right in raw_pairs
                    )
                ),
                tuple(player.pairing_no for player in unresolved),
                None,
            )
            if shape_key not in seen_shapes:
                seen_shapes.add(shape_key)
                generated.append(
                    _CandidateInternal(
                        pairings=raw_pairs,
                        unresolved=unresolved,
                        bye_player=None,
                        sequence_no=sequence_no,
                    )
                )
            sequence_no += 1

    return tuple(generated)


def _iter_homogeneous_candidates(
    players: Sequence[PlayerState],
    *,
    sequence_start: int = 0,
) -> tuple[_CandidateInternal, ...]:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    return _iter_homogeneous_candidates_cached(ordered_players, sequence_start)


@cache
def _solve_even_players_via_sequence_cached(
    players: tuple[PlayerState, ...],
    initial_color: Color,
) -> _EvenPairingInternal | None:
    """Solve by exact homogeneous candidate sequence for small brackets."""
    best_candidate = _select_best_candidate(
        _iter_homogeneous_candidates(players),
        context=BracketContext(initial_color=initial_color),
        dedupe_shapes=False,
    )
    if best_candidate is None:
        return None
    return _EvenPairingInternal(
        pairings=tuple(sorted(best_candidate.pairings, key=_candidate_pair_sort_key)),
        unresolved=best_candidate.unresolved,
    )


def _solve_even_players_via_sequence_uncached(
    players: tuple[PlayerState, ...],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    best_candidate = _select_best_candidate(
        _iter_homogeneous_candidates(players),
        context=context,
        dedupe_shapes=False,
    )
    if best_candidate is None:
        return None
    return _EvenPairingInternal(
        pairings=tuple(sorted(best_candidate.pairings, key=_candidate_pair_sort_key)),
        unresolved=best_candidate.unresolved,
    )


@cache
def _solve_even_players_via_sequence_with_context_cached(
    players: tuple[PlayerState, ...],
    initial_color: Color,
    next_bracket_validator: NextBracketValidator | None,
    next_bracket_key: NextBracketKeyFn | None,
) -> _EvenPairingInternal | None:
    return _solve_even_players_via_sequence_uncached(
        players,
        context=BracketContext(
            initial_color=initial_color,
            next_bracket_validator=next_bracket_validator,
            next_bracket_key=next_bracket_key,
        ),
    )


def _solve_even_players_via_sequence(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if context.next_bracket_validator is None and context.next_bracket_key is None:
        return _solve_even_players_via_sequence_cached(
            ordered_players,
            context.initial_color,
        )
    return _solve_even_players_via_sequence_with_context_cached(
        ordered_players,
        context.initial_color,
        context.next_bracket_validator,
        context.next_bracket_key,
    )


@cache
def _homogeneous_exact_pair_penalty_cached(
    left: PlayerState,
    right: PlayerState,
    initial_color: Color,
    pair_count: int,
) -> int:
    """Pack local [C10]-[C13] penalties for exact homogeneous matching shortcuts."""
    white, black = _choose_color_order_cached(left, right, initial_color)
    c10, c11, c12, c13 = _pair_color_quality_cached(white, black)
    radix = (2 * pair_count) + 1
    return (((c10 * radix) + c11) * radix + c12) * radix + c13

@cache
def _homogeneous_legal_exact_pair_penalty(
    left: PlayerState,
    right: PlayerState,
    initial_color: Color,
    pair_count: int,
) -> int | None:
    """Return the exact homogeneous pair penalty when the pair is legal."""
    if not _is_legal_pair(left, right):
        return None
    return _homogeneous_exact_pair_penalty_cached(left, right, initial_color, pair_count)


@cache
def _homogeneous_zero_exchange_min_penalty(
    s1: tuple[PlayerState, ...],
    s2: tuple[PlayerState, ...],
    *,
    initial_color: Color,
    pair_count: int,
) -> int | None:
    """Return the exact minimum [C10]-[C13] penalty inside one zero-exchange bucket."""
    if len(s1) != len(s2):
        return None
    if not s1:
        return 0

    right_offset = len(s1)
    weighted_edges = [
        (left_index, right_index, -penalty)
        for left_index, left in enumerate(s1)
        for right_index, right in enumerate(s2, start=right_offset)
        if (
            penalty := _homogeneous_legal_exact_pair_penalty(
                left,
                right,
                initial_color,
                pair_count,
            )
        )
        is not None
    ]

    matched_edges, total_weight = compute_maximum_weight_matching_total(
        node_count=len(s1) + len(s2),
        weighted_edges=tuple(weighted_edges),
        max_cardinality=True,
    )
    if matched_edges != len(s1):
        return None

    return -total_weight


@cache
def _homogeneous_global_min_penalty(
    players: tuple[PlayerState, ...],
    *,
    initial_color: Color,
) -> int | None:
    """Return a lower bound on homogeneous exact penalties over all perfect matchings."""
    if len(players) % 2 != 0:
        return None
    if not players:
        return 0

    pair_count = len(players) // 2
    weighted_edges = [
        (left_index, right_index, -penalty)
        for left_index, left in enumerate(players)
        for right_index in range(left_index + 1, len(players))
        if (
            penalty := _homogeneous_legal_exact_pair_penalty(
                left,
                players[right_index],
                initial_color,
                pair_count,
            )
        )
        is not None
    ]

    matched_edges, total_weight = compute_maximum_weight_matching_total(
        node_count=len(players),
        weighted_edges=tuple(weighted_edges),
        max_cardinality=True,
    )
    if matched_edges != pair_count:
        return None

    return -total_weight


@cache
def _build_zero_exchange_earliest_optimal_pairs(
    s1: tuple[PlayerState, ...],
    s2: tuple[PlayerState, ...],
    *,
    initial_color: Color,
    pair_count: int,
    target_penalty: int,
) -> tuple[tuple[PlayerState, PlayerState], ...] | None:
    """Reconstruct the earliest article-4.2 optimum inside one zero-exchange bucket."""
    if not s1:
        return ()

    left = s1[0]
    remaining_s1 = s1[1:]
    for index, right in enumerate(s2):
        pair_penalty = _homogeneous_legal_exact_pair_penalty(left, right, initial_color, pair_count)
        if pair_penalty is None:
            continue
        remaining_s2 = s2[:index] + s2[index + 1 :]
        remaining_penalty = _homogeneous_zero_exchange_min_penalty(
            remaining_s1,
            remaining_s2,
            initial_color=initial_color,
            pair_count=pair_count,
        )
        if remaining_penalty is None or pair_penalty + remaining_penalty != target_penalty:
            continue
        tail = _build_zero_exchange_earliest_optimal_pairs(
            remaining_s1,
            remaining_s2,
            initial_color=initial_color,
            pair_count=pair_count,
            target_penalty=remaining_penalty,
        )
        if tail is None:
            continue
        return ((left, right), *tail)
    return None


def _solve_homogeneous_even_players_via_zero_exchange_exact_shortcut(
    players: Sequence[PlayerState],
    *,
    initial_color: Color,
) -> _EvenPairingInternal | None:
    """Solve large homogeneous even brackets exactly when zero-exchange is provably optimal.

    Article 4.3 puts the zero-exchange bucket ahead of every exchanged bucket.
    If the best zero-exchange transposition already reaches the global minimum
    local [C10]-[C13] penalty across all legal perfect matchings, then that
    bucket is exact-optimal and we only need the earliest article-4.2 optimum
    inside it.
    """
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if not ordered_players or len(ordered_players) % 2 != 0:
        return None

    pair_count = len(ordered_players) // 2
    s1 = ordered_players[:pair_count]
    s2 = ordered_players[pair_count:]
    zero_exchange_penalty = _homogeneous_zero_exchange_min_penalty(
        s1,
        s2,
        initial_color=initial_color,
        pair_count=pair_count,
    )
    if zero_exchange_penalty is None:
        return None

    global_penalty = _homogeneous_global_min_penalty(
        ordered_players,
        initial_color=initial_color,
    )
    if global_penalty is None or zero_exchange_penalty != global_penalty:
        return None

    earliest_pairs = _build_zero_exchange_earliest_optimal_pairs(
        s1,
        s2,
        initial_color=initial_color,
        pair_count=pair_count,
        target_penalty=zero_exchange_penalty,
    )
    if earliest_pairs is None:
        return None
    return _EvenPairingInternal(
        pairings=tuple(sorted(earliest_pairs, key=_candidate_pair_sort_key)),
        unresolved=(),
    )


@cache
def _solve_homogeneous_even_players_via_zero_exchange_exact_shortcut_cached(
    players: tuple[PlayerState, ...],
    initial_color: Color,
) -> _EvenPairingInternal | None:
    return _solve_homogeneous_even_players_via_zero_exchange_exact_shortcut(
        players,
        initial_color=initial_color,
    )


def _solve_single_mdp_odd_exact(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int,
) -> _CandidateInternal | None:
    """Solve manageable odd one-MDP brackets in article order.

    This keeps the current bracket's exact sequence closer to the handbook than
    the generic unresolved-player-first scan by iterating the MDP resident
    partner in article-4.2 order and exact-solving the odd homogeneous
    remainder for each partner.
    """
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if len(ordered_players) % 2 == 0 or len(context.mdp_ids) != 1:
        return None
    if len(ordered_players) > _SINGLE_MDP_ODD_EXACT_MAX_PLAYERS:
        return None

    mdp = next((player for player in ordered_players if player.player_id in context.mdp_ids), None)
    if mdp is None:
        return None

    residents = tuple(player for player in ordered_players if player.player_id != mdp.player_id)
    bsn_by_player_id = {player.player_id: index + 1 for index, player in enumerate(ordered_players)}
    remainder_context = BracketContext(
        initial_color=context.initial_color,
        next_bracket_validator=context.next_bracket_validator,
        next_bracket_key=context.next_bracket_key,
    )
    best_candidate: _CandidateInternal | None = None
    best_key: tuple[object, ...] | None = None
    unsupported_found = False

    for sequence_no, s2_transposition in enumerate(
        _iter_s2_transpositions(
            s1=(mdp,),
            s2=residents,
            bsn_by_player_id=bsn_by_player_id,
        )
    ):
        resident = s2_transposition[0]
        if not _is_legal_pair(mdp, resident, context=context):
            continue
        remainder_players = tuple(sorted(s2_transposition[1:], key=_player_rank_key))
        try:
            remainder_candidate = _solve_without_bye_candidate(
                remainder_players,
                context=remainder_context,
                sequential_search_max_players=sequential_search_max_players,
            )
        except ExactSearchUnavailableError:
            unsupported_found = True
            continue
        except PairingError:
            continue

        candidate = _CandidateInternal(
            pairings=tuple(
                sorted(
                    (*remainder_candidate.pairings, (mdp, resident)),
                    key=_candidate_pair_sort_key,
                )
            ),
            unresolved=remainder_candidate.unresolved,
            bye_player=None,
            sequence_no=sequence_no,
        )
        candidate_key = _candidate_quality_key(candidate=candidate, context=context)
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best_candidate = candidate

    if best_candidate is None and unsupported_found:
        raise ExactSearchUnavailableError("exact Dutch mode does not yet support this odd bracket")
    return best_candidate


def _solve_even_players(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int = _SEQUENTIAL_SEARCH_MAX_PLAYERS,
) -> _EvenPairingInternal:
    """Compute one maximum-cardinality matching for an even-sized set."""
    if len(players) % 2 != 0:
        raise PairingError("internal even solver received odd player count")

    exact_candidate_max = _MAX_EXACT_SEQUENCE_CANDIDATES
    exact_search_attempted = False

    if not context.mdp_ids:
        exact_shortcut = _solve_homogeneous_even_players_via_zero_exchange_exact_shortcut_cached(
            tuple(sorted(players, key=_player_rank_key)),
            context.initial_color,
        )
        if exact_shortcut is not None:
            return exact_shortcut

    if len(context.mdp_ids) == 1:
        exact_search_attempted = True
        single_mdp_exact = _solve_even_players_via_single_mdp_exact(players, context=context)
        if single_mdp_exact is not None:
            return single_mdp_exact

    if context.mdp_ids and _use_heterogeneous_exact_search(
        len(players),
        mdp_count=len(context.mdp_ids),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    ):
        exact_search_attempted = True
        sequence_result = _solve_even_players_via_heterogeneous_sequence(players, context=context)
        if sequence_result is not None:
            return sequence_result

    if not context.mdp_ids and _use_homogeneous_exact_search(
        len(players),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    ):
        exact_search_attempted = True
        sequence_result = _solve_even_players_via_sequence(players, context=context)
        if sequence_result is not None:
            return sequence_result

    if exact_search_attempted:
        return _EvenPairingInternal(
            pairings=(),
            unresolved=tuple(sorted(players, key=_player_rank_key)),
        )
    raise ExactSearchUnavailableError("exact Dutch mode does not yet support this even bracket")


def _candidate_downfloaters(candidate: _CandidateInternal) -> tuple[PlayerState, ...]:
    downfloaters = list(candidate.unresolved)
    if candidate.bye_player is not None:
        downfloaters.append(candidate.bye_player)
    return tuple(sorted(downfloaters, key=_player_rank_key))


@cache
def _candidate_local_quality_key(
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
    context = BracketContext(mdp_ids=mdp_ids, initial_color=initial_color)
    downfloaters = _candidate_downfloaters(candidate)
    pair_components = tuple(
        _edge_penalty_components(left, right, context=context) for left, right in candidate.pairings
    )

    c5 = candidate.bye_player.score if candidate.bye_player is not None else 0
    c6 = -len(candidate.pairings)
    c7 = tuple(player.score for player in sorted(downfloaters, key=lambda player: -player.score))
    c9 = candidate.bye_player.unplayed_games if candidate.bye_player is not None else 0

    c10, c11, c12, c13 = _collect_pair_quality_counts(pair_components)

    resident_downfloaters = tuple(
        player for player in downfloaters if player.player_id not in context.mdp_ids
    )
    c14 = sum(
        int(player.had_float(rounds_ago=1, kind=FloatKind.DOWN)) for player in resident_downfloaters
    )
    c16 = sum(
        int(player.had_float(rounds_ago=2, kind=FloatKind.DOWN)) for player in resident_downfloaters
    )
    c15, c17, c18, c19, c20, c21 = _collect_mdp_quality(pair_components=pair_components)

    return (
        downfloaters,
        c5,
        c6,
        c7,
        c9,
        c10,
        c11,
        c12,
        c13,
        c14,
        c15,
        c16,
        c17,
        c18,
        c19,
        c20,
        c21,
        candidate.sequence_no,
    )


def _next_bracket_c1_to_c7_violation(
    *,
    downfloaters: tuple[PlayerState, ...],
    context: BracketContext,
) -> int:
    """Return [C8] penalty: 0 means validator accepts the downfloater set."""
    validator = context.next_bracket_validator
    if validator is None:
        return 0
    return 0 if _next_bracket_validator_result(validator, downfloaters) else 1


@cache
def _next_bracket_validator_result(
    validator: NextBracketValidator,
    downfloaters: tuple[PlayerState, ...],
) -> bool:
    return validator(downfloaters)


def _next_bracket_key(
    *,
    downfloaters: tuple[PlayerState, ...],
    context: BracketContext,
) -> NextBracketKey:
    key_fn = context.next_bracket_key
    if key_fn is None:
        return _EMPTY_NEXT_BRACKET_KEY
    key = _next_bracket_key_result(key_fn, downfloaters)
    if key is None:
        return _EMPTY_NEXT_BRACKET_KEY
    return key


@cache
def _next_bracket_key_result(
    key_fn: NextBracketKeyFn,
    downfloaters: tuple[PlayerState, ...],
) -> NextBracketKey | None:
    return key_fn(downfloaters)


def _collect_pair_quality_counts(
    pair_components: Sequence[tuple[int, int, int, int, int, int, int, int, int, int]],
) -> tuple[int, int, int, int]:
    c10 = 0
    c11 = 0
    c12 = 0
    c13 = 0
    for p10, p11, p12, p13, _, _, _, _, _, _ in pair_components:
        c10 += p10
        c11 += p11
        c12 += p12
        c13 += p13
    return c10, c11, c12, c13


def _collect_mdp_quality(
    *,
    pair_components: Sequence[tuple[int, int, int, int, int, int, int, int, int, int]],
) -> tuple[int, int, tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    c15 = 0
    c17 = 0
    c18_values: list[int] = []
    c19_values: list[int] = []
    c20_values: list[int] = []
    c21_values: list[int] = []

    for _, _, _, _, p15, p17, p18, p19, p20, p21 in pair_components:
        c15 += p15
        c17 += p17
        if p18:
            c18_values.append(p18)
        if p19:
            c19_values.append(p19)
        if p20:
            c20_values.append(p20)
        if p21:
            c21_values.append(p21)

    return (
        c15,
        c17,
        tuple(sorted(c18_values, reverse=True)),
        tuple(sorted(c19_values, reverse=True)),
        tuple(sorted(c20_values, reverse=True)),
        tuple(sorted(c21_values, reverse=True)),
    )


def _candidate_quality_key(
    *,
    candidate: _CandidateInternal,
    context: BracketContext,
) -> tuple[
    int,
    int,
    tuple[int, ...],
    int,
    NextBracketKey,
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
    """Return lexicographic key for [C5]-[C21] + generation order tie-break."""
    (
        downfloaters,
        c5,
        c6,
        c7,
        c9,
        c10,
        c11,
        c12,
        c13,
        c14,
        c15,
        c16,
        c17,
        c18,
        c19,
        c20,
        c21,
        sequence_no,
    ) = _candidate_local_quality_key(candidate, context.mdp_ids, context.initial_color)
    c8 = _next_bracket_c1_to_c7_violation(downfloaters=downfloaters, context=context)
    c8_key = (
        _EMPTY_NEXT_BRACKET_KEY
        if c8 or context.next_bracket_key is None
        else _next_bracket_key(downfloaters=downfloaters, context=context)
    )

    return (
        c5,
        c6,
        c7,
        c8,
        c8_key,
        c9,
        c10,
        c11,
        c12,
        c13,
        c14,
        c15,
        c16,
        c17,
        c18,
        c19,
        c20,
        c21,
        sequence_no,
    )


def pairing_result_next_bracket_local_key(
    *,
    players: tuple[PlayerState, ...],
    result: PairingResult,
    context: BracketContext,
) -> NextBracketLocalKey:
    """Project one concrete next-bracket result onto local [C5]-[C7] quality.

    FIDE [C8] is about preserving the next bracket's [C1]-[C7] outlook.
    Later local quality layers ([C9]-[C21]) belong to the current bracket's own
    comparison and should not override it merely through lookahead.
    """
    del context
    by_id = {player.player_id: player for player in players}
    bye_score = 0
    paired_games = 0
    for pairing in result.pairings:
        if pairing.black_id is None:
            bye_score = by_id[pairing.white_id].score
            continue
        paired_games += 1
    unresolved_ids = tuple(
        sorted(
            result.unpaired_ids,
            key=lambda player_id: _player_rank_key(by_id[player_id]),
        )
    )
    unresolved_scores = tuple(
        by_id[player_id].score
        for player_id in unresolved_ids
    )
    return NextBracketLocalKey(
        c5=bye_score,
        c6=-paired_games,
        c7=unresolved_scores,
    )


def _split_mdps_and_residents(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> tuple[tuple[PlayerState, ...], tuple[PlayerState, ...]]:
    """Split a bracket into MDPs and resident players."""
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    mdps = tuple(player for player in ordered_players if player.player_id in context.mdp_ids)
    residents = tuple(
        player for player in ordered_players if player.player_id not in context.mdp_ids
    )
    return mdps, residents


def _selected_mdp_set_is_pairable(
    *,
    selected_mdps: Sequence[PlayerState],
    residents: Sequence[PlayerState],
) -> bool:
    """Return whether each selected MDP can be matched to a distinct resident."""
    if not selected_mdps:
        return True

    options_by_mdp_id: dict[str, tuple[PlayerState, ...]] = {}
    for mdp in selected_mdps:
        options = tuple(resident for resident in residents if _is_legal_pair(mdp, resident))
        if not options:
            return False
        options_by_mdp_id[mdp.player_id] = options

    ordered_mdps = tuple(
        sorted(
            selected_mdps,
            key=lambda mdp: (len(options_by_mdp_id[mdp.player_id]), _player_rank_key(mdp)),
        )
    )
    matched_resident_ids: set[str] = set()

    def assign(index: int) -> bool:
        if index >= len(ordered_mdps):
            return True
        mdp = ordered_mdps[index]
        for resident in options_by_mdp_id[mdp.player_id]:
            if resident.player_id in matched_resident_ids:
                continue
            matched_resident_ids.add(resident.player_id)
            if assign(index + 1):
                return True
            matched_resident_ids.remove(resident.player_id)
        return False

    return assign(0)


def _iter_pairable_mdp_sets(
    *,
    mdps: Sequence[PlayerState],
    residents: Sequence[PlayerState],
    bsn_by_player_id: dict[str, int],
) -> tuple[tuple[PlayerState, ...], ...]:
    """Return MDP sets in article-4.4 style order.

    Implementation notes:
    - M1 is chosen as `min(M0, number_of_residents)` to maximize pair count.
    - [C7] is approximated by retaining sets with best Limbo score tuple.
    - Remaining ties are sorted by selected BSN tuple (article 4.4.2).
    """
    ordered_mdps = tuple(sorted(mdps, key=_player_rank_key))
    m1 = min(len(ordered_mdps), len(residents))
    if m1 <= 0:
        return ((),)

    specs: list[tuple[tuple[int, ...], tuple[int, ...], tuple[PlayerState, ...]]] = []
    for indices in combinations(range(len(ordered_mdps)), m1):
        selected = tuple(ordered_mdps[index] for index in indices)
        if not _selected_mdp_set_is_pairable(
            selected_mdps=selected,
            residents=residents,
        ):
            continue
        selected_ids = frozenset(player.player_id for player in selected)
        limbo = tuple(player for player in ordered_mdps if player.player_id not in selected_ids)
        limbo_scores_desc = tuple(
            player.score for player in sorted(limbo, key=lambda player: -player.score)
        )
        selected_bsns = tuple(sorted(bsn_by_player_id[player.player_id] for player in selected))
        specs.append((limbo_scores_desc, selected_bsns, selected))

    if not specs:
        return ()

    best_limbo_scores = min(spec[0] for spec in specs)
    filtered = [spec for spec in specs if spec[0] == best_limbo_scores]
    filtered.sort(key=lambda spec: spec[1])
    return tuple(spec[2] for spec in filtered)


@cache
def _solve_even_players_via_heterogeneous_sequence_cached(
    players: tuple[PlayerState, ...],
    mdp_ids: frozenset[str],
    initial_color: Color,
) -> _EvenPairingInternal | None:
    """Solve small heterogeneous brackets by article 3.7 candidate sequence."""
    best_candidate = _select_best_candidate(
        _iter_heterogeneous_candidates_cached(players, mdp_ids, initial_color),
        context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
    )
    if best_candidate is None:
        return None
    return _EvenPairingInternal(
        pairings=tuple(sorted(best_candidate.pairings, key=_candidate_pair_sort_key)),
        unresolved=tuple(sorted(best_candidate.unresolved, key=_player_rank_key)),
    )


def _solve_even_players_via_heterogeneous_sequence(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    return _solve_even_players_via_heterogeneous_sequence_cached(
        tuple(sorted(players, key=_player_rank_key)),
        context.mdp_ids,
        context.initial_color,
    )


@cache
def _iter_heterogeneous_candidates_cached(
    players: tuple[PlayerState, ...],
    mdp_ids: frozenset[str],
    initial_color: Color,
) -> tuple[_CandidateInternal, ...]:
    """Generate heterogeneous candidates in article 3.7 order.

    Sequence:
    - choose pairable MDP set (article 4.4)
    - iterate S2 transpositions for MDP-pairing (article 3.7.2 / 4.2)
    - for each, iterate all remainder candidates (article 3.7.1 / 3.6)
    """
    ordered_players = players
    context = BracketContext(mdp_ids=mdp_ids, initial_color=initial_color)
    mdps, residents = _split_mdps_and_residents(ordered_players, context=context)
    if not mdps or not residents:
        return ()

    bsn_by_player_id = {player.player_id: index + 1 for index, player in enumerate(ordered_players)}
    mdp_sets = _iter_pairable_mdp_sets(
        mdps=mdps,
        residents=residents,
        bsn_by_player_id=bsn_by_player_id,
    )
    generated: list[_CandidateInternal] = []
    sequence_no = 0

    for selected_mdps in mdp_sets:
        selected_ids = frozenset(player.player_id for player in selected_mdps)
        limbo = tuple(player for player in mdps if player.player_id not in selected_ids)
        s1 = tuple(sorted(selected_mdps, key=_player_rank_key))
        s2 = tuple(sorted(residents, key=_player_rank_key))

        for s2_permutation in _iter_s2_transpositions(
            s1=s1,
            s2=s2,
            bsn_by_player_id=bsn_by_player_id,
        ):
            mdp_pairs = tuple(zip(s1, s2_permutation[: len(s1)], strict=True))
            if any(not _is_legal_pair(left, right, context=context) for left, right in mdp_pairs):
                continue

            remainder_players = tuple(sorted(s2_permutation[len(s1) :], key=_player_rank_key))
            remainder_candidates = _iter_homogeneous_candidates(remainder_players)
            for remainder_candidate in remainder_candidates:
                unresolved = tuple(
                    sorted((*limbo, *remainder_candidate.unresolved), key=_player_rank_key)
                )
                generated.append(
                    _CandidateInternal(
                        pairings=(*mdp_pairs, *remainder_candidate.pairings),
                        unresolved=unresolved,
                        bye_player=None,
                        sequence_no=sequence_no,
                    )
                )
                sequence_no += 1

    return tuple(generated)


def _iter_heterogeneous_candidates(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> tuple[_CandidateInternal, ...]:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    return _iter_heterogeneous_candidates_cached(
        ordered_players,
        context.mdp_ids,
        context.initial_color,
    )


@cache
def _solve_even_players_via_single_mdp_exact_cached(
    players: tuple[PlayerState, ...],
    mdp_ids: frozenset[str],
    initial_color: Color,
) -> _EvenPairingInternal | None:
    """Solve large one-MDP even brackets exactly without full hetero expansion.

    With one MDP, article 3.7 reduces to scanning resident partners in
    article-4.2 order and solving the remaining homogeneous bracket exactly.
    """
    if len(players) % 2 != 0 or len(mdp_ids) != 1:
        return None

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    context = BracketContext(mdp_ids=mdp_ids, initial_color=initial_color)
    mdps, residents = _split_mdps_and_residents(ordered_players, context=context)
    if len(mdps) != 1 or not residents:
        return None

    mdp = mdps[0]
    remainder_context = BracketContext(initial_color=initial_color)
    bsn_by_player_id = {player.player_id: index + 1 for index, player in enumerate(ordered_players)}
    best_candidate: _CandidateInternal | None = None
    best_key: tuple[object, ...] | None = None

    for sequence_no, s2_transposition in enumerate(
        _iter_s2_transpositions(
            s1=(mdp,),
            s2=residents,
            bsn_by_player_id=bsn_by_player_id,
        )
    ):
        resident = s2_transposition[0]
        if not _is_legal_pair(mdp, resident, context=context):
            continue

        remainder_players = tuple(sorted(s2_transposition[1:], key=_player_rank_key))
        try:
            remainder_result = _solve_even_players(
                remainder_players,
                context=remainder_context,
                sequential_search_max_players=len(remainder_players),
            )
        except ExactSearchUnavailableError:
            continue

        candidate = _CandidateInternal(
            pairings=tuple(
                sorted(
                    (*remainder_result.pairings, (mdp, resident)),
                    key=_candidate_pair_sort_key,
                )
            ),
            unresolved=remainder_result.unresolved,
            bye_player=None,
            sequence_no=sequence_no,
        )
        candidate_key = _candidate_quality_key(candidate=candidate, context=context)
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best_candidate = candidate

    if best_candidate is None:
        return None

    return _EvenPairingInternal(
        pairings=best_candidate.pairings,
        unresolved=best_candidate.unresolved,
    )


def _solve_even_players_via_single_mdp_exact_uncached(
    players: tuple[PlayerState, ...],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    """Solve one-MDP even brackets exactly while honoring live next-bracket criteria."""
    if len(players) % 2 != 0 or len(context.mdp_ids) != 1:
        return None

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    mdps, residents = _split_mdps_and_residents(ordered_players, context=context)
    if len(mdps) != 1 or not residents:
        return None

    mdp = mdps[0]
    remainder_context = BracketContext(
        initial_color=context.initial_color,
        next_bracket_validator=context.next_bracket_validator,
        next_bracket_key=context.next_bracket_key,
    )
    bsn_by_player_id = {player.player_id: index + 1 for index, player in enumerate(ordered_players)}
    best_candidates_by_unresolved: dict[tuple[PlayerState, ...], _CandidateInternal] = {}
    best_local_keys_by_unresolved: dict[tuple[PlayerState, ...], tuple[object, ...]] = {}
    unsupported_found = False

    for sequence_no, s2_transposition in enumerate(
        _iter_s2_transpositions(
            s1=(mdp,),
            s2=residents,
            bsn_by_player_id=bsn_by_player_id,
        )
    ):
        resident = s2_transposition[0]
        if not _is_legal_pair(mdp, resident, context=context):
            continue

        remainder_players = tuple(sorted(s2_transposition[1:], key=_player_rank_key))
        try:
            remainder_result = _solve_even_players(
                remainder_players,
                context=remainder_context,
                sequential_search_max_players=len(remainder_players),
            )
        except ExactSearchUnavailableError:
            unsupported_found = True
            continue

        candidate = _CandidateInternal(
            pairings=tuple(
                sorted(
                    (*remainder_result.pairings, (mdp, resident)),
                    key=_candidate_pair_sort_key,
                )
            ),
            unresolved=remainder_result.unresolved,
            bye_player=None,
            sequence_no=sequence_no,
        )
        unresolved_key = candidate.unresolved
        local_key = _candidate_local_quality_key(
            candidate,
            context.mdp_ids,
            context.initial_color,
        )
        best_local_key = best_local_keys_by_unresolved.get(unresolved_key)
        if best_local_key is None or local_key < best_local_key:
            best_local_keys_by_unresolved[unresolved_key] = local_key
            best_candidates_by_unresolved[unresolved_key] = candidate

    best_candidate: _CandidateInternal | None = None
    best_key: tuple[object, ...] | None = None
    for candidate in best_candidates_by_unresolved.values():
        candidate_key = _candidate_quality_key(candidate=candidate, context=context)
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best_candidate = candidate

    if best_candidate is None:
        if unsupported_found:
            raise ExactSearchUnavailableError(
                "exact Dutch mode does not yet support this even bracket"
            )
        return None

    return _EvenPairingInternal(
        pairings=best_candidate.pairings,
        unresolved=best_candidate.unresolved,
    )


@cache
def _solve_even_players_via_single_mdp_exact_with_context_cached(
    players: tuple[PlayerState, ...],
    mdp_ids: frozenset[str],
    initial_color: Color,
    next_bracket_validator: NextBracketValidator | None,
    next_bracket_key: NextBracketKeyFn | None,
) -> _EvenPairingInternal | None:
    return _solve_even_players_via_single_mdp_exact_uncached(
        players,
        context=BracketContext(
            mdp_ids=mdp_ids,
            initial_color=initial_color,
            next_bracket_validator=next_bracket_validator,
            next_bracket_key=next_bracket_key,
        ),
    )


def _solve_even_players_via_single_mdp_exact(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if context.next_bracket_validator is None and context.next_bracket_key is None:
        return _solve_even_players_via_single_mdp_exact_cached(
            ordered_players,
            context.mdp_ids,
            context.initial_color,
        )
    return _solve_even_players_via_single_mdp_exact_with_context_cached(
        ordered_players,
        context.mdp_ids,
        context.initial_color,
        context.next_bracket_validator,
        context.next_bracket_key,
    )


def _find_single_mdp_even_feasible_unresolved(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int,
) -> tuple[PlayerState, ...] | None:
    """Return one feasible unresolved set for an exact one-MDP even bracket."""
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if len(ordered_players) % 2 != 0 or len(context.mdp_ids) != 1:
        return None

    mdps, residents = _split_mdps_and_residents(ordered_players, context=context)
    if len(mdps) != 1 or not residents:
        return None

    mdp = mdps[0]
    remainder_context = BracketContext(initial_color=context.initial_color)
    bsn_by_player_id = {player.player_id: index + 1 for index, player in enumerate(ordered_players)}
    unsupported_found = False

    for s2_transposition in _iter_s2_transpositions(
        s1=(mdp,),
        s2=residents,
        bsn_by_player_id=bsn_by_player_id,
    ):
        resident = s2_transposition[0]
        if not _is_legal_pair(mdp, resident, context=context):
            continue

        remainder_players = tuple(sorted(s2_transposition[1:], key=_player_rank_key))
        try:
            remainder_result = _solve_even_players(
                remainder_players,
                context=remainder_context,
                sequential_search_max_players=sequential_search_max_players,
            )
        except ExactSearchUnavailableError:
            unsupported_found = True
            continue
        except PairingError:
            continue

        unresolved = tuple(sorted(remainder_result.unresolved, key=_player_rank_key))
        validator = context.next_bracket_validator
        if validator is not None and not validator(unresolved):
            continue
        return unresolved

    if unsupported_found:
        raise ExactSearchUnavailableError("exact Dutch mode does not yet support this even bracket")
    return None


def _solve_without_bye_candidate_uncached(
    players: tuple[PlayerState, ...],
    *,
    context: BracketContext,
    sequential_search_max_players: int,
) -> _CandidateInternal:
    """Return best candidate for a bracket that cannot assign a pairing bye."""
    ordered_players = players
    if not ordered_players:
        return _CandidateInternal(pairings=(), unresolved=(), bye_player=None, sequence_no=0)

    exact_candidate_max = _MAX_EXACT_SEQUENCE_CANDIDATES

    if len(ordered_players) % 2 == 0:
        even_result = _solve_even_players(
            ordered_players,
            context=context,
            sequential_search_max_players=sequential_search_max_players,
        )
        return _CandidateInternal(
            pairings=even_result.pairings,
            unresolved=even_result.unresolved,
            bye_player=None,
            sequence_no=0,
        )

    use_exact_heterogeneous = bool(context.mdp_ids) and _use_heterogeneous_exact_search(
        len(ordered_players),
        mdp_count=len(context.mdp_ids),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    )
    if len(context.mdp_ids) == 1:
        use_exact_heterogeneous = False
    if use_exact_heterogeneous:
        best_candidate = _select_best_candidate(
            _iter_heterogeneous_candidates(ordered_players, context=context),
            context=context,
        )
        if best_candidate is not None:
            return best_candidate

    use_exact_homogeneous = (not context.mdp_ids) and _use_homogeneous_exact_search(
        len(ordered_players),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    )
    if use_exact_homogeneous:
        best_candidate = _select_best_candidate(
            _iter_homogeneous_candidates(ordered_players),
            context=context,
            dedupe_shapes=False,
        )
        if best_candidate is not None:
            return best_candidate

    if len(context.mdp_ids) == 1:
        single_mdp_odd_exact = _solve_single_mdp_odd_exact(
            ordered_players,
            context=context,
            sequential_search_max_players=sequential_search_max_players,
        )
        if single_mdp_odd_exact is not None:
            return single_mdp_odd_exact
    unsupported_found = False
    score_groups_desc: list[tuple[PlayerState, ...]] = []
    current_score_group: list[PlayerState] = []
    current_score: int | None = None
    for player in ordered_players:
        if current_score is None or player.score != current_score:
            if current_score_group:
                score_groups_desc.append(tuple(current_score_group))
            current_score_group = [player]
            current_score = player.score
            continue
        current_score_group.append(player)
    if current_score_group:
        score_groups_desc.append(tuple(current_score_group))
    downfloater_groups = tuple(reversed(score_groups_desc))

    for downfloater_group in downfloater_groups:
        group_candidates: list[_CandidateInternal] = []
        sequence_no = 0
        for downfloater in downfloater_group:
            rest = tuple(
                player for player in ordered_players if player.player_id != downfloater.player_id
            )
            adjusted_context = context
            if downfloater.player_id in context.mdp_ids:
                adjusted_context = BracketContext(
                    mdp_ids=context.mdp_ids - {downfloater.player_id},
                    initial_color=context.initial_color,
                    next_bracket_validator=context.next_bracket_validator,
                    next_bracket_key=context.next_bracket_key,
                )
            feasibility_validator: NextBracketValidator | None = None
            if adjusted_context.next_bracket_validator is not None:
                feasibility_validator = _extend_next_bracket_validator(
                    adjusted_context.next_bracket_validator,
                    fixed_downfloaters=(downfloater,),
                )

            if feasibility_validator is not None and len(adjusted_context.mdp_ids) == 1:
                try:
                    is_feasible = bracket_is_feasible_exact(
                        rest,
                        context=BracketContext(
                            mdp_ids=adjusted_context.mdp_ids,
                            initial_color=adjusted_context.initial_color,
                            next_bracket_validator=feasibility_validator,
                        ),
                        allow_bye=False,
                        sequential_search_max_players=sequential_search_max_players,
                        initial_color=adjusted_context.initial_color,
                    )
                except ExactSearchUnavailableError:
                    unsupported_found = True
                    continue
                if not is_feasible:
                    continue

            remainder_context = BracketContext(
                mdp_ids=adjusted_context.mdp_ids,
                initial_color=adjusted_context.initial_color,
            )

            remainder_candidates: tuple[_CandidateInternal, ...]
            preselect_fixed_downfloater_homogeneous = False
            if remainder_context.mdp_ids and _use_heterogeneous_exact_search(
                len(rest),
                mdp_count=len(remainder_context.mdp_ids),
                sequential_search_max_players=sequential_search_max_players,
                exact_candidate_max=exact_candidate_max,
            ):
                remainder_candidates = _iter_heterogeneous_candidates(
                    rest,
                    context=remainder_context,
                )
            elif len(remainder_context.mdp_ids) == 1:
                try:
                    even_result = _solve_even_players(
                        rest,
                        context=remainder_context,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                except ExactSearchUnavailableError:
                    unsupported_found = True
                    continue
                except PairingError:
                    continue
                remainder_candidates = (
                    _CandidateInternal(
                        pairings=even_result.pairings,
                        unresolved=even_result.unresolved,
                        bye_player=None,
                        sequence_no=0,
                    ),
                )
            elif _use_homogeneous_exact_search(
                len(rest),
                sequential_search_max_players=sequential_search_max_players,
                exact_candidate_max=exact_candidate_max,
            ):
                remainder_candidates = _iter_homogeneous_candidates(rest)
                preselect_fixed_downfloater_homogeneous = True
            else:
                try:
                    even_result = _solve_even_players(
                        rest,
                        context=remainder_context,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                except ExactSearchUnavailableError:
                    unsupported_found = True
                    continue
                remainder_candidates = (
                    _CandidateInternal(
                        pairings=even_result.pairings,
                        unresolved=even_result.unresolved,
                        bye_player=None,
                        sequence_no=0,
                    ),
                )

            if preselect_fixed_downfloater_homogeneous:
                downfloater_candidates: list[_CandidateInternal] = []
                for remainder in remainder_candidates:
                    candidate = _CandidateInternal(
                        pairings=remainder.pairings,
                        unresolved=(downfloater,),
                        bye_player=None,
                        sequence_no=sequence_no,
                    )
                    downfloater_candidates.append(candidate)
                    sequence_no += 1
                if downfloater_candidates:
                    best_downfloater_candidate = _select_best_homogeneous_odd_candidate(
                        ordered_players,
                        downfloater_candidates,
                        context=BracketContext(initial_color=adjusted_context.initial_color),
                    )
                    if best_downfloater_candidate is not None:
                        group_candidates.append(best_downfloater_candidate)
                continue

            for remainder in remainder_candidates:
                unresolved = tuple(
                    sorted(
                        (*remainder.unresolved, downfloater),
                        key=_player_rank_key,
                    )
                )
                candidate = _CandidateInternal(
                    pairings=remainder.pairings,
                    unresolved=unresolved,
                    bye_player=None,
                    sequence_no=sequence_no,
                )
                group_candidates.append(candidate)
                sequence_no += 1

        if group_candidates:
            if not context.mdp_ids:
                best_candidate = _select_best_homogeneous_odd_candidate(
                    ordered_players,
                    group_candidates,
                    context=context,
                )
            else:
                best_candidate = _select_best_candidate(group_candidates, context=context)
            if best_candidate is not None:
                return best_candidate

    if unsupported_found:
        raise ExactSearchUnavailableError("exact Dutch mode does not yet support this odd bracket")
    raise PairingError("internal failure selecting downfloater candidate")


@cache
def _solve_without_bye_candidate_cached(
    players: tuple[PlayerState, ...],
    mdp_ids: frozenset[str],
    sequential_search_max_players: int,
    initial_color: Color,
) -> _CandidateInternal:
    return _solve_without_bye_candidate_uncached(
        players,
        context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
        sequential_search_max_players=sequential_search_max_players,
    )


def _solve_without_bye_candidate(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int = _SEQUENTIAL_SEARCH_MAX_PLAYERS,
) -> _CandidateInternal:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if context.next_bracket_validator is None and context.next_bracket_key is None:
        return _solve_without_bye_candidate_cached(
            ordered_players,
            context.mdp_ids,
            sequential_search_max_players,
            context.initial_color,
        )
    return _solve_without_bye_candidate_uncached(
        ordered_players,
        context=context,
        sequential_search_max_players=sequential_search_max_players,
    )


def _sort_for_publication(
    pairings: Iterable[Pairing], by_id: dict[str, PlayerState]
) -> tuple[Pairing, ...]:
    """Sort pairings for publication, following C.04.2 section 3.6 recommendation."""

    def key(pairing: Pairing) -> tuple[int, int, int]:
        white = by_id[pairing.white_id]
        black = by_id[pairing.black_id] if pairing.black_id is not None else None

        high = white
        low = black
        if black is not None and _player_rank_key(black) < _player_rank_key(white):
            high = black
            low = white

        sum_score = high.score + (low.score if low is not None else 0)
        return (-high.score, -sum_score, high.pairing_no)

    return tuple(sorted(pairings, key=key))


def build_float_assignments(
    players: Sequence[PlayerState],
    *,
    pairings: tuple[Pairing, ...],
    unpaired_ids: tuple[str, ...],
) -> tuple[FloatAssignment, ...]:
    by_id = {player.player_id: player for player in players}
    assignments: dict[str, FloatKind] = {}

    def assign(player_id: str, kind: FloatKind) -> None:
        existing = assignments.get(player_id)
        if existing is not None and existing != kind:
            raise AssertionError(f"conflicting float assignment for {player_id}")
        assignments[player_id] = kind

    for pairing in pairings:
        if pairing.black_id is None:
            assign(pairing.white_id, FloatKind.DOWN)
            continue

        white = by_id[pairing.white_id]
        black = by_id[pairing.black_id]
        if white.score == black.score:
            continue

        higher, lower = (
            (white, black) if _player_rank_key(white) <= _player_rank_key(black) else (black, white)
        )
        assign(higher.player_id, FloatKind.DOWN)
        assign(lower.player_id, FloatKind.UP)

    for player_id in unpaired_ids:
        assign(player_id, FloatKind.DOWN)

    return tuple(
        FloatAssignment(player_id=player_id, kind=assignments[player_id])
        for player_id in sorted(
            assignments,
            key=lambda player_id: _player_rank_key(by_id[player_id]),
        )
    )


def _is_trivial_initial_homogeneous_bracket(
    players: tuple[PlayerState, ...],
    *,
    context: BracketContext,
) -> bool:
    """Return whether the bracket is an unconstrained round-1-style bracket."""
    if context.mdp_ids:
        return False
    if not players:
        return False
    score = players[0].score
    for player in players:
        if player.score != score:
            return False
        if player.opponents or player.forbidden_opponents or player.color_history:
            return False
        if player.unplayed_games != 0:
            return False
        if player.had_full_point_bye or player.had_full_point_unplayed_round:
            return False
        if any(float_kind is not FloatKind.NONE for float_kind in player.float_history):
            return False
    return True


def _pair_trivial_initial_homogeneous_bracket(
    players: tuple[PlayerState, ...],
    *,
    allow_bye: bool,
    initial_color: Color,
) -> PairingResult:
    """Pair the first legal S1/S2 candidate directly for an unconstrained bracket."""
    by_id = {player.player_id: player for player in players}
    pairable_players = players
    all_pairings: list[Pairing] = []
    unresolved_ids: tuple[str, ...] = ()

    if len(players) % 2 != 0:
        bye_player = players[-1]
        if allow_bye:
            if bye_player.is_pairing_allocated_bye_ineligible:
                raise PairingError("no legal bye candidate available under C2 constraints")
            all_pairings.append(Pairing(white_id=bye_player.player_id, black_id=None))
        else:
            unresolved_ids = (bye_player.player_id,)
        pairable_players = tuple(
            player for player in players if player.player_id != bye_player.player_id
        )

    split_size = len(pairable_players) // 2
    s1 = pairable_players[:split_size]
    s2 = pairable_players[split_size:]
    for left, right in zip(s1, s2, strict=True):
        white, black = _choose_color_order(left, right, initial_color=initial_color)
        all_pairings.append(Pairing(white_id=white.player_id, black_id=black.player_id))

    sorted_pairings = _sort_for_publication(tuple(all_pairings), by_id)
    return PairingResult(
        pairings=sorted_pairings,
        unpaired_ids=unresolved_ids,
        float_assignments=build_float_assignments(
            players,
            pairings=sorted_pairings,
            unpaired_ids=unresolved_ids,
        ),
    )


def _pair_bracket_impl(
    players: Sequence[PlayerState],
    *,
    context: BracketContext | None = None,
    allow_bye: bool = True,
    sequential_search_max_players: int = _SEQUENTIAL_SEARCH_MAX_PLAYERS,
    initial_color: Color = "white",
) -> PairingResult:
    """Internal exact bracket solver.

    The function remains deterministic for a fixed input state and context.
    `allow_bye=False` is used for non-final brackets where unresolved players
    must downfloat instead of receiving a pairing-allocated bye.
    """
    if len(players) == 0:
        return PairingResult(pairings=(), unpaired_ids=(), float_assignments=())

    local_context = _context_with_initial_color(context, initial_color=initial_color)
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if _is_trivial_initial_homogeneous_bracket(ordered_players, context=local_context):
        return _pair_trivial_initial_homogeneous_bracket(
            ordered_players,
            allow_bye=allow_bye,
            initial_color=initial_color,
        )

    by_id = {player.player_id: player for player in ordered_players}

    if not allow_bye:
        candidate = _solve_without_bye_candidate(
            ordered_players,
            context=local_context,
            sequential_search_max_players=sequential_search_max_players,
        )
        pairings: list[Pairing] = []
        for left, right in candidate.pairings:
            white, black = _choose_color_order(left, right, initial_color=initial_color)
            pairings.append(Pairing(white_id=white.player_id, black_id=black.player_id))
        unresolved_ids = tuple(player.player_id for player in candidate.unresolved)
        sorted_pairings = _sort_for_publication(pairings, by_id)
        return PairingResult(
            pairings=sorted_pairings,
            unpaired_ids=unresolved_ids,
            float_assignments=build_float_assignments(
                ordered_players,
                pairings=sorted_pairings,
                unpaired_ids=unresolved_ids,
            ),
        )

    # Even case: one cardinality-optimal candidate.
    if len(ordered_players) % 2 == 0:
        even_result = _solve_even_players(
            ordered_players,
            context=local_context,
            sequential_search_max_players=sequential_search_max_players,
        )
        pairings: list[Pairing] = []
        for left, right in even_result.pairings:
            white, black = _choose_color_order(left, right, initial_color=initial_color)
            pairings.append(Pairing(white_id=white.player_id, black_id=black.player_id))
        sorted_pairings = _sort_for_publication(pairings, by_id)
        unresolved_ids = tuple(player.player_id for player in even_result.unresolved)
        return PairingResult(
            pairings=sorted_pairings,
            unpaired_ids=unresolved_ids,
            float_assignments=build_float_assignments(
                ordered_players,
                pairings=sorted_pairings,
                unpaired_ids=unresolved_ids,
            ),
        )

    # Odd case with pairing-allocated bye:
    # C2: players with a previous PAB or other full-point unplayed round are excluded.
    bye_candidates = tuple(
        sorted(
            (
                player
                for player in ordered_players
                if not player.is_pairing_allocated_bye_ineligible
            ),
            key=_player_rank_key,
        )
    )
    if not bye_candidates:
        raise PairingError("no legal bye candidate available under C2 constraints")

    exact_bye_candidates = _iter_exact_final_bye_candidates(
        ordered_players,
        context=local_context,
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=_MAX_EXACT_SEQUENCE_CANDIDATES,
    )
    legal_exact_bye_candidates = tuple(
        candidate
        for candidate in exact_bye_candidates
        if candidate.bye_player is not None
        and not candidate.bye_player.is_pairing_allocated_bye_ineligible
    )
    if exact_bye_candidates:
        best_candidate = _select_best_candidate(legal_exact_bye_candidates, context=local_context)
        if best_candidate is None:
            raise PairingError("no legal bye candidate available under C2 constraints")
    else:
        best_candidate = None
        best_key: tuple[object, ...] | None = None
        unsupported_found = False

        # Exact odd-bracket generation already yields article sequence
        # order. Keep the fallback scan aligned with that direction so
        # equal-quality bye candidates still resolve to the same
        # last-sequence resident.
        for sequence_no, bye_candidate in enumerate(reversed(bye_candidates)):
            rest = tuple(
                player for player in ordered_players if player.player_id != bye_candidate.player_id
            )
            try:
                even_result = _solve_even_players(
                    rest,
                    context=local_context,
                    sequential_search_max_players=sequential_search_max_players,
                )
            except ExactSearchUnavailableError:
                unsupported_found = True
                continue
            candidate = _CandidateInternal(
                pairings=even_result.pairings,
                unresolved=even_result.unresolved,
                bye_player=bye_candidate,
                sequence_no=sequence_no,
            )
            candidate_key = _candidate_quality_key(candidate=candidate, context=local_context)
            if best_key is None or candidate_key < best_key:
                best_key = candidate_key
                best_candidate = candidate
        if best_candidate is None and unsupported_found:
            raise ExactSearchUnavailableError(
                "exact Dutch mode does not yet support this final bracket"
            )

    if best_candidate is None:
        raise PairingError("internal failure selecting bye candidate")

    normal_pairings: list[Pairing] = []
    for left, right in best_candidate.pairings:
        white, black = _choose_color_order(left, right, initial_color=initial_color)
        normal_pairings.append(Pairing(white_id=white.player_id, black_id=black.player_id))

    bye_player = best_candidate.bye_player
    if bye_player is None:
        raise PairingError("internal failure building odd bracket result")
    all_pairings = [*normal_pairings, Pairing(white_id=bye_player.player_id, black_id=None)]

    unresolved_ids = tuple(player.player_id for player in best_candidate.unresolved)
    sorted_pairings = _sort_for_publication(all_pairings, by_id)
    return PairingResult(
        pairings=sorted_pairings,
        unpaired_ids=unresolved_ids,
        float_assignments=build_float_assignments(
            ordered_players,
            pairings=sorted_pairings,
            unpaired_ids=unresolved_ids,
        ),
    )


def bracket_is_feasible_exact(
    players: Sequence[PlayerState],
    *,
    context: BracketContext | None = None,
    allow_bye: bool = True,
    sequential_search_max_players: int | None = None,
    initial_color: Color = "white",
) -> bool:
    """Return whether one exact bracket solution exists under the given context."""
    if len(players) == 0:
        return True

    local_context = _context_with_initial_color(context, initial_color=initial_color)
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    effective_search_limit = (
        len(ordered_players)
        if sequential_search_max_players is None
        else sequential_search_max_players
    )

    if not allow_bye:
        unsupported_found = False
        score_groups_desc: list[tuple[PlayerState, ...]] = []
        current_score_group: list[PlayerState] = []
        current_score: int | None = None
        for player in ordered_players:
            if current_score is None or player.score != current_score:
                if current_score_group:
                    score_groups_desc.append(tuple(current_score_group))
                current_score_group = [player]
                current_score = player.score
                continue
            current_score_group.append(player)
        if current_score_group:
            score_groups_desc.append(tuple(current_score_group))

        for downfloater_group in reversed(score_groups_desc):
            for downfloater in downfloater_group:
                rest = tuple(
                    player
                    for player in ordered_players
                    if player.player_id != downfloater.player_id
                )
                adjusted_context = local_context
                if downfloater.player_id in local_context.mdp_ids:
                    adjusted_context = BracketContext(
                        mdp_ids=local_context.mdp_ids - {downfloater.player_id},
                        initial_color=local_context.initial_color,
                        next_bracket_validator=local_context.next_bracket_validator,
                        next_bracket_key=local_context.next_bracket_key,
                    )
                feasibility_context = adjusted_context
                validator = local_context.next_bracket_validator
                if validator is not None:
                    feasibility_context = BracketContext(
                        mdp_ids=adjusted_context.mdp_ids,
                        initial_color=adjusted_context.initial_color,
                        next_bracket_validator=_extend_next_bracket_validator(
                            validator,
                            fixed_downfloaters=(downfloater,),
                        ),
                    )

                if len(feasibility_context.mdp_ids) == 1:
                    try:
                        unresolved = _find_single_mdp_even_feasible_unresolved(
                            rest,
                            context=feasibility_context,
                            sequential_search_max_players=effective_search_limit,
                        )
                    except ExactSearchUnavailableError:
                        unsupported_found = True
                        continue
                    if unresolved is not None:
                        return True
                    continue
                try:
                    even_result = _solve_even_players(
                        rest,
                        context=feasibility_context,
                        sequential_search_max_players=effective_search_limit,
                    )
                except ExactSearchUnavailableError:
                    unsupported_found = True
                    continue
                except PairingError:
                    continue
                if (
                    feasibility_context.next_bracket_validator is not None
                    and not feasibility_context.next_bracket_validator(
                        tuple(sorted(even_result.unresolved, key=_player_rank_key))
                    )
                ):
                    continue
                return True

        if unsupported_found:
            raise ExactSearchUnavailableError(
                "exact Dutch mode does not yet support this odd bracket"
            )
        return False

    if len(ordered_players) % 2 == 0:
        even_result = _solve_even_players(
            ordered_players,
            context=local_context,
            sequential_search_max_players=effective_search_limit,
        )
        return not even_result.unresolved

    bye_candidates = tuple(
        sorted(
            (
                player
                for player in ordered_players
                if not player.is_pairing_allocated_bye_ineligible
            ),
            key=_player_rank_key,
        )
    )
    if not bye_candidates:
        return False

    unsupported_found = False
    for bye_candidate in reversed(bye_candidates):
        rest = tuple(
            player for player in ordered_players if player.player_id != bye_candidate.player_id
        )
        try:
            even_result = _solve_even_players(
                rest,
                context=local_context,
                sequential_search_max_players=effective_search_limit,
            )
        except ExactSearchUnavailableError:
            unsupported_found = True
            continue
        except PairingError:
            continue
        if not even_result.unresolved:
            return True

    if unsupported_found:
        raise ExactSearchUnavailableError(
            "exact Dutch mode does not yet support this final bracket"
        )
    return False


def pair_bracket(
    players: Sequence[PlayerState],
    *,
    context: BracketContext | None = None,
    allow_bye: bool = True,
    sequential_search_max_players: int | None = None,
    initial_color: Color = "white",
) -> PairingResult:
    """Pair one bracket with the canonical exact Dutch solver.

    This uses only the current exact-search surface and raises `PairingError`
    when the solver does not yet support the bracket exactly.
    """
    exact_search_max_players = (
        len(players) if sequential_search_max_players is None else sequential_search_max_players
    )
    try:
        return _pair_bracket_impl(
            players,
            context=context,
            allow_bye=allow_bye,
            sequential_search_max_players=exact_search_max_players,
            initial_color=initial_color,
        )
    except ExactSearchUnavailableError as exc:
        raise PairingError(str(exc)) from exc
