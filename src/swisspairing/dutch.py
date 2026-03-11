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

from swisspairing._matching import compute_maximum_weight_matching
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


type NextBracketKeyFn = Callable[[tuple[PlayerState, ...]], NextBracketKey | None]


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


def _pair_color_quality(
    *,
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


def _color_allocation_key(
    *,
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


def _choose_color_order(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    initial_color: Color = "white",
) -> tuple[PlayerState, PlayerState]:
    """Pick white/black order following C.04.3 article 5.2 tie-breaks."""
    first_key = (
        *_color_allocation_key(white=player_a, black=player_b, initial_color=initial_color),
        _player_rank_key(player_a),
        _player_rank_key(player_b),
    )
    second_key = (
        *_color_allocation_key(white=player_b, black=player_a, initial_color=initial_color),
        _player_rank_key(player_b),
        _player_rank_key(player_a),
    )
    if first_key <= second_key:
        return player_a, player_b
    return player_b, player_a


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
    """Return local penalty components mapped to [C10]-[C13], [C15], [C17]-[C21]."""
    white, black = _choose_color_order(
        player_a,
        player_b,
        initial_color=context.initial_color,
    )
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
_MAX_EXACT_SEQUENCE_CANDIDATES = 5_000
_MAX_EXACT_SEQUENCE_CANDIDATES_EXACT_MODE = 50_000
_ODD_DOWNFLOATER_SCAN_MAX_PLAYERS = 20
_ODD_REFINEMENT_EXACT_SEARCH_MAX_PLAYERS = 10
_ODD_HETEROGENEOUS_REFINEMENT_MAX_PLAYERS = 11
_ODD_HETEROGENEOUS_REFINEMENT_EXACT_UPPER_BOUND = 80_000
_ODD_HETEROGENEOUS_REFINEMENT_MAX_CANDIDATES = 20_000
_ODD_HETEROGENEOUS_REFINEMENT_MAX_CANDIDATES_WITH_NEXT_BRACKET = 1_000
_ODD_FINAL_BYE_SCAN_MAX_PLAYERS = 20
_ODD_HOMOGENEOUS_REFINEMENT_SCAN_MAX_PLAYERS = 34
_ODD_HOMOGENEOUS_REFINEMENT_SKIP_MAX_PLAYERS_WITH_NEXT_BRACKET = 23
_ODD_HOMOGENEOUS_C8_TAIL_SCAN_CANDIDATES = 2
_SINGLE_MDP_ODD_REFINEMENT_MAX_PLAYERS = 24
_SINGLE_MDP_REMAINDER_HOMOGENEOUS_REFINEMENT_MAX_PLAYERS = 54
_SINGLE_MDP_ODD_REFINEMENT_SEARCH_MAX_PLAYERS = 6


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
    within a tractable budget; larger homogeneous brackets fall back to the
    weighted/D.1-D.2 approximation path even in strict mode.
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


def _exact_sequence_candidate_limit(*, allow_heuristic_fallback: bool) -> int:
    if allow_heuristic_fallback:
        return _MAX_EXACT_SEQUENCE_CANDIDATES
    return _MAX_EXACT_SEQUENCE_CANDIDATES_EXACT_MODE


def _edge_weight(player_a: PlayerState, player_b: PlayerState, *, context: BracketContext) -> int:
    """Approximate pair weight used by the generic heterogeneous fallback."""
    components = _edge_penalty_components(player_a, player_b, context=context)
    penalty = (
        (components[0] * 10**12)
        + (components[1] * 10**10)
        + (components[2] * 10**8)
        + (components[3] * 10**6)
        + (components[4] * 10**5)
        + (components[5] * 10**4)
        + (components[6] * 10**3)
        + (components[7] * 10**2)
        + (components[8] * 10**1)
        + components[9]
    )
    return -penalty


def _pack_penalty_components(
    *,
    components: Sequence[int],
    max_totals: Sequence[int],
) -> int:
    packed = 0
    for component, max_total in zip(components, max_totals, strict=True):
        packed = (packed * (max_total + 1)) + component
    return packed


def _heterogeneous_pair_penalty(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    context: BracketContext,
    split_size: int,
    max_score_difference: int,
) -> int:
    """Pack pair-local heterogeneous penalties exactly for weighted matching.

    The weighted heterogeneous matcher sums edge penalties across several
    pairs. Decimal weights are not safe there because lower-priority score
    difference totals can spill into higher-priority digits. A mixed-radix
    packing with bracket-level maxima preserves the intended lexicographic
    [C10]-[C21] ordering for the full matching.
    """

    components = _edge_penalty_components(player_a, player_b, context=context)
    player_count_max = 2 * split_size
    float_count_max = split_size
    score_difference_max = split_size * max_score_difference
    max_totals = (
        player_count_max,  # C10
        player_count_max,  # C11
        player_count_max,  # C12
        player_count_max,  # C13
        float_count_max,  # C15
        float_count_max,  # C17
        score_difference_max,  # C18
        score_difference_max,  # C19
        score_difference_max,  # C20
        score_difference_max,  # C21
    )
    return _pack_penalty_components(
        components=components,
        max_totals=max_totals,
    )


def _homogeneous_pair_penalty(
    player_a: PlayerState,
    player_b: PlayerState,
    *,
    split_size: int,
    initial_color: Color,
) -> int:
    """Pack [C10]-[C13] exactly for one homogeneous split edge.

    For homogeneous even brackets the exact article-3.6 / 4.2 / 4.3 candidate
    objective is additive over pair-local [C10]-[C13] counts. A mixed-radix
    packing with radix `2 * split_size + 1` preserves that lexicographic order
    for the total matching while staying within ordinary machine-sized ints.
    """
    white, black = _choose_color_order(
        player_a,
        player_b,
        initial_color=initial_color,
    )
    c10, c11, c12, c13 = _pair_color_quality(white=white, black=black)
    radix = (2 * split_size) + 1
    return (((c10 * radix) + c11) * radix + c12) * radix + c13


def _normalized_edge_key(left_id: str, right_id: str) -> tuple[str, str]:
    if left_id <= right_id:
        return left_id, right_id
    return right_id, left_id


@dataclass(slots=True)
class _HomogeneousMatchingState:
    """Mutable matching state for the large homogeneous Dutch fallback."""

    players: tuple[PlayerState, ...]
    split_size: int
    edge_penalties: dict[tuple[str, str], int]
    tie_scale: int
    final_bonus: int
    edge_bonuses: dict[tuple[str, str], int] = field(init=False)
    removed_edges: set[tuple[str, str]] = field(init=False)
    matching_by_id: dict[str, str] = field(init=False)
    by_id: dict[str, PlayerState] = field(init=False)

    def __post_init__(self) -> None:
        self.edge_bonuses = {}
        self.removed_edges = set()
        self.matching_by_id = {}
        self.by_id = {player.player_id: player for player in self.players}
        self.update_matching()

    def update_matching(self) -> None:
        edge_weights = {
            edge: -(penalty * self.tie_scale) + self.edge_bonuses.get(edge, 0)
            for edge, penalty in self.edge_penalties.items()
            if edge not in self.removed_edges
        }
        matching = compute_maximum_weight_matching(
            node_ids=(player.player_id for player in self.players),
            edge_weights=edge_weights,
            max_cardinality=True,
        )
        matching_by_id: dict[str, str] = {}
        for left_id, right_id in matching:
            matching_by_id[left_id] = right_id
            matching_by_id[right_id] = left_id
        self.matching_by_id = matching_by_id

    def partner(self, player: PlayerState) -> PlayerState | None:
        partner_id = self.matching_by_id.get(player.player_id)
        if partner_id is None:
            return None
        return self.by_id[partner_id]

    def has_match(self, player: PlayerState) -> bool:
        return player.player_id in self.matching_by_id

    def in_current_s1(self, player: PlayerState) -> bool:
        partner = self.partner(player)
        if partner is None:
            return False
        return _player_rank_key(player) < _player_rank_key(partner)

    def in_current_s2(self, player: PlayerState) -> bool:
        return not self.in_current_s1(player)

    def add_to_weights(
        self,
        player: PlayerState,
        others: Sequence[PlayerState],
        value: int,
        *,
        increment: bool = False,
    ) -> None:
        for other in others:
            edge = _normalized_edge_key(player.player_id, other.player_id)
            if edge in self.edge_penalties and edge not in self.removed_edges:
                self.edge_bonuses[edge] = self.edge_bonuses.get(edge, 0) + value
            value += int(increment)

    def remove_weights(self, player: PlayerState, others: Sequence[PlayerState]) -> None:
        for other in others:
            edge = _normalized_edge_key(player.player_id, other.player_id)
            if edge in self.edge_penalties:
                self.removed_edges.add(edge)

    def finalize_match(self, player_a: PlayerState, player_b: PlayerState) -> None:
        pair_edge = _normalized_edge_key(player_a.player_id, player_b.player_id)
        for other in self.players:
            if other.player_id not in {player_a.player_id, player_b.player_id}:
                self.remove_weights(player_a, (other,))
                self.remove_weights(player_b, (other,))
        self.edge_bonuses[pair_edge] = self.final_bonus

    def to_candidate(self) -> _CandidateInternal:
        return _matching_to_candidate(
            set(
                _normalized_edge_key(left_id, right_id)
                for left_id, right_id in self.matching_by_id.items()
                if left_id < right_id
            ),
            players=self.players,
            sequence_no=0,
        )


def _build_homogeneous_matching_state(
    players: Sequence[PlayerState],
    *,
    initial_color: Color,
) -> _HomogeneousMatchingState | None:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    split_size = len(ordered_players) // 2
    edge_penalties: dict[tuple[str, str], int] = {}
    for left, right in combinations(ordered_players, 2):
        if not _is_legal_pair(left, right):
            continue
        edge_penalties[_normalized_edge_key(left.player_id, right.player_id)] = (
            _homogeneous_pair_penalty(
                left,
                right,
                split_size=split_size,
                initial_color=initial_color,
            )
        )
    return _build_weighted_matching_state(
        ordered_players,
        edge_penalties=edge_penalties,
        split_size=split_size,
    )


def _build_heterogeneous_matching_state(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _HomogeneousMatchingState | None:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    split_size = len(ordered_players) // 2
    max_score_difference = max((player.score for player in ordered_players), default=0) - min(
        (player.score for player in ordered_players), default=0
    )
    edge_penalties: dict[tuple[str, str], int] = {}
    for left, right in combinations(ordered_players, 2):
        if not _is_legal_pair(left, right, context=context):
            continue
        edge_penalties[_normalized_edge_key(left.player_id, right.player_id)] = (
            _heterogeneous_pair_penalty(
                left,
                right,
                context=context,
                split_size=split_size,
                max_score_difference=max_score_difference,
            )
        )
    return _build_weighted_matching_state(
        ordered_players,
        edge_penalties=edge_penalties,
        split_size=split_size,
    )


def _build_weighted_matching_state(
    players: tuple[PlayerState, ...],
    *,
    edge_penalties: dict[tuple[str, str], int],
    split_size: int,
) -> _HomogeneousMatchingState | None:
    if not edge_penalties and players:
        return None

    player_count = len(players)
    bracket_bits = max(1, player_count.bit_length())
    max_d2_edge_bonus = ((1 << (2 * bracket_bits)) + player_count) << 1
    max_d1_edge_bonus = player_count
    max_edge_bonus = (player_count * max_d2_edge_bonus * 2) + (player_count * max_d1_edge_bonus)
    tie_scale = (player_count * max_edge_bonus) + 1

    max_penalty = max(edge_penalties.values(), default=0)
    max_matching_weight = (split_size * max_penalty * tie_scale) + (split_size * max_edge_bonus)
    final_bonus = max_matching_weight + 1

    return _HomogeneousMatchingState(
        players=players,
        split_size=split_size,
        edge_penalties=edge_penalties,
        tie_scale=tie_scale,
        final_bonus=final_bonus,
    )


def _apply_homogeneous_remainder_steps(
    state: _HomogeneousMatchingState,
    residents: Sequence[PlayerState],
) -> None:
    if not residents:
        return

    resident_list = list(residents)
    pairs = sum(int(state.has_match(player)) for player in resident_list) // 2
    homogeneous_s1 = resident_list[:pairs]
    homogeneous_s2 = resident_list[pairs:]
    bracket_bits = max(1, len(resident_list).bit_length())

    for index, resident in enumerate(resident_list):
        value = ((int(index < pairs) << (2 * bracket_bits)) - index) << 1
        state.add_to_weights(resident, resident_list[index + 1 :], value)
    state.update_matching()
    exchanges = sum(int(state.in_current_s2(player)) for player in homogeneous_s1)

    remaining_exchanges = exchanges
    for index in range(len(homogeneous_s1) - 1, -1, -1):
        if remaining_exchanges == 0:
            break
        resident = homogeneous_s1[index]
        lower_residents = [*homogeneous_s1[index + 1 :], *homogeneous_s2]
        was_in_s2 = state.in_current_s2(resident)
        if not was_in_s2:
            state.add_to_weights(resident, lower_residents, -1)
            state.update_matching()
        if state.in_current_s2(resident):
            remaining_exchanges -= 1
            state.remove_weights(resident, lower_residents)
        if not was_in_s2:
            state.add_to_weights(resident, lower_residents, 1)

    remaining_exchanges = exchanges
    for index, resident in enumerate(homogeneous_s2):
        if remaining_exchanges == 0:
            break
        higher_residents = [*homogeneous_s1, *homogeneous_s2[:index]]
        was_in_s1 = state.in_current_s1(resident)
        if not was_in_s1:
            state.add_to_weights(resident, higher_residents, -1)
            state.update_matching()
        if state.in_current_s1(resident):
            remaining_exchanges -= 1
            state.remove_weights(resident, higher_residents)
        if not was_in_s1:
            state.add_to_weights(resident, higher_residents, 1)

    homogeneous_bracket = [*homogeneous_s1, *homogeneous_s2]
    homogeneous_s1 = [resident for resident in homogeneous_bracket if state.in_current_s1(resident)]
    homogeneous_s2 = [resident for resident in homogeneous_bracket if state.in_current_s2(resident)]

    for index, resident in enumerate(homogeneous_s1):
        state.remove_weights(resident, homogeneous_s1[index + 1 :])
    for index, resident in enumerate(homogeneous_s2):
        state.remove_weights(resident, homogeneous_s2[index + 1 :])

    for resident in homogeneous_s1:
        state.add_to_weights(resident, homogeneous_s2[::-1], 0, increment=True)
        state.update_matching()
        match = state.partner(resident)
        if match is None:
            continue
        state.finalize_match(resident, match)


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


def _iter_resident_exchanges(
    players: Sequence[PlayerState],
    *,
    max_exchange_size: int | None = None,
) -> Sequence[tuple[tuple[PlayerState, ...], tuple[PlayerState, ...]]]:
    """Yield `(S1, S2)` compositions in article-4.3 exchange order."""
    ordered_players = tuple(sorted(players, key=_player_rank_key))
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

    return generated


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
    transpositions: list[tuple[tuple[int, ...], tuple[int, ...], tuple[PlayerState, ...]]] = []

    for prefix in permutations(s2_ordered, n1):
        prefix_ids = frozenset(player.player_id for player in prefix)
        tail = tuple(player for player in s2_ordered if player.player_id not in prefix_ids)
        candidate = tuple((*prefix, *tail))
        prefix_key = tuple(bsn_by_player_id[player.player_id] for player in prefix)
        full_key = tuple(bsn_by_player_id[player.player_id] for player in candidate)
        transpositions.append((prefix_key, full_key, candidate))

    transpositions.sort(key=lambda entry: (entry[0], entry[1]))
    return [entry[2] for entry in transpositions]


def _candidate_pair_sort_key(
    pair: tuple[PlayerState, PlayerState],
) -> tuple[tuple[int, int], tuple[int, int]]:
    return _player_rank_key(pair[0]), _player_rank_key(pair[1])


def _homogeneous_article_order_key(
    *,
    players: Sequence[PlayerState],
    candidate: _CandidateInternal,
) -> tuple[int, int, tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Approximate article-4.x candidate order for large homogeneous brackets.

    This mirrors the same D.2 then D.1 priorities used by the fallback matcher:
    fewer exchanges first, then better exchange composition, then earlier S2
    transposition order. It is used only as a tie-break after all quality
    criteria except generation order are equal.
    """
    ordered_players = tuple(sorted(players, key=_player_rank_key))
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

    When [C5]-[C21] still tie exactly, BBP's weighted Dutch implementation
    tends to prefer the candidate whose resident remainder keeps score
    differences tighter before falling back to raw generation order. Using this
    structural key only inside already-equal heterogeneous cohorts closes the
    checked 2026 reference gap without perturbing the main criterion ordering.
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
) -> _CandidateInternal | None:
    best_candidate: _CandidateInternal | None = None
    best_key: tuple[object, ...] | None = None

    for candidate in candidates:
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
    generated: list[_CandidateInternal] = []
    sequence_no = sequence_start

    for s1, s2 in _iter_resident_exchanges(ordered_players):
        for s2_transposition in _iter_s2_transpositions(
            s1=s1,
            s2=s2,
            bsn_by_player_id=bsn_by_player_id,
        ):
            raw_pairs = tuple(zip(s1, s2_transposition[: len(s1)], strict=True))
            if any(not _is_legal_pair(left, right) for left, right in raw_pairs):
                continue

            unresolved = tuple(sorted(s2_transposition[len(s1) :], key=_player_rank_key))
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
    )
    if best_candidate is None:
        return None
    return _EvenPairingInternal(
        pairings=tuple(sorted(best_candidate.pairings, key=_candidate_pair_sort_key)),
        unresolved=best_candidate.unresolved,
    )


def _solve_even_players_via_sequence(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    return _solve_even_players_via_sequence_cached(
        tuple(sorted(players, key=_player_rank_key)),
        context.initial_color,
    )


def _homogeneous_exact_pair_penalty(
    left: PlayerState,
    right: PlayerState,
    *,
    initial_color: Color,
    pair_count: int,
) -> int:
    """Pack local [C10]-[C13] penalties for exact homogeneous matching shortcuts."""
    white, black = _choose_color_order(left, right, initial_color=initial_color)
    c10, c11, c12, c13 = _pair_color_quality(white=white, black=black)
    radix = (2 * pair_count) + 1
    return (((c10 * radix) + c11) * radix + c12) * radix + c13


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

    edge_weights: dict[tuple[str, str], int] = {}
    by_id = {player.player_id: player for player in (*s1, *s2)}
    for left in s1:
        for right in s2:
            if not _is_legal_pair(left, right):
                continue
            penalty = _homogeneous_exact_pair_penalty(
                left,
                right,
                initial_color=initial_color,
                pair_count=pair_count,
            )
            edge_weights[(left.player_id, right.player_id)] = -penalty

    matching = compute_maximum_weight_matching(
        node_ids=(player.player_id for player in (*s1, *s2)),
        edge_weights=edge_weights,
        max_cardinality=True,
    )
    if len(matching) != len(s1):
        return None

    total_penalty = 0
    s1_ids = {player.player_id for player in s1}
    for first_id, second_id in matching:
        left_id, right_id = (first_id, second_id) if first_id in s1_ids else (second_id, first_id)
        total_penalty += _homogeneous_exact_pair_penalty(
            by_id[left_id],
            by_id[right_id],
            initial_color=initial_color,
            pair_count=pair_count,
        )
    return total_penalty


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
    edge_weights: dict[tuple[str, str], int] = {}
    by_id = {player.player_id: player for player in players}
    for left, right in combinations(players, 2):
        if not _is_legal_pair(left, right):
            continue
        penalty = _homogeneous_exact_pair_penalty(
            left,
            right,
            initial_color=initial_color,
            pair_count=pair_count,
        )
        edge_weights[(left.player_id, right.player_id)] = -penalty

    matching = compute_maximum_weight_matching(
        node_ids=(player.player_id for player in players),
        edge_weights=edge_weights,
        max_cardinality=True,
    )
    if len(matching) != pair_count:
        return None

    total_penalty = 0
    for left_id, right_id in matching:
        total_penalty += _homogeneous_exact_pair_penalty(
            by_id[left_id],
            by_id[right_id],
            initial_color=initial_color,
            pair_count=pair_count,
        )
    return total_penalty


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
        if not _is_legal_pair(left, right):
            continue
        pair_penalty = _homogeneous_exact_pair_penalty(
            left,
            right,
            initial_color=initial_color,
            pair_count=pair_count,
        )
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


def _matching_to_candidate(
    matching: set[tuple[str, str]],
    *,
    players: Sequence[PlayerState],
    sequence_no: int,
) -> _CandidateInternal:
    """Convert one matching result into a candidate with unresolved players."""
    by_id = {player.player_id: player for player in players}
    matched_ids: set[str] = set()
    raw_pairs: list[tuple[PlayerState, PlayerState]] = []
    for left_id, right_id in matching:
        left = by_id[left_id]
        right = by_id[right_id]
        raw_pairs.append((left, right))
        matched_ids.add(left_id)
        matched_ids.add(right_id)

    unresolved = tuple(
        sorted(
            (player for player in players if player.player_id not in matched_ids),
            key=_player_rank_key,
        )
    )
    sorted_pairs = tuple(sorted(raw_pairs, key=_candidate_pair_sort_key))
    return _CandidateInternal(
        pairings=sorted_pairs,
        unresolved=unresolved,
        bye_player=None,
        sequence_no=sequence_no,
    )


def _solve_homogeneous_even_players_via_bipartite_fallback(
    players: Sequence[PlayerState],
    *,
    initial_color: Color,
) -> _EvenPairingInternal | None:
    """Approximate large homogeneous brackets with py4swiss-style D.1/D.2 steps."""
    state = _build_homogeneous_matching_state(players, initial_color=initial_color)
    if state is None:
        return None

    _apply_homogeneous_remainder_steps(state, state.players)
    candidate = state.to_candidate()
    return _EvenPairingInternal(pairings=candidate.pairings, unresolved=candidate.unresolved)


def _solve_even_players_via_heterogeneous_weighted_steps(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    """Approximate large heterogeneous brackets with py4swiss-style D.3/D.1 steps."""
    state = _build_heterogeneous_matching_state(players, context=context)
    if state is None:
        return None

    mdps = [player for player in state.players if player.player_id in context.mdp_ids]
    residents = [player for player in state.players if player.player_id not in context.mdp_ids]
    resident_ids = {player.player_id for player in residents}
    heterogeneous_s1: list[PlayerState] = []

    for mdp in mdps:
        partner = state.partner(mdp)
        has_resident_match = partner is not None and partner.player_id in resident_ids
        if not has_resident_match:
            # Article 4.4 first maximizes the number of paired MDPs. Use a
            # dominating bonus here so a feasible MDP-resident match wins
            # before pair-local penalty tie-breaks are considered.
            state.add_to_weights(mdp, residents, state.final_bonus)
            state.update_matching()
            partner = state.partner(mdp)
            has_resident_match = partner is not None and partner.player_id in resident_ids
        if has_resident_match:
            heterogeneous_s1.append(mdp)
            state.add_to_weights(mdp, residents, len(state.players))

    heterogeneous_s2: list[PlayerState] = []
    for mdp in heterogeneous_s1:
        state.add_to_weights(mdp, residents[::-1], 0, increment=True)
        state.update_matching()
        partner = state.partner(mdp)
        if partner is None or partner.player_id not in resident_ids:
            continue
        heterogeneous_s2.append(partner)
        state.finalize_match(mdp, partner)

    paired_resident_ids = {player.player_id for player in heterogeneous_s2}
    remainder = [player for player in residents if player.player_id not in paired_resident_ids]
    _apply_homogeneous_remainder_steps(state, remainder)

    candidate = state.to_candidate()
    return _EvenPairingInternal(pairings=candidate.pairings, unresolved=candidate.unresolved)


def _solve_without_bye_candidate_via_weighted_steps(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _CandidateInternal | None:
    """Approximate large odd non-final brackets without explicit downfloater loops.

    For large brackets, iterating all possible downfloaters breaks the Dutch
    generation order badly. A closer approximation is to keep the unmatched
    player inside the weighted S1/S2 process itself, like py4swiss does via its
    bracket matcher with lower-bracket vertices.
    """
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if not ordered_players:
        return _CandidateInternal(pairings=(), unresolved=(), bye_player=None, sequence_no=0)

    if context.mdp_ids:
        state = _build_heterogeneous_matching_state(ordered_players, context=context)
        if state is None:
            return None

        mdps = [player for player in state.players if player.player_id in context.mdp_ids]
        residents = [player for player in state.players if player.player_id not in context.mdp_ids]
        resident_ids = {player.player_id for player in residents}
        heterogeneous_s1: list[PlayerState] = []

        for mdp in mdps:
            partner = state.partner(mdp)
            has_resident_match = partner is not None and partner.player_id in resident_ids
            if not has_resident_match:
                # Article 4.4 first maximizes the number of paired MDPs. Use a
                # dominating bonus here so a feasible MDP-resident match wins
                # before pair-local penalty tie-breaks are considered.
                state.add_to_weights(mdp, residents, state.final_bonus)
                state.update_matching()
                partner = state.partner(mdp)
                has_resident_match = partner is not None and partner.player_id in resident_ids
            if has_resident_match:
                heterogeneous_s1.append(mdp)
                state.add_to_weights(mdp, residents, len(state.players))

        heterogeneous_s2: list[PlayerState] = []
        for mdp in heterogeneous_s1:
            state.add_to_weights(mdp, residents[::-1], 0, increment=True)
            state.update_matching()
            partner = state.partner(mdp)
            if partner is None or partner.player_id not in resident_ids:
                continue
            heterogeneous_s2.append(partner)
            state.finalize_match(mdp, partner)

        paired_resident_ids = {player.player_id for player in heterogeneous_s2}
        remainder = [player for player in residents if player.player_id not in paired_resident_ids]
        _apply_homogeneous_remainder_steps(state, remainder)
        return state.to_candidate()

    state = _build_homogeneous_matching_state(
        ordered_players,
        initial_color=context.initial_color,
    )
    if state is None:
        return None
    _apply_homogeneous_remainder_steps(state, state.players)
    return state.to_candidate()


@cache
def _refine_weighted_homogeneous_odd_candidate(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    weighted_candidate: _CandidateInternal,
    sequential_search_max_players: int,
    scan_max_players: int = _ODD_HOMOGENEOUS_REFINEMENT_SCAN_MAX_PLAYERS,
) -> _CandidateInternal:
    """Refine medium-size odd homogeneous brackets around the weighted result.

    The weighted odd-bracket fallback is usually close, but can miss the best
    original-S2 downfloater on medium-size fixtures. Re-checking only those
    candidates preserves the observed parity improvement without the runtime
    cost of scanning every possible downfloater.
    """
    if context.next_bracket_validator is not None and context.next_bracket_key is None:
        return weighted_candidate

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    split_size = len(ordered_players) // 2
    original_s2 = ordered_players[split_size:]
    candidate_specs = tuple((index, player) for index, player in enumerate(original_s2))

    if weighted_candidate.unresolved:
        weighted_downfloater_id = weighted_candidate.unresolved[0].player_id
        for index, player in enumerate(original_s2):
            if player.player_id == weighted_downfloater_id:
                candidate_specs = candidate_specs[: index + 1]
                break

    if (
        context.next_bracket_validator is not None
        and len(ordered_players) <= _ODD_HOMOGENEOUS_REFINEMENT_SKIP_MAX_PLAYERS_WITH_NEXT_BRACKET
    ):
        if len(candidate_specs) <= _ODD_HOMOGENEOUS_C8_TAIL_SCAN_CANDIDATES:
            return weighted_candidate
        candidate_specs = candidate_specs[-_ODD_HOMOGENEOUS_C8_TAIL_SCAN_CANDIDATES:]
    if len(ordered_players) > scan_max_players:
        return weighted_candidate

    refinement_search_limit = min(
        sequential_search_max_players,
        _ODD_REFINEMENT_EXACT_SEARCH_MAX_PLAYERS,
    )

    best_candidate = weighted_candidate
    best_key_without_generation = _candidate_quality_key(
        candidate=weighted_candidate,
        context=context,
    )[:-1]
    best_article_order_key = _homogeneous_article_order_key(
        players=ordered_players,
        candidate=weighted_candidate,
    )
    best_generation_order = len(original_s2)

    for sequence_no, downfloater in candidate_specs:
        if weighted_candidate.unresolved == (downfloater,):
            best_generation_order = sequence_no
            continue
        rest = tuple(
            player for player in ordered_players if player.player_id != downfloater.player_id
        )
        even_result = _solve_even_players(
            rest,
            context=context,
            sequential_search_max_players=refinement_search_limit,
        )
        candidate = _CandidateInternal(
            pairings=even_result.pairings,
            unresolved=tuple(sorted((*even_result.unresolved, downfloater), key=_player_rank_key)),
            bye_player=None,
            sequence_no=sequence_no,
        )
        candidate_key = _candidate_quality_key(candidate=candidate, context=context)
        key_without_generation = candidate_key[:-1]
        article_order_key = _homogeneous_article_order_key(
            players=ordered_players,
            candidate=candidate,
        )

        if key_without_generation < best_key_without_generation:
            best_key_without_generation = key_without_generation
            best_article_order_key = article_order_key
            best_generation_order = sequence_no
            best_candidate = candidate
            continue

        if key_without_generation > best_key_without_generation:
            continue

        if article_order_key < best_article_order_key:
            best_article_order_key = article_order_key
            best_generation_order = sequence_no
            best_candidate = candidate
            continue

        if article_order_key != best_article_order_key:
            continue

        if sequence_no < best_generation_order:
            best_generation_order = sequence_no
            best_candidate = candidate

    return best_candidate


@cache
def _refine_weighted_heterogeneous_odd_candidate(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    weighted_candidate: _CandidateInternal,
) -> _CandidateInternal:
    """Restore exact odd heterogeneous choice when the candidate space is still cheap.

    Fast mode can skip the exact heterogeneous scan because of the bracket-size
    cap even when the article-order candidate space is tiny. In those cases,
    reuse the exact sequence search as a narrow refinement instead of trusting
    the weighted approximation's downfloater choice.
    """
    if len(context.mdp_ids) == 1 and context.next_bracket_validator is None:
        return weighted_candidate

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    exact_upper_bound = _heterogeneous_exact_candidate_upper_bound(
        len(ordered_players),
        len(context.mdp_ids),
    )
    if (
        len(ordered_players) > _ODD_HETEROGENEOUS_REFINEMENT_MAX_PLAYERS
        or exact_upper_bound > _ODD_HETEROGENEOUS_REFINEMENT_EXACT_UPPER_BOUND
    ):
        return weighted_candidate

    exact_candidates = _iter_heterogeneous_candidates(ordered_players, context=context)
    max_candidates = _ODD_HETEROGENEOUS_REFINEMENT_MAX_CANDIDATES
    if context.next_bracket_validator is not None:
        max_candidates = _ODD_HETEROGENEOUS_REFINEMENT_MAX_CANDIDATES_WITH_NEXT_BRACKET
    if len(exact_candidates) > max_candidates:
        return weighted_candidate

    best_candidate = _select_best_candidate(exact_candidates, context=context)
    return best_candidate or weighted_candidate


@cache
def _refine_weighted_single_mdp_odd_candidate(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int,
) -> _CandidateInternal | None:
    """Refine small one-MDP odd brackets by scanning resident partners only."""
    if context.next_bracket_validator is not None:
        return None

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if len(ordered_players) > _SINGLE_MDP_ODD_REFINEMENT_MAX_PLAYERS or len(context.mdp_ids) != 1:
        return None

    mdp = next((player for player in ordered_players if player.player_id in context.mdp_ids), None)
    if mdp is None:
        return None

    residents = tuple(player for player in ordered_players if player.player_id != mdp.player_id)
    best_candidate: _CandidateInternal | None = None
    best_key: tuple[object, ...] | None = None
    refinement_search_limit = min(
        sequential_search_max_players,
        _SINGLE_MDP_ODD_REFINEMENT_SEARCH_MAX_PLAYERS,
    )

    for sequence_no, resident in enumerate(residents):
        if not _is_legal_pair(mdp, resident, context=context):
            continue
        remainder_players = tuple(
            player for player in residents if player.player_id != resident.player_id
        )
        remainder_candidate = _solve_without_bye_candidate(
            remainder_players,
            context=BracketContext(initial_color=context.initial_color),
            sequential_search_max_players=refinement_search_limit,
        )
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

    return best_candidate


@cache
def _refine_weighted_single_mdp_remainder_candidate(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    weighted_candidate: _CandidateInternal,
    sequential_search_max_players: int,
) -> _CandidateInternal:
    """Re-solve the weighted one-MDP remainder once before broader refinement.

    The weighted heterogeneous fallback often picks the correct MDP partner but
    can still miss the best resident downfloater in the homogeneous remainder.
    Re-solving only that remainder is much cheaper than scanning every partner
    and is enough to recover medium-size one-MDP cases like Graz round 4.
    """
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if len(context.mdp_ids) != 1 or len(weighted_candidate.unresolved) != 1:
        return weighted_candidate

    mdp = next((player for player in ordered_players if player.player_id in context.mdp_ids), None)
    if mdp is None:
        return weighted_candidate

    mdp_partner: PlayerState | None = None
    for player_a, player_b in weighted_candidate.pairings:
        mdp_pair = _mdp_and_opponent(player_a, player_b, context=context)
        if mdp_pair is None or mdp_pair[0].player_id != mdp.player_id:
            continue
        mdp_partner = mdp_pair[1]
        break

    if mdp_partner is None:
        return weighted_candidate

    residents = tuple(player for player in ordered_players if player.player_id != mdp.player_id)
    refinement_search_limit = min(
        sequential_search_max_players,
        _SINGLE_MDP_ODD_REFINEMENT_SEARCH_MAX_PLAYERS,
    )
    remainder_players = tuple(
        player for player in residents if player.player_id != mdp_partner.player_id
    )
    remainder_context = BracketContext(initial_color=context.initial_color)
    remainder_candidate = _solve_without_bye_candidate(
        remainder_players,
        context=remainder_context,
        sequential_search_max_players=refinement_search_limit,
    )
    if (
        _ODD_HOMOGENEOUS_REFINEMENT_SCAN_MAX_PLAYERS
        < len(remainder_players)
        <= _SINGLE_MDP_REMAINDER_HOMOGENEOUS_REFINEMENT_MAX_PLAYERS
    ):
        weighted_remainder_candidate = _solve_without_bye_candidate_via_weighted_steps(
            remainder_players,
            context=remainder_context,
        )
        if weighted_remainder_candidate is not None and weighted_remainder_candidate.unresolved:
            remainder_candidate = _refine_weighted_homogeneous_odd_candidate(
                remainder_players,
                context=remainder_context,
                weighted_candidate=weighted_remainder_candidate,
                sequential_search_max_players=refinement_search_limit,
                scan_max_players=_SINGLE_MDP_REMAINDER_HOMOGENEOUS_REFINEMENT_MAX_PLAYERS,
            )
    sequence_no = next(
        index for index, player in enumerate(residents) if player.player_id == mdp_partner.player_id
    )
    refined_candidate = _CandidateInternal(
        pairings=tuple(
            sorted(
                (*remainder_candidate.pairings, (mdp, mdp_partner)),
                key=_candidate_pair_sort_key,
            )
        ),
        unresolved=remainder_candidate.unresolved,
        bye_player=None,
        sequence_no=sequence_no,
    )
    if _candidate_quality_key(
        candidate=refined_candidate, context=context
    ) < _candidate_quality_key(
        candidate=weighted_candidate,
        context=context,
    ):
        return refined_candidate
    return weighted_candidate


def _select_large_final_bye_candidate_via_weighted_steps(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    bye_candidates: Sequence[PlayerState],
    sequential_search_max_players: int,
) -> _CandidateInternal | None:
    """Pick one large final-bracket bye without scanning every legal candidate.

    For very large odd final brackets, evaluating every legal bye candidate means
    re-solving the full even remainder once per player. Reuse the odd weighted
    matcher to identify the likely article-order bye first, then solve the
    even remainder exactly once for that selected player.
    """
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if len(ordered_players) <= _ODD_FINAL_BYE_SCAN_MAX_PLAYERS:
        return None

    weighted_candidate = _solve_without_bye_candidate_via_weighted_steps(
        ordered_players,
        context=context,
    )
    if weighted_candidate is None or len(weighted_candidate.unresolved) != 1:
        return None

    bye_player = weighted_candidate.unresolved[0]
    reversed_bye_candidates = tuple(reversed(tuple(bye_candidates)))
    try:
        sequence_no = next(
            index
            for index, candidate in enumerate(reversed_bye_candidates)
            if candidate.player_id == bye_player.player_id
        )
    except StopIteration:
        return None

    rest = tuple(player for player in ordered_players if player.player_id != bye_player.player_id)
    even_result = _solve_even_players(
        rest,
        context=context,
        sequential_search_max_players=sequential_search_max_players,
    )
    return _CandidateInternal(
        pairings=even_result.pairings,
        unresolved=even_result.unresolved,
        bye_player=bye_player,
        sequence_no=sequence_no,
    )


def _solve_even_players(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int = _SEQUENTIAL_SEARCH_MAX_PLAYERS,
    allow_heuristic_fallback: bool = True,
) -> _EvenPairingInternal:
    """Compute one maximum-cardinality matching for an even-sized set."""
    if len(players) % 2 != 0:
        raise PairingError("internal even solver received odd player count")

    exact_candidate_max = _exact_sequence_candidate_limit(
        allow_heuristic_fallback=allow_heuristic_fallback
    )

    if not context.mdp_ids and not allow_heuristic_fallback:
        exact_shortcut = _solve_homogeneous_even_players_via_zero_exchange_exact_shortcut(
            players,
            initial_color=context.initial_color,
        )
        if exact_shortcut is not None:
            return exact_shortcut

    if len(context.mdp_ids) == 1 and not allow_heuristic_fallback:
        single_mdp_exact = _solve_even_players_via_single_mdp_exact(players, context=context)
        if single_mdp_exact is not None:
            return single_mdp_exact

    if context.mdp_ids and _use_heterogeneous_exact_search(
        len(players),
        mdp_count=len(context.mdp_ids),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    ):
        sequence_result = _solve_even_players_via_heterogeneous_sequence(players, context=context)
        if sequence_result is not None:
            return sequence_result

    if not context.mdp_ids and _use_homogeneous_exact_search(
        len(players),
        sequential_search_max_players=sequential_search_max_players,
        exact_candidate_max=exact_candidate_max,
    ):
        sequence_result = _solve_even_players_via_sequence(players, context=context)
        if sequence_result is not None:
            return sequence_result

    if not allow_heuristic_fallback:
        raise ExactSearchUnavailableError(
            "exact Dutch mode currently requires heuristic fallback for this even bracket"
        )

    if context.mdp_ids:
        fallback_result = _solve_even_players_via_heterogeneous_weighted_steps(
            players,
            context=context,
        )
        if fallback_result is not None and not fallback_result.unresolved:
            return fallback_result
    else:
        fallback_result = _solve_homogeneous_even_players_via_bipartite_fallback(
            players,
            initial_color=context.initial_color,
        )
        if fallback_result is not None and not fallback_result.unresolved:
            return fallback_result

    by_id = {player.player_id: player for player in players}
    edge_weights: dict[tuple[str, str], int] = {}

    for left, right in combinations(players, 2):
        if not _is_legal_pair(left, right, context=context):
            continue
        key = (left.player_id, right.player_id)
        edge_weights[key] = _edge_weight(left, right, context=context)

    matching = compute_maximum_weight_matching(
        node_ids=(player.player_id for player in players),
        edge_weights=edge_weights,
        max_cardinality=True,
    )

    matched_ids: set[str] = set()
    raw_pairs: list[tuple[PlayerState, PlayerState]] = []
    for left_id, right_id in matching:
        left = by_id[left_id]
        right = by_id[right_id]
        raw_pairs.append((left, right))
        matched_ids.add(left_id)
        matched_ids.add(right_id)

    unresolved = tuple(
        sorted(
            (player for player in players if player.player_id not in matched_ids),
            key=_player_rank_key,
        )
    )

    sorted_pairs = tuple(
        sorted(
            raw_pairs,
            key=lambda pair: (
                _player_rank_key(pair[0]),
                _player_rank_key(pair[1]),
            ),
        )
    )
    unrestricted_result = _EvenPairingInternal(pairings=sorted_pairs, unresolved=unresolved)

    if context.mdp_ids:
        fallback_result = _solve_even_players_via_heterogeneous_weighted_steps(
            players,
            context=context,
        )
        if fallback_result is not None:
            fallback_pairs = len(fallback_result.pairings)
            unrestricted_pairs = len(unrestricted_result.pairings)
            if fallback_pairs > unrestricted_pairs:
                return fallback_result
            if fallback_pairs == unrestricted_pairs:
                fallback_candidate = _CandidateInternal(
                    pairings=fallback_result.pairings,
                    unresolved=fallback_result.unresolved,
                    bye_player=None,
                    sequence_no=0,
                )
                unrestricted_candidate = _CandidateInternal(
                    pairings=unrestricted_result.pairings,
                    unresolved=unrestricted_result.unresolved,
                    bye_player=None,
                    sequence_no=1,
                )
                if _candidate_quality_key(
                    candidate=fallback_candidate,
                    context=context,
                ) <= _candidate_quality_key(
                    candidate=unrestricted_candidate,
                    context=context,
                ):
                    return fallback_result
    else:
        fallback_result = _solve_homogeneous_even_players_via_bipartite_fallback(
            players,
            initial_color=context.initial_color,
        )
        if fallback_result is not None:
            fallback_pairs = len(fallback_result.pairings)
            unrestricted_pairs = len(unrestricted_result.pairings)
            if fallback_pairs > unrestricted_pairs:
                return fallback_result
            if fallback_pairs == unrestricted_pairs:
                fallback_candidate = _CandidateInternal(
                    pairings=fallback_result.pairings,
                    unresolved=fallback_result.unresolved,
                    bye_player=None,
                    sequence_no=0,
                )
                unrestricted_candidate = _CandidateInternal(
                    pairings=unrestricted_result.pairings,
                    unresolved=unrestricted_result.unresolved,
                    bye_player=None,
                    sequence_no=1,
                )
                if _candidate_quality_key(
                    candidate=fallback_candidate,
                    context=BracketContext(initial_color=context.initial_color),
                ) <= _candidate_quality_key(
                    candidate=unrestricted_candidate,
                    context=BracketContext(initial_color=context.initial_color),
                ):
                    return fallback_result

    return unrestricted_result


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
    oriented_pairs = tuple(
        _choose_color_order(left, right, initial_color=initial_color)
        for left, right in candidate.pairings
    )
    downfloaters = _candidate_downfloaters(candidate)

    c5 = candidate.bye_player.score if candidate.bye_player is not None else 0
    c6 = -len(candidate.pairings)
    c7 = tuple(player.score for player in sorted(downfloaters, key=lambda player: -player.score))
    c9 = candidate.bye_player.unplayed_games if candidate.bye_player is not None else 0

    c10, c11, c12, c13 = _collect_pair_quality_counts(oriented_pairs)

    resident_downfloaters = tuple(
        player for player in downfloaters if player.player_id not in context.mdp_ids
    )
    c14 = sum(
        int(player.had_float(rounds_ago=1, kind=FloatKind.DOWN)) for player in resident_downfloaters
    )
    c16 = sum(
        int(player.had_float(rounds_ago=2, kind=FloatKind.DOWN)) for player in resident_downfloaters
    )

    c15, c17, c18, c19, c20, c21 = _collect_mdp_quality(
        oriented_pairs=oriented_pairs,
        context=context,
    )

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
    return 0 if validator(downfloaters) else 1


def _next_bracket_key(
    *,
    downfloaters: tuple[PlayerState, ...],
    context: BracketContext,
) -> NextBracketKey:
    key_fn = context.next_bracket_key
    if key_fn is None:
        return NextBracketKey()
    key = key_fn(downfloaters)
    if key is None:
        return NextBracketKey()
    return key


def _collect_pair_quality_counts(
    oriented_pairs: Sequence[tuple[PlayerState, PlayerState]],
) -> tuple[int, int, int, int]:
    c10 = 0
    c11 = 0
    c12 = 0
    c13 = 0
    for white, black in oriented_pairs:
        p10, p11, p12, p13 = _pair_color_quality(white=white, black=black)
        c10 += p10
        c11 += p11
        c12 += p12
        c13 += p13
    return c10, c11, c12, c13


def _collect_mdp_quality(
    *,
    oriented_pairs: Sequence[tuple[PlayerState, PlayerState]],
    context: BracketContext,
) -> tuple[int, int, tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    c15 = 0
    c17 = 0
    c18_values: list[int] = []
    c19_values: list[int] = []
    c20_values: list[int] = []
    c21_values: list[int] = []

    for white, black in oriented_pairs:
        mdp_pair = _mdp_and_opponent(white, black, context=context)
        if mdp_pair is None:
            continue
        mdp_player, opponent = mdp_pair
        score_difference = _pair_score_difference(mdp_player, opponent)

        if opponent.had_float(rounds_ago=1, kind=FloatKind.UP):
            c15 += 1
            c19_values.append(score_difference)
        if opponent.had_float(rounds_ago=2, kind=FloatKind.UP):
            c17 += 1
            c21_values.append(score_difference)
        if mdp_player.had_float(rounds_ago=1, kind=FloatKind.DOWN):
            c18_values.append(score_difference)
        if mdp_player.had_float(rounds_ago=2, kind=FloatKind.DOWN):
            c20_values.append(score_difference)

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
    c8_key = _next_bracket_key(downfloaters=downfloaters, context=context)

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
    by_id = {player.player_id: player for player in players}
    reconstructed_pairs: list[tuple[PlayerState, PlayerState]] = []
    bye_player: PlayerState | None = None

    for pairing in result.pairings:
        white = by_id[pairing.white_id]
        if pairing.black_id is None:
            bye_player = white
            continue
        reconstructed_pairs.append((white, by_id[pairing.black_id]))

    candidate = _CandidateInternal(
        pairings=tuple(reconstructed_pairs),
        unresolved=tuple(by_id[player_id] for player_id in result.unpaired_ids),
        bye_player=bye_player,
        sequence_no=0,
    )
    local_key = _candidate_quality_key(
        candidate=candidate,
        context=BracketContext(
            mdp_ids=context.mdp_ids,
            initial_color=context.initial_color,
        ),
    )
    return NextBracketLocalKey(
        c5=local_key[0],
        c6=local_key[1],
        c7=local_key[2],
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
                allow_heuristic_fallback=False,
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


def _solve_even_players_via_single_mdp_exact(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
) -> _EvenPairingInternal | None:
    return _solve_even_players_via_single_mdp_exact_cached(
        tuple(sorted(players, key=_player_rank_key)),
        context.mdp_ids,
        context.initial_color,
    )


def _solve_without_bye_candidate_uncached(
    players: tuple[PlayerState, ...],
    *,
    context: BracketContext,
    sequential_search_max_players: int,
    allow_heuristic_fallback: bool,
) -> _CandidateInternal:
    """Return best candidate for a bracket that cannot assign a pairing bye."""
    ordered_players = players
    if not ordered_players:
        return _CandidateInternal(pairings=(), unresolved=(), bye_player=None, sequence_no=0)

    exact_candidate_max = _exact_sequence_candidate_limit(
        allow_heuristic_fallback=allow_heuristic_fallback
    )

    if len(ordered_players) % 2 == 0:
        even_result = _solve_even_players(
            ordered_players,
            context=context,
            sequential_search_max_players=sequential_search_max_players,
            allow_heuristic_fallback=allow_heuristic_fallback,
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
        )
        if best_candidate is not None:
            return best_candidate

    if allow_heuristic_fallback and (
        len(ordered_players) > sequential_search_max_players
        or (context.mdp_ids and not use_exact_heterogeneous)
        or (not context.mdp_ids and not use_exact_homogeneous)
    ):
        weighted_candidate = _solve_without_bye_candidate_via_weighted_steps(
            ordered_players,
            context=context,
        )
        if weighted_candidate is not None and weighted_candidate.unresolved:
            refined_weighted_candidate = weighted_candidate
            if len(weighted_candidate.unresolved) == 1:
                if len(context.mdp_ids) == 1:
                    refined_weighted_candidate = _refine_weighted_single_mdp_remainder_candidate(
                        ordered_players,
                        context=context,
                        weighted_candidate=refined_weighted_candidate,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                    refined_single_mdp = _refine_weighted_single_mdp_odd_candidate(
                        ordered_players,
                        context=context,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                    if refined_single_mdp is not None:
                        refined_weighted_candidate = refined_single_mdp
                if context.mdp_ids and len(ordered_players) <= _ODD_DOWNFLOATER_SCAN_MAX_PLAYERS:
                    return _refine_weighted_heterogeneous_odd_candidate(
                        ordered_players,
                        context=context,
                        weighted_candidate=refined_weighted_candidate,
                    )
                if (
                    not context.mdp_ids
                    and len(ordered_players) <= _ODD_HOMOGENEOUS_REFINEMENT_SCAN_MAX_PLAYERS
                ):
                    return _refine_weighted_homogeneous_odd_candidate(
                        ordered_players,
                        context=context,
                        weighted_candidate=refined_weighted_candidate,
                        sequential_search_max_players=sequential_search_max_players,
                    )
            return refined_weighted_candidate

    generated: list[_CandidateInternal] = []
    unsupported_found = False
    if allow_heuristic_fallback:
        downfloater_groups = tuple((player,) for player in ordered_players)
    else:
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

            remainder_candidates: tuple[_CandidateInternal, ...]
            if adjusted_context.mdp_ids and _use_heterogeneous_exact_search(
                len(rest),
                mdp_count=len(adjusted_context.mdp_ids),
                sequential_search_max_players=sequential_search_max_players,
                exact_candidate_max=exact_candidate_max,
            ):
                remainder_candidates = _iter_heterogeneous_candidates(
                    rest,
                    context=adjusted_context,
                )
            elif _use_homogeneous_exact_search(
                len(rest),
                sequential_search_max_players=sequential_search_max_players,
                exact_candidate_max=exact_candidate_max,
            ):
                remainder_candidates = _iter_homogeneous_candidates(rest)
            else:
                try:
                    even_result = _solve_even_players(
                        rest,
                        context=adjusted_context,
                        sequential_search_max_players=sequential_search_max_players,
                        allow_heuristic_fallback=allow_heuristic_fallback,
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
                if allow_heuristic_fallback:
                    generated.append(candidate)
                else:
                    group_candidates.append(candidate)
                sequence_no += 1

        if not allow_heuristic_fallback and group_candidates:
            best_candidate = _select_best_candidate(group_candidates, context=context)
            if best_candidate is not None:
                return best_candidate

    best_candidate = _select_best_candidate(generated, context=context)
    if best_candidate is None:
        if unsupported_found and not allow_heuristic_fallback:
            raise ExactSearchUnavailableError(
                "exact Dutch mode currently requires heuristic fallback for this odd bracket"
            )
        raise PairingError("internal failure selecting downfloater candidate")
    return best_candidate


@cache
def _solve_without_bye_candidate_cached(
    players: tuple[PlayerState, ...],
    mdp_ids: frozenset[str],
    sequential_search_max_players: int,
    initial_color: Color,
    allow_heuristic_fallback: bool,
) -> _CandidateInternal:
    return _solve_without_bye_candidate_uncached(
        players,
        context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
        sequential_search_max_players=sequential_search_max_players,
        allow_heuristic_fallback=allow_heuristic_fallback,
    )


def _solve_without_bye_candidate(
    players: Sequence[PlayerState],
    *,
    context: BracketContext,
    sequential_search_max_players: int = _SEQUENTIAL_SEARCH_MAX_PLAYERS,
    allow_heuristic_fallback: bool = True,
) -> _CandidateInternal:
    ordered_players = tuple(sorted(players, key=_player_rank_key))
    if context.next_bracket_validator is None and context.next_bracket_key is None:
        return _solve_without_bye_candidate_cached(
            ordered_players,
            context.mdp_ids,
            sequential_search_max_players,
            context.initial_color,
            allow_heuristic_fallback,
        )
    return _solve_without_bye_candidate_uncached(
        ordered_players,
        context=context,
        sequential_search_max_players=sequential_search_max_players,
        allow_heuristic_fallback=allow_heuristic_fallback,
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


def pair_bracket(
    players: Sequence[PlayerState],
    *,
    context: BracketContext | None = None,
    allow_bye: bool = True,
    sequential_search_max_players: int = _SEQUENTIAL_SEARCH_MAX_PLAYERS,
    initial_color: Color = "white",
    allow_heuristic_fallback: bool = True,
) -> PairingResult:
    """Pair one bracket and return pairings plus unresolved player ids.

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
            allow_heuristic_fallback=allow_heuristic_fallback,
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
            allow_heuristic_fallback=allow_heuristic_fallback,
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
        exact_candidate_max=_exact_sequence_candidate_limit(
            allow_heuristic_fallback=allow_heuristic_fallback
        ),
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
        if allow_heuristic_fallback:
            best_candidate = _select_large_final_bye_candidate_via_weighted_steps(
                ordered_players,
                context=local_context,
                bye_candidates=bye_candidates,
                sequential_search_max_players=sequential_search_max_players,
            )
        if best_candidate is None:
            best_key: tuple[object, ...] | None = None
            unsupported_found = False

            # Exact odd-bracket generation already yields article sequence
            # order. Keep the fallback scan aligned with that direction so
            # equal-quality bye candidates still resolve to the same
            # last-sequence resident.
            for sequence_no, bye_candidate in enumerate(reversed(bye_candidates)):
                rest = tuple(
                    player
                    for player in ordered_players
                    if player.player_id != bye_candidate.player_id
                )
                try:
                    even_result = _solve_even_players(
                        rest,
                        context=local_context,
                        sequential_search_max_players=sequential_search_max_players,
                        allow_heuristic_fallback=allow_heuristic_fallback,
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
            if best_candidate is None and unsupported_found and not allow_heuristic_fallback:
                raise ExactSearchUnavailableError(
                    "exact Dutch mode currently requires heuristic fallback for this final bracket"
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


def pair_bracket_exact(
    players: Sequence[PlayerState],
    *,
    context: BracketContext | None = None,
    allow_bye: bool = True,
    sequential_search_max_players: int | None = None,
    initial_color: Color = "white",
) -> PairingResult:
    """Pair one bracket without heuristic fallback.

    This is the first step toward a normative Dutch mode. It uses only the
    current exact-search surface and raises `PairingError` when the solver
    would otherwise switch to weighted or greedy approximations.
    """
    exact_search_max_players = (
        len(players) if sequential_search_max_players is None else sequential_search_max_players
    )
    try:
        return pair_bracket(
            players,
            context=context,
            allow_bye=allow_bye,
            sequential_search_max_players=exact_search_max_players,
            initial_color=initial_color,
            allow_heuristic_fallback=False,
        )
    except ExactSearchUnavailableError as exc:
        raise PairingError(str(exc)) from exc
