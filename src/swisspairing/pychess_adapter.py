"""Adapter helpers for integrating `swisspairing` into pychess tournament code.

The adapter exposes plain, typed conversion steps so pychess can keep its own
state model while delegating Dutch pairing to this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from swisspairing.model import Color, FloatKind, PairingResult, PlayerState
from swisspairing.tournament import pair_round_dutch


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
    initial_color: Color = "white",
) -> PychessPairingPlan:
    """Pair one round from pychess snapshots with the exact Dutch solver."""
    states = build_player_states_from_snapshots(snapshots)
    return pairing_result_to_pychess_plan(pair_round_dutch(states, initial_color=initial_color))


def pair_snapshots_dutch_exact(
    snapshots: tuple[PychessPlayerSnapshot, ...],
    *,
    initial_color: Color = "white",
) -> PychessPairingPlan:
    """Alias for the canonical snapshot-based exact Dutch solver."""
    return pair_snapshots_dutch(snapshots, initial_color=initial_color)


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
