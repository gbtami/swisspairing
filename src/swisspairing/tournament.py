"""Tournament-level Dutch round pairing pipeline.

This module orchestrates bracket-by-bracket pairing over scoregroups, carrying
MDPs to the next bracket as required by C.04.3 section 1.9.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from swisspairing.dutch import (
    BracketContext,
    NextBracketKey,
    pair_bracket,
    pairing_result_next_bracket_local_key,
)
from swisspairing.exceptions import PairingError
from swisspairing.model import Pairing, PairingResult, PlayerState

_COLLAPSE_SEARCH_MAX_PLAYERS = 80
_FAST_COLLAPSE_SEARCH_MAX_PLAYERS = 40


def _player_rank_key(player: PlayerState) -> tuple[int, int]:
    return (-player.score, player.pairing_no)


def _collapse_search_max_players(
    *,
    sequential_search_max_players: int | None,
) -> int:
    if sequential_search_max_players is None:
        return _COLLAPSE_SEARCH_MAX_PLAYERS
    return min(_COLLAPSE_SEARCH_MAX_PLAYERS, _FAST_COLLAPSE_SEARCH_MAX_PLAYERS)


@dataclass(frozen=True, slots=True)
class _RoundTailSolution:
    """Recursive round solve result with per-bracket game-count summary."""

    pairings: tuple[Pairing, ...]
    first_result: PairingResult | None
    bracket_game_counts: tuple[int, ...]
    solution_key: tuple[object, ...]


def _published_bracket_pairings(
    result: PairingResult,
    *,
    is_last_bracket: bool,
) -> tuple[Pairing, ...]:
    if is_last_bracket:
        return result.pairings
    return tuple(pairing for pairing in result.pairings if pairing.black_id is not None)


def _paired_game_count(pairings: tuple[Pairing, ...]) -> int:
    return sum(1 for pairing in pairings if pairing.black_id is not None)


def _solution_bye_key(
    *,
    players: tuple[PlayerState, ...],
    result: PairingResult,
) -> tuple[int, int]:
    for pairing in result.pairings:
        if pairing.black_id is not None:
            continue
        bye_player = next(player for player in players if player.player_id == pairing.white_id)
        return (bye_player.score, bye_player.unplayed_games)
    return (0, 0)


def _lowest_possible_bye_key(players: tuple[PlayerState, ...]) -> tuple[int, int]:
    if len(players) % 2 == 0:
        return (0, 0)
    eligible_players = tuple(player for player in players if not player.had_full_point_bye)
    if not eligible_players:
        return (10**9, 10**9)
    lowest_score = min(player.score for player in eligible_players)
    lowest_unplayed_games = min(
        player.unplayed_games for player in eligible_players if player.score == lowest_score
    )
    return (lowest_score, lowest_unplayed_games)


def _flatten_future_game_counts(key: NextBracketKey | None) -> tuple[int, ...]:
    if key is None:
        return ()
    if key.local.c6 == 0 and not key.future_game_counts:
        return ()
    return (key.local.c6, *key.future_game_counts)


def _build_next_bracket_key(
    *,
    players: tuple[PlayerState, ...],
    result: PairingResult,
    mdp_ids: frozenset[str],
    future_key: NextBracketKey | None = None,
) -> NextBracketKey:
    return NextBracketKey(
        local=pairing_result_next_bracket_local_key(
            players=players,
            result=result,
            context=BracketContext(mdp_ids=mdp_ids),
        ),
        future_game_counts=_flatten_future_game_counts(future_key),
    )


def _group_residents_by_score(
    players: tuple[PlayerState, ...],
) -> tuple[tuple[PlayerState, ...], ...]:
    groups: dict[int, list[PlayerState]] = {}
    for player in players:
        groups.setdefault(player.score, []).append(player)
    sorted_scores_desc = sorted(groups.keys(), reverse=True)
    grouped: list[tuple[PlayerState, ...]] = []
    for score in sorted_scores_desc:
        grouped.append(tuple(sorted(groups[score], key=_player_rank_key)))
    return tuple(grouped)


def _pair_bracket_with_optional_limit(
    players: tuple[PlayerState, ...],
    *,
    context: BracketContext,
    allow_bye: bool,
    sequential_search_max_players: int | None,
) -> PairingResult:
    if sequential_search_max_players is None:
        return pair_bracket(players, context=context, allow_bye=allow_bye)
    return pair_bracket(
        players,
        context=context,
        allow_bye=allow_bye,
        sequential_search_max_players=sequential_search_max_players,
    )


def _pair_round_dutch_greedy(
    scoregroups: tuple[tuple[PlayerState, ...], ...],
    *,
    sequential_search_max_players: int | None = None,
) -> tuple[Pairing, ...] | None:
    """Pair one round without global collapse backtracking (fast-path for large events)."""
    all_pairings: list[Pairing] = []
    carried_mdps: tuple[PlayerState, ...] = ()
    index = 0

    while index < len(scoregroups):
        solved = False

        # Keep the large-event path greedy, but allow forward collapse when the
        # immediate scoregroup boundary makes the next bracket unsatisfiable.
        for collapse_size in range(1, len(scoregroups) - index + 1):
            residents = tuple(
                sorted(
                    (
                        player
                        for group in scoregroups[index : index + collapse_size]
                        for player in group
                    ),
                    key=_player_rank_key,
                )
            )
            bracket_players = tuple(sorted((*carried_mdps, *residents), key=_player_rank_key))
            mdp_ids = frozenset(player.player_id for player in carried_mdps)
            is_last_bracket = index + collapse_size == len(scoregroups)

            if is_last_bracket:
                try:
                    bracket_result = _pair_bracket_with_optional_limit(
                        bracket_players,
                        context=BracketContext(mdp_ids=mdp_ids),
                        allow_bye=True,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                except PairingError:
                    continue
                if bracket_result.unpaired_ids:
                    continue
                all_pairings.extend(bracket_result.pairings)
                return tuple(all_pairings)

            next_residents = scoregroups[index + collapse_size]
            next_is_last_bracket = index + collapse_size == len(scoregroups) - 1
            next_bracket_cache: dict[tuple[PlayerState, ...], bool] = {}
            next_bracket_key_cache: dict[tuple[PlayerState, ...], NextBracketKey] = {}

            def next_bracket_validator(
                downfloaters: tuple[PlayerState, ...],
                *,
                next_residents_snapshot: tuple[PlayerState, ...] = next_residents,
                allow_bye_next: bool = next_is_last_bracket,
                next_bracket_cache_snapshot: dict[
                    tuple[PlayerState, ...], bool
                ] = next_bracket_cache,
                next_bracket_key_cache_snapshot: dict[
                    tuple[PlayerState, ...], NextBracketKey
                ] = next_bracket_key_cache,
            ) -> bool:
                ordered_downfloaters = tuple(sorted(downfloaters, key=_player_rank_key))
                cached = next_bracket_cache_snapshot.get(ordered_downfloaters)
                if cached is not None:
                    return cached

                next_players = tuple(
                    sorted((*ordered_downfloaters, *next_residents_snapshot), key=_player_rank_key)
                )
                next_mdp_ids = frozenset(player.player_id for player in ordered_downfloaters)
                try:
                    next_result = _pair_bracket_with_optional_limit(
                        next_players,
                        context=BracketContext(mdp_ids=next_mdp_ids),
                        allow_bye=allow_bye_next,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                except PairingError:
                    next_bracket_cache_snapshot[ordered_downfloaters] = False
                    return False
                next_bracket_key_cache_snapshot[ordered_downfloaters] = _build_next_bracket_key(
                    players=next_players,
                    result=next_result,
                    mdp_ids=next_mdp_ids,
                )
                next_bracket_cache_snapshot[ordered_downfloaters] = True
                return True

            def next_bracket_key(
                downfloaters: tuple[PlayerState, ...],
                *,
                next_bracket_cache_snapshot: dict[
                    tuple[PlayerState, ...], bool
                ] = next_bracket_cache,
                next_bracket_key_cache_snapshot: dict[
                    tuple[PlayerState, ...], NextBracketKey
                ] = next_bracket_key_cache,
            ) -> NextBracketKey | None:
                ordered_downfloaters = tuple(sorted(downfloaters, key=_player_rank_key))
                cached_key = next_bracket_key_cache_snapshot.get(ordered_downfloaters)
                if cached_key is not None:
                    return cached_key
                if not next_bracket_validator(ordered_downfloaters):
                    return None
                if not next_bracket_cache_snapshot.get(ordered_downfloaters, False):
                    return None
                return next_bracket_key_cache_snapshot.get(ordered_downfloaters)

            try:
                bracket_result = _pair_bracket_with_optional_limit(
                    bracket_players,
                    context=BracketContext(
                        mdp_ids=mdp_ids,
                        next_bracket_validator=next_bracket_validator,
                        next_bracket_key=next_bracket_key,
                    ),
                    allow_bye=False,
                    sequential_search_max_players=sequential_search_max_players,
                )
            except PairingError:
                continue

            all_pairings.extend(
                pairing for pairing in bracket_result.pairings if pairing.black_id is not None
            )
            by_id = {player.player_id: player for player in bracket_players}
            carried_mdps = tuple(by_id[player_id] for player_id in bracket_result.unpaired_ids)
            index += collapse_size
            solved = True
            break

        if not solved:
            return None

    return tuple(all_pairings)


def pair_round_dutch(
    players: tuple[PlayerState, ...],
    *,
    sequential_search_max_players: int | None = None,
) -> PairingResult:
    """Pair one full round with bracket chaining over scoregroups.

    References:
    - C.04.3 section 1.9.2: pairing proceeds bracket by bracket from top scoregroup.
    - C.04.3 section 3.7: heterogeneous brackets with MDPs.
    - C.04.3 [C8]: current-bracket downfloaters should keep next-bracket outlook viable.
    - C.04.3 sections B.6-B.9: collapse to larger pairing brackets when needed.

    Tuning:
    - `sequential_search_max_players` overrides the bracket-level exact-search
      size cap used by `pair_bracket`; `None` keeps the default.
    - When a cap is active, round-level collapse backtracking also uses a lower
      player-count ceiling so fast mode can hand medium-size events to the
      greedy pipeline sooner.
    """
    if not players:
        return PairingResult(pairings=(), unpaired_ids=())

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    scoregroups = _group_residents_by_score(ordered_players)

    # Collapse backtracking improves parity in rare edge cases, but its search
    # space can grow quickly. For larger tournaments, keep a bounded fast path.
    if len(ordered_players) > _collapse_search_max_players(
        sequential_search_max_players=sequential_search_max_players
    ):
        pairings = _pair_round_dutch_greedy(
            scoregroups,
            sequential_search_max_players=sequential_search_max_players,
        )
        if pairings is None:
            raise PairingError("round cannot be fully paired under current absolute constraints")
        return PairingResult(pairings=pairings, unpaired_ids=())

    @cache
    def solve(
        remaining_groups: tuple[tuple[PlayerState, ...], ...],
        carried_mdps: tuple[PlayerState, ...],
    ) -> _RoundTailSolution | None:
        if not remaining_groups:
            if carried_mdps:
                return None
            return _RoundTailSolution(
                pairings=(),
                first_result=None,
                bracket_game_counts=(),
                solution_key=(),
            )

        best_solution: _RoundTailSolution | None = None
        best_key: tuple[object, ...] | None = None
        all_remaining_players = tuple(
            sorted(
                (player for group in remaining_groups for player in group),
                key=_player_rank_key,
            )
        )
        subproblem_players = tuple(
            sorted((*carried_mdps, *all_remaining_players), key=_player_rank_key)
        )
        best_possible_bye_key = _lowest_possible_bye_key(subproblem_players)

        for collapse_size in range(1, len(remaining_groups) + 1):
            residents = tuple(
                sorted(
                    (player for group in remaining_groups[:collapse_size] for player in group),
                    key=_player_rank_key,
                )
            )
            bracket_players = tuple(sorted((*carried_mdps, *residents), key=_player_rank_key))
            mdp_ids = frozenset(player.player_id for player in carried_mdps)
            tail_groups = remaining_groups[collapse_size:]
            is_last_bracket = len(tail_groups) == 0

            if is_last_bracket:
                try:
                    bracket_result = _pair_bracket_with_optional_limit(
                        bracket_players,
                        context=BracketContext(mdp_ids=mdp_ids),
                        allow_bye=True,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                except PairingError:
                    continue
                if bracket_result.unpaired_ids:
                    continue
                local_key = pairing_result_next_bracket_local_key(
                    players=bracket_players,
                    result=bracket_result,
                    context=BracketContext(mdp_ids=mdp_ids),
                )
                bye_key = _solution_bye_key(players=bracket_players, result=bracket_result)
                candidate_solution = _RoundTailSolution(
                    pairings=bracket_result.pairings,
                    first_result=bracket_result,
                    bracket_game_counts=(_paired_game_count(bracket_result.pairings),),
                    solution_key=(*bye_key, collapse_size, local_key),
                )
                if best_key is None or candidate_solution.solution_key < best_key:
                    best_key = candidate_solution.solution_key
                    best_solution = candidate_solution
                if best_key[:2] == best_possible_bye_key and best_key[2] == 1:
                    break
                continue

            next_bracket_key_cache: dict[tuple[PlayerState, ...], NextBracketKey | None] = {}

            def next_bracket_validator(
                downfloaters: tuple[PlayerState, ...],
                *,
                tail_groups_snapshot: tuple[tuple[PlayerState, ...], ...] = tail_groups,
            ) -> bool:
                ordered_downfloaters = tuple(sorted(downfloaters, key=_player_rank_key))
                return solve(tail_groups_snapshot, ordered_downfloaters) is not None

            def next_bracket_key(
                downfloaters: tuple[PlayerState, ...],
                *,
                tail_groups_snapshot: tuple[tuple[PlayerState, ...], ...] = tail_groups,
                next_bracket_key_cache_snapshot: dict[
                    tuple[PlayerState, ...], NextBracketKey | None
                ] = next_bracket_key_cache,
            ) -> NextBracketKey | None:
                ordered_downfloaters = tuple(sorted(downfloaters, key=_player_rank_key))
                if ordered_downfloaters in next_bracket_key_cache_snapshot:
                    return next_bracket_key_cache_snapshot[ordered_downfloaters]
                next_residents = tail_groups_snapshot[0]
                next_tail_groups = tail_groups_snapshot[1:]
                next_is_last_bracket = len(next_tail_groups) == 0
                next_players = tuple(
                    sorted((*ordered_downfloaters, *next_residents), key=_player_rank_key)
                )
                next_mdp_ids = frozenset(player.player_id for player in ordered_downfloaters)

                if next_is_last_bracket:
                    try:
                        next_result = _pair_bracket_with_optional_limit(
                            next_players,
                            context=BracketContext(mdp_ids=next_mdp_ids),
                            allow_bye=True,
                            sequential_search_max_players=sequential_search_max_players,
                        )
                    except PairingError:
                        next_bracket_key_cache_snapshot[ordered_downfloaters] = None
                        return None
                    next_key = _build_next_bracket_key(
                        players=next_players,
                        result=next_result,
                        mdp_ids=next_mdp_ids,
                    )
                    next_bracket_key_cache_snapshot[ordered_downfloaters] = next_key
                    return next_key

                def next_next_validator(next_downfloaters: tuple[PlayerState, ...]) -> bool:
                    ordered_next_downfloaters = tuple(
                        sorted(next_downfloaters, key=_player_rank_key)
                    )
                    return solve(next_tail_groups, ordered_next_downfloaters) is not None

                # Preserve C8 feasibility pruning, but stop the tie-break key
                # at the immediate next bracket to avoid medium-size collapse
                # search blow-ups from recursive downstream key expansion.
                try:
                    next_result = _pair_bracket_with_optional_limit(
                        next_players,
                        context=BracketContext(
                            mdp_ids=next_mdp_ids,
                            next_bracket_validator=next_next_validator,
                        ),
                        allow_bye=False,
                        sequential_search_max_players=sequential_search_max_players,
                    )
                except PairingError:
                    next_bracket_key_cache_snapshot[ordered_downfloaters] = None
                    return None
                next_key = _build_next_bracket_key(
                    players=next_players,
                    result=next_result,
                    mdp_ids=next_mdp_ids,
                )
                next_bracket_key_cache_snapshot[ordered_downfloaters] = next_key
                return next_key

            try:
                bracket_result = _pair_bracket_with_optional_limit(
                    bracket_players,
                    context=BracketContext(
                        mdp_ids=mdp_ids,
                        next_bracket_validator=next_bracket_validator,
                        next_bracket_key=next_bracket_key,
                    ),
                    allow_bye=False,
                    sequential_search_max_players=sequential_search_max_players,
                )
            except PairingError:
                continue

            by_id = {player.player_id: player for player in bracket_players}
            downfloaters = tuple(
                sorted(
                    (by_id[player_id] for player_id in bracket_result.unpaired_ids),
                    key=_player_rank_key,
                )
            )
            tail_solution = solve(tail_groups, downfloaters)
            if tail_solution is None:
                continue

            current_pairings = _published_bracket_pairings(
                bracket_result,
                is_last_bracket=False,
            )
            local_key = pairing_result_next_bracket_local_key(
                players=bracket_players,
                result=bracket_result,
                context=BracketContext(mdp_ids=mdp_ids),
            )
            candidate_solution = _RoundTailSolution(
                pairings=(*current_pairings, *tail_solution.pairings),
                first_result=bracket_result,
                bracket_game_counts=(
                    _paired_game_count(current_pairings),
                    *tail_solution.bracket_game_counts,
                ),
                solution_key=(
                    *tail_solution.solution_key[:2],
                    collapse_size,
                    local_key,
                    *tail_solution.solution_key[2:],
                ),
            )
            if best_key is None or candidate_solution.solution_key < best_key:
                best_key = candidate_solution.solution_key
                best_solution = candidate_solution
            if best_key[:2] == best_possible_bye_key and best_key[2] == 1:
                break

        return best_solution

    solution = solve(scoregroups, ())
    if solution is None:
        raise PairingError("round cannot be fully paired under current absolute constraints")
    return PairingResult(pairings=solution.pairings, unpaired_ids=())


def pair_round_dutch_fast(
    players: tuple[PlayerState, ...],
    *,
    sequential_search_max_players: int | None = None,
) -> PairingResult:
    """Pair one full round with the greedy bracket pipeline only.

    This skips collapse backtracking to keep runtime bounded for synthetic
    workload generation and large stress scenarios.
    `sequential_search_max_players` has the same meaning as in
    `pair_round_dutch`.
    """
    if not players:
        return PairingResult(pairings=(), unpaired_ids=())
    scoregroups = _group_residents_by_score(tuple(sorted(players, key=_player_rank_key)))
    pairings = _pair_round_dutch_greedy(
        scoregroups,
        sequential_search_max_players=sequential_search_max_players,
    )
    if pairings is None:
        raise PairingError("round cannot be fully paired under current absolute constraints")
    return PairingResult(pairings=pairings, unpaired_ids=())
