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
    bracket_is_feasible_exact,
    build_float_assignments,
    pair_bracket,
    pairing_result_next_bracket_local_key,
)
from swisspairing.exceptions import ExactSearchUnavailableError, PairingError
from swisspairing.model import Color, Pairing, PairingResult, PlayerState


def _player_rank_key(player: PlayerState) -> tuple[int, int]:
    return (-player.score, player.pairing_no)


@dataclass(frozen=True, slots=True)
class _RoundTailSolution:
    """Recursive round solve result with per-bracket game-count summary."""

    pairings: tuple[Pairing, ...]
    first_result: PairingResult | None
    first_players: tuple[PlayerState, ...] | None
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
    eligible_players = tuple(
        player for player in players if not player.is_pairing_allocated_bye_ineligible
    )
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
    initial_color: Color,
    future_key: NextBracketKey | None = None,
) -> NextBracketKey:
    return NextBracketKey(
        local=pairing_result_next_bracket_local_key(
            players=players,
            result=result,
            context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
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
    initial_color: Color,
) -> PairingResult:
    exact_or_explicit_limit = (
        len(players) if sequential_search_max_players is None else sequential_search_max_players
    )
    return pair_bracket(
        players,
        context=context,
        allow_bye=allow_bye,
        sequential_search_max_players=exact_or_explicit_limit,
        initial_color=initial_color,
    )


def pair_round_dutch(
    players: tuple[PlayerState, ...],
    *,
    sequential_search_max_players: int | None = None,
    initial_color: Color = "white",
) -> PairingResult:
    """Pair one full round with deterministic Dutch bracket chaining.

    References:
    - C.04.3 section 1.9.2: pairing proceeds bracket by bracket from top scoregroup.
    - C.04.3 section 3.7: heterogeneous brackets with MDPs.
    - C.04.3 [C8]: current-bracket downfloaters should keep next-bracket outlook viable.
    - C.04.3 sections B.6-B.9: collapse to larger pairing brackets when needed.

    Tuning:
    - `sequential_search_max_players` overrides the bracket-level exact-search
      size cap used by `pair_bracket`; `None` uses the current bracket size.
    """
    if not players:
        return PairingResult(pairings=(), unpaired_ids=(), float_assignments=())

    ordered_players = tuple(sorted(players, key=_player_rank_key))
    scoregroups = _group_residents_by_score(ordered_players)

    @cache
    def solve(
        remaining_groups: tuple[tuple[PlayerState, ...], ...],
        carried_mdps: tuple[PlayerState, ...],
    ) -> _RoundTailSolution | None:
        nonlocal unsupported_found
        if not remaining_groups:
            if carried_mdps:
                return None
            return _RoundTailSolution(
                pairings=(),
                first_result=None,
                first_players=None,
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
                        context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
                        allow_bye=True,
                        sequential_search_max_players=sequential_search_max_players,
                        initial_color=initial_color,
                    )
                except ExactSearchUnavailableError:
                    unsupported_found = True
                    continue
                except PairingError:
                    continue
                if bracket_result.unpaired_ids:
                    continue
                local_key = pairing_result_next_bracket_local_key(
                    players=bracket_players,
                    result=bracket_result,
                    context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
                )
                bye_key = _solution_bye_key(players=bracket_players, result=bracket_result)
                candidate_solution = _RoundTailSolution(
                    pairings=bracket_result.pairings,
                    first_result=bracket_result,
                    first_players=bracket_players,
                    bracket_game_counts=(_paired_game_count(bracket_result.pairings),),
                    solution_key=(*bye_key, collapse_size, local_key),
                )
                if best_key is None or candidate_solution.solution_key < best_key:
                    best_key = candidate_solution.solution_key
                    best_solution = candidate_solution
                if best_key[:2] == best_possible_bye_key and best_key[2] == 1:
                    break
                continue

            next_bracket_result_cache: dict[tuple[PlayerState, ...], PairingResult | None] = {}
            next_bracket_key_cache: dict[tuple[PlayerState, ...], NextBracketKey | None] = {}

            def _pair_immediate_next_bracket(
                downfloaters: tuple[PlayerState, ...],
                *,
                tail_groups_snapshot: tuple[tuple[PlayerState, ...], ...] = tail_groups,
                next_bracket_result_cache_snapshot: dict[
                    tuple[PlayerState, ...], PairingResult | None
                ] = next_bracket_result_cache,
            ) -> PairingResult | None:
                nonlocal unsupported_found
                ordered_downfloaters = tuple(sorted(downfloaters, key=_player_rank_key))
                if ordered_downfloaters in next_bracket_result_cache_snapshot:
                    return next_bracket_result_cache_snapshot[ordered_downfloaters]
                next_residents = tail_groups_snapshot[0]
                next_players = tuple(
                    sorted((*ordered_downfloaters, *next_residents), key=_player_rank_key)
                )
                next_mdp_ids = frozenset(player.player_id for player in ordered_downfloaters)

                next_tail_groups = tail_groups_snapshot[1:]
                next_is_last_bracket = len(next_tail_groups) == 0
                next_next_validator_cache: dict[tuple[PlayerState, ...], bool] = {}

                if next_is_last_bracket:
                    try:
                        next_result = _pair_bracket_with_optional_limit(
                            next_players,
                            context=BracketContext(
                                mdp_ids=next_mdp_ids,
                                initial_color=initial_color,
                            ),
                            allow_bye=True,
                            sequential_search_max_players=sequential_search_max_players,
                            initial_color=initial_color,
                        )
                    except ExactSearchUnavailableError:
                        unsupported_found = True
                        next_bracket_result_cache_snapshot[ordered_downfloaters] = None
                        return None
                    except PairingError:
                        next_bracket_result_cache_snapshot[ordered_downfloaters] = None
                        return None
                    next_bracket_result_cache_snapshot[ordered_downfloaters] = next_result
                    return next_result

                def next_next_validator(next_downfloaters: tuple[PlayerState, ...]) -> bool:
                    ordered_next_downfloaters = tuple(
                        sorted(next_downfloaters, key=_player_rank_key)
                    )
                    if ordered_next_downfloaters in next_next_validator_cache:
                        return next_next_validator_cache[ordered_next_downfloaters]
                    next_next_players = tuple(
                        sorted(
                            (*ordered_next_downfloaters, *next_tail_groups[0]),
                            key=_player_rank_key,
                        )
                    )
                    if len(ordered_next_downfloaters) == 1 and len(next_next_players) % 2 == 1:
                        future_tail_groups = next_tail_groups[1:]
                        next_next_context = BracketContext(
                            mdp_ids=frozenset(
                                player.player_id for player in ordered_next_downfloaters
                            ),
                            initial_color=initial_color,
                        )
                        allow_bye_next = len(future_tail_groups) == 0
                        if not allow_bye_next:

                            def future_validator(
                                future_downfloaters: tuple[PlayerState, ...],
                            ) -> bool:
                                ordered_future_downfloaters = tuple(
                                    sorted(future_downfloaters, key=_player_rank_key)
                                )
                                return (
                                    solve(
                                        future_tail_groups,
                                        ordered_future_downfloaters,
                                    )
                                    is not None
                                )

                            next_next_context = BracketContext(
                                mdp_ids=next_next_context.mdp_ids,
                                initial_color=initial_color,
                                next_bracket_validator=future_validator,
                            )
                        try:
                            result = bracket_is_feasible_exact(
                                next_next_players,
                                context=next_next_context,
                                allow_bye=allow_bye_next,
                                sequential_search_max_players=sequential_search_max_players,
                                initial_color=initial_color,
                            )
                            next_next_validator_cache[ordered_next_downfloaters] = result
                            return result
                        except ExactSearchUnavailableError:
                            next_next_validator_cache[ordered_next_downfloaters] = False
                            return False
                    result = solve(next_tail_groups, ordered_next_downfloaters) is not None
                    next_next_validator_cache[ordered_next_downfloaters] = result
                    return result

                # C.04.3 [C8] compares the immediate next bracket's [C1]-[C7]
                # outlook. Keep deeper brackets inside that next bracket's own
                # exact solve instead of reusing them again as an extra current-
                # bracket tie-break surface.
                try:
                    next_result = _pair_bracket_with_optional_limit(
                        next_players,
                        context=BracketContext(
                            mdp_ids=next_mdp_ids,
                            initial_color=initial_color,
                            next_bracket_validator=next_next_validator,
                        ),
                        allow_bye=False,
                        sequential_search_max_players=sequential_search_max_players,
                        initial_color=initial_color,
                    )
                except ExactSearchUnavailableError:
                    unsupported_found = True
                    next_bracket_result_cache_snapshot[ordered_downfloaters] = None
                    return None
                except PairingError:
                    next_bracket_result_cache_snapshot[ordered_downfloaters] = None
                    return None
                next_bracket_result_cache_snapshot[ordered_downfloaters] = next_result
                return next_result

            def next_bracket_validator(
                downfloaters: tuple[PlayerState, ...],
                *,
                tail_groups_snapshot: tuple[tuple[PlayerState, ...], ...] = tail_groups,
            ) -> bool:
                ordered_downfloaters = tuple(sorted(downfloaters, key=_player_rank_key))
                return (
                    _pair_immediate_next_bracket(
                        ordered_downfloaters,
                        tail_groups_snapshot=tail_groups_snapshot,
                    )
                    is not None
                )

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
                next_players = tuple(
                    sorted((*ordered_downfloaters, *next_residents), key=_player_rank_key)
                )
                next_mdp_ids = frozenset(player.player_id for player in ordered_downfloaters)
                next_result = _pair_immediate_next_bracket(
                    ordered_downfloaters,
                    tail_groups_snapshot=tail_groups_snapshot,
                )
                if next_result is None:
                    next_bracket_key_cache_snapshot[ordered_downfloaters] = None
                    return None
                next_key = _build_next_bracket_key(
                    players=next_players,
                    result=next_result,
                    mdp_ids=next_mdp_ids,
                    initial_color=initial_color,
                )
                next_bracket_key_cache_snapshot[ordered_downfloaters] = next_key
                return next_key

            try:
                bracket_result = _pair_bracket_with_optional_limit(
                    bracket_players,
                    context=BracketContext(
                        mdp_ids=mdp_ids,
                        initial_color=initial_color,
                        next_bracket_validator=next_bracket_validator,
                        next_bracket_key=next_bracket_key,
                    ),
                    allow_bye=False,
                    sequential_search_max_players=sequential_search_max_players,
                    initial_color=initial_color,
                )
            except ExactSearchUnavailableError:
                unsupported_found = True
                continue
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
                context=BracketContext(mdp_ids=mdp_ids, initial_color=initial_color),
            )
            candidate_solution = _RoundTailSolution(
                pairings=(*current_pairings, *tail_solution.pairings),
                first_result=bracket_result,
                first_players=bracket_players,
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

    unsupported_found = False
    solution = solve(scoregroups, ())
    if solution is None:
        if unsupported_found:
            raise PairingError(
                "exact Dutch mode currently requires heuristic fallback for this round"
            )
        raise PairingError("round cannot be fully paired under current absolute constraints")
    return PairingResult(
        pairings=solution.pairings,
        unpaired_ids=(),
        float_assignments=build_float_assignments(
            ordered_players,
            pairings=solution.pairings,
            unpaired_ids=(),
        ),
    )
