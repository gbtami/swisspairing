"""Adapter helpers for integrating `swisspairing` into pychess tournament code.

The adapter exposes plain, typed conversion steps so pychess can keep its own
state model while delegating Dutch pairing to this package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from swisspairing.model import Color, FloatKind, PairingResult, PlayerState
from swisspairing.tournament import pair_round_dutch, pair_round_dutch_exact

_PAIRING_MODE_ENV = "SWISSPAIRING_PAIRING_MODE"
_SEQUENTIAL_SEARCH_MAX_PLAYERS_ENV = "SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS"
_PAIRING_MODE_FAST = "fast"
_PAIRING_MODE_STRICT = "strict"
_PAIRING_MODE_EXACT = "exact"
_DEFAULT_FAST_SEQUENTIAL_SEARCH_MAX_PLAYERS = 6


@dataclass(frozen=True, slots=True)
class PychessPlayerSnapshot:
    """Pairing input snapshot for one waiting pychess participant."""

    username: str
    pairing_no: int
    score: int
    opponents: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    forbidden_opponents: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    color_history: tuple[Color, ...] = ()
    unplayed_games: int = 0
    had_full_point_bye: bool = False
    had_full_point_unplayed_round: bool = False
    is_top_scorer: bool = False
    is_topscorer_or_opponent: bool | None = None
    float_history: tuple[FloatKind, ...] = ()


@dataclass(frozen=True, slots=True)
class PychessPairingPlan:
    """Pairing output in pychess-friendly identifiers."""

    pairings: tuple[tuple[str, str], ...]
    bye_usernames: tuple[str, ...]


class _UsernameCarrier(Protocol):
    @property
    def username(self) -> str: ...


def _sequential_search_limit_from_env() -> int | None:
    """Read optional sequence-depth override from environment.

    This controls how many players a bracket may have before exact article-4
    sequence search is skipped in favor of faster matching fallback.
    """
    raw = os.getenv(_SEQUENTIAL_SEARCH_MAX_PLAYERS_ENV)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{_SEQUENTIAL_SEARCH_MAX_PLAYERS_ENV} must be an integer; got {raw!r}"
        ) from exc
    if value < 0:
        raise ValueError(f"{_SEQUENTIAL_SEARCH_MAX_PLAYERS_ENV} must be >= 0; got {value}")
    return value


def _pairing_mode_from_env() -> str:
    """Read optional pairing-mode override from environment.

    Accepted values:
    - `fast` (default): bounded sequence-search cap for practical runtime.
    - `strict`: keep full sequence-search behavior.
    - `exact`: use the explicit heuristic-free Dutch solver.
    """
    raw = os.getenv(_PAIRING_MODE_ENV)
    if raw is None or not raw.strip():
        return _PAIRING_MODE_FAST

    mode = raw.strip().lower()
    if mode not in (_PAIRING_MODE_FAST, _PAIRING_MODE_STRICT, _PAIRING_MODE_EXACT):
        raise ValueError(
            f"{_PAIRING_MODE_ENV} must be '{_PAIRING_MODE_FAST}', "
            f"'{_PAIRING_MODE_STRICT}', or '{_PAIRING_MODE_EXACT}'; got {raw!r}"
        )
    return mode


def _effective_sequential_search_limit(
    explicit_limit: int | None,
) -> int | None:
    """Resolve sequence-search cap with explicit/env/mode precedence.

    Precedence:
    1. explicit function argument,
    2. `SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS`,
    3. `SWISSPAIRING_PAIRING_MODE`
       (`fast` default -> cap=6, `strict` / `exact` -> `None`).
    """
    if explicit_limit is not None:
        return explicit_limit

    env_limit = _sequential_search_limit_from_env()
    if env_limit is not None:
        return env_limit

    if _pairing_mode_from_env() in (_PAIRING_MODE_STRICT, _PAIRING_MODE_EXACT):
        return None
    return _DEFAULT_FAST_SEQUENTIAL_SEARCH_MAX_PLAYERS


def _ensure_unique_snapshots(snapshots: tuple[PychessPlayerSnapshot, ...]) -> None:
    usernames = [snapshot.username for snapshot in snapshots]
    if len(set(usernames)) != len(usernames):
        raise ValueError("snapshot usernames must be unique")

    pairing_numbers = [snapshot.pairing_no for snapshot in snapshots]
    if len(set(pairing_numbers)) != len(pairing_numbers):
        raise ValueError("snapshot pairing numbers must be unique")


def build_player_states_from_snapshots(
    snapshots: tuple[PychessPlayerSnapshot, ...],
) -> tuple[PlayerState, ...]:
    """Convert pychess snapshots into `PlayerState` values.

    Reference:
    - C.04.3 section 1.8: criteria [C10]-[C11] apply to topscorers and their
      opponents, so this helper can derive that marker when omitted.
    """
    _ensure_unique_snapshots(snapshots)
    top_ids = {snapshot.username for snapshot in snapshots if snapshot.is_top_scorer}
    states: list[PlayerState] = []

    for snapshot in snapshots:
        topscorer_or_opponent = snapshot.is_topscorer_or_opponent
        if topscorer_or_opponent is None:
            topscorer_or_opponent = snapshot.is_top_scorer or bool(snapshot.opponents & top_ids)

        states.append(
            PlayerState(
                player_id=snapshot.username,
                pairing_no=snapshot.pairing_no,
                score=snapshot.score,
                opponents=snapshot.opponents,
                forbidden_opponents=snapshot.forbidden_opponents,
                color_history=snapshot.color_history,
                unplayed_games=snapshot.unplayed_games,
                had_full_point_bye=snapshot.had_full_point_bye,
                had_full_point_unplayed_round=snapshot.had_full_point_unplayed_round,
                is_top_scorer=snapshot.is_top_scorer,
                is_topscorer_or_opponent=topscorer_or_opponent,
                float_history=snapshot.float_history,
            )
        )

    return tuple(states)


def pairing_result_to_pychess_plan(result: PairingResult) -> PychessPairingPlan:
    """Convert `PairingResult` into username pairings and byes."""
    pairings: list[tuple[str, str]] = []
    byes: list[str] = []

    for pairing in result.pairings:
        if pairing.black_id is None:
            byes.append(pairing.white_id)
            continue
        pairings.append((pairing.white_id, pairing.black_id))

    return PychessPairingPlan(
        pairings=tuple(pairings),
        bye_usernames=tuple(byes),
    )


def pair_snapshots_dutch(
    snapshots: tuple[PychessPlayerSnapshot, ...],
    *,
    sequential_search_max_players: int | None = None,
    initial_color: Color = "white",
) -> PychessPairingPlan:
    """Pair one round from pychess snapshots using Dutch round pairing.

    Runtime tuning:
    - `sequential_search_max_players` sets the max bracket size that still uses
      exact article-4 sequence search.
    - When omitted, precedence is:
      1) `SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS`,
      2) `SWISSPAIRING_PAIRING_MODE`
         (`fast` default -> cap 6, `strict` -> no cap, `exact` -> exact solver).
    - Lower values usually improve speed for pathological states but can reduce
      strict parity with exhaustive sequence ordering in edge cases.
    """
    states = build_player_states_from_snapshots(snapshots)
    limit = _effective_sequential_search_limit(sequential_search_max_players)
    if _pairing_mode_from_env() == _PAIRING_MODE_EXACT:
        return pairing_result_to_pychess_plan(
            pair_round_dutch_exact(
                states,
                sequential_search_max_players=limit,
                initial_color=initial_color,
            )
        )
    return pairing_result_to_pychess_plan(
        pair_round_dutch(
            states,
            sequential_search_max_players=limit,
            initial_color=initial_color,
        )
    )


def pair_snapshots_dutch_exact(
    snapshots: tuple[PychessPlayerSnapshot, ...],
    *,
    sequential_search_max_players: int | None = None,
    initial_color: Color = "white",
) -> PychessPairingPlan:
    """Pair one round from pychess snapshots using the explicit exact solver."""
    states = build_player_states_from_snapshots(snapshots)
    return pairing_result_to_pychess_plan(
        pair_round_dutch_exact(
            states,
            sequential_search_max_players=sequential_search_max_players,
            initial_color=initial_color,
        )
    )


def map_plan_to_users[UserT: _UsernameCarrier](
    plan: PychessPairingPlan,
    users: tuple[UserT, ...],
) -> tuple[tuple[tuple[UserT, UserT], ...], tuple[UserT, ...]]:
    """Map username-based plan entries back to user instances."""
    users_by_name = {user.username: user for user in users}
    if len(users_by_name) != len(users):
        raise ValueError("users must have unique usernames")

    user_pairings: list[tuple[UserT, UserT]] = []
    for white_name, black_name in plan.pairings:
        white_user = users_by_name.get(white_name)
        black_user = users_by_name.get(black_name)
        if white_user is None or black_user is None:
            raise ValueError("pairing plan references unknown username")
        user_pairings.append((white_user, black_user))

    bye_users: list[UserT] = []
    for bye_name in plan.bye_usernames:
        bye_user = users_by_name.get(bye_name)
        if bye_user is None:
            raise ValueError("pairing plan references unknown bye username")
        bye_users.append(bye_user)

    return tuple(user_pairings), tuple(bye_users)
