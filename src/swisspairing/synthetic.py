"""Synthetic Swiss tournament simulation helpers.

This module provides deterministic, seeded simulation utilities for building
benchmark fixtures when production Swiss tournament history is unavailable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

from swisspairing.exceptions import PairingError
from swisspairing.model import Color, FloatKind, Pairing, PlayerState
from swisspairing.tournament import pair_round_dutch

GameResult = Literal["win", "loss", "draw"]
OutcomeKind = Literal["game", "bye", "absent"]


def _new_opponents() -> set[str]:
    return set()


def _new_colors() -> list[Color]:
    return []


def _new_floats() -> list[FloatKind]:
    return []


def _new_round_outcomes() -> list[SyntheticRoundOutcome]:
    return []


@dataclass(frozen=True, slots=True)
class SyntheticConfig:
    """Configuration for one synthetic tournament run."""

    tournament_id: str
    player_count: int
    rounds: int
    win_points: int = 2
    draw_points: int = 1
    loss_points: int = 0
    bye_points: int = 2
    draw_probability: float = 0.18
    draw_scale: float = 600.0
    withdraw_probability: float = 0.0
    rating_mean: float = 1500.0
    rating_stddev: float = 280.0
    rating_min: int = 900
    rating_max: int = 2600


@dataclass(frozen=True, slots=True)
class SyntheticRoundOutcome:
    kind: OutcomeKind
    score_before: int
    score_after: int
    opponent_id: str | None = None
    color: Color | None = None
    result: GameResult | None = None
    float_kind: FloatKind = FloatKind.NONE


@dataclass(slots=True)
class _MutablePlayer:
    player_id: str
    pairing_no: int
    rating: int
    score: int = 0
    opponents: set[str] = field(default_factory=_new_opponents)
    color_history: list[Color] = field(default_factory=_new_colors)
    float_history: list[FloatKind] = field(default_factory=_new_floats)
    had_full_point_bye: bool = False
    had_full_point_unplayed_round: bool = False
    withdrawn: bool = False
    round_outcomes: list[SyntheticRoundOutcome] = field(default_factory=_new_round_outcomes)

    def to_snapshot(self) -> SyntheticPlayerSnapshot:
        return SyntheticPlayerSnapshot(
            player_id=self.player_id,
            pairing_no=self.pairing_no,
            rating=self.rating,
            score=self.score,
            opponents=frozenset(self.opponents),
            color_history=tuple(self.color_history),
            float_history=tuple(self.float_history),
            had_full_point_bye=self.had_full_point_bye,
            had_full_point_unplayed_round=self.had_full_point_unplayed_round,
            withdrawn=self.withdrawn,
            round_outcomes=tuple(self.round_outcomes),
        )


@dataclass(frozen=True, slots=True)
class SyntheticPlayerSnapshot:
    player_id: str
    pairing_no: int
    rating: int
    score: int
    opponents: frozenset[str]
    color_history: tuple[Color, ...]
    float_history: tuple[FloatKind, ...]
    had_full_point_bye: bool
    had_full_point_unplayed_round: bool
    withdrawn: bool
    round_outcomes: tuple[SyntheticRoundOutcome, ...]


@dataclass(frozen=True, slots=True)
class SyntheticTournament:
    tournament_id: str
    planned_rounds: int
    completed_rounds: int
    players: tuple[SyntheticPlayerSnapshot, ...]
    active_before_round: tuple[frozenset[str], ...]
    stop_reason: str | None = None


def generate_players(config: SyntheticConfig, *, rng: random.Random) -> tuple[_MutablePlayer, ...]:
    """Create initial players with rating-seeded pairing numbers."""
    seeded: list[tuple[int, str]] = []
    for index in range(1, config.player_count + 1):
        player_id = f"{config.tournament_id}_p{index:03d}"
        sampled = int(round(rng.gauss(config.rating_mean, config.rating_stddev)))
        rating = max(config.rating_min, min(config.rating_max, sampled))
        seeded.append((rating, player_id))

    seeded.sort(key=lambda item: (-item[0], item[1]))
    players: list[_MutablePlayer] = []
    for pairing_no, (rating, player_id) in enumerate(seeded, start=1):
        players.append(_MutablePlayer(player_id=player_id, pairing_no=pairing_no, rating=rating))
    return tuple(players)


def sample_game_result(
    *,
    white_rating: int,
    black_rating: int,
    draw_probability: float,
    draw_scale: float,
    rng: random.Random,
) -> tuple[GameResult, GameResult]:
    """Sample a game result from ratings with configurable draw rate."""
    expected_white = 1.0 / (1.0 + 10.0 ** ((black_rating - white_rating) / 400.0))
    adjusted_draw = draw_probability * math.exp(-abs(white_rating - black_rating) / draw_scale)
    adjusted_draw = max(0.0, min(0.95, adjusted_draw))

    decisive_mass = max(0.0, 1.0 - adjusted_draw)
    white_win_probability = decisive_mass * expected_white
    black_win_probability = decisive_mass - white_win_probability

    roll = rng.random()
    if roll < adjusted_draw:
        return ("draw", "draw")
    roll -= adjusted_draw
    if roll < white_win_probability:
        return ("win", "loss")
    if roll < white_win_probability + black_win_probability:
        return ("loss", "win")
    return ("draw", "draw")


def simulate_tournament(config: SyntheticConfig, *, rng: random.Random) -> SyntheticTournament:
    """Simulate one Swiss tournament with seeded randomness."""
    if config.player_count < 2:
        raise ValueError("player_count must be at least 2")
    if config.rounds <= 0:
        raise ValueError("rounds must be positive")

    players = generate_players(config, rng=rng)
    by_id = {player.player_id: player for player in players}
    active_before_round: list[frozenset[str]] = [frozenset(player.player_id for player in players)]
    completed_rounds = 0
    stop_reason: str | None = None

    for _round_no in range(1, config.rounds + 1):
        active = tuple(player for player in players if not player.withdrawn)
        if len(active) < 2:
            stop_reason = "insufficient_active_players"
            break

        try:
            pairings = _pair_active_players(active)
        except PairingError:
            stop_reason = "pairing_error"
            break

        pre_round_scores = {player.player_id: player.score for player in active}
        paired_ids: set[str] = set()

        for pairing in pairings:
            white_player = by_id[pairing.white_id]
            if pairing.black_id is None:
                paired_ids.add(white_player.player_id)
                _apply_bye(player=white_player, config=config)
                continue

            black_player = by_id[pairing.black_id]
            paired_ids.add(white_player.player_id)
            paired_ids.add(black_player.player_id)
            _apply_game_result(
                white_player=white_player,
                black_player=black_player,
                config=config,
                rng=rng,
                pre_round_scores=pre_round_scores,
            )

        # If the pairing result leaves unresolved players, mark them absent.
        for player in active:
            if player.player_id in paired_ids:
                continue
            _append_absent_outcome(player)

        for player in players:
            if player.withdrawn:
                _append_absent_outcome(player)

        completed_rounds += 1
        _apply_withdrawals(players=players, probability=config.withdraw_probability, rng=rng)
        active_before_round.append(
            frozenset(player.player_id for player in players if not player.withdrawn)
        )

    snapshots = tuple(player.to_snapshot() for player in players)
    return SyntheticTournament(
        tournament_id=config.tournament_id,
        planned_rounds=config.rounds,
        completed_rounds=completed_rounds,
        players=snapshots,
        active_before_round=tuple(active_before_round),
        stop_reason=stop_reason,
    )


def _pair_active_players(active_players: tuple[_MutablePlayer, ...]) -> tuple[Pairing, ...]:
    states = _build_states_for_pairing(active_players)
    return pair_round_dutch(states).pairings


def _build_states_for_pairing(
    active_players: tuple[_MutablePlayer, ...],
) -> tuple[PlayerState, ...]:
    max_score = max(player.score for player in active_players)
    top_ids = {player.player_id for player in active_players if player.score == max_score}

    states: list[PlayerState] = []
    for player in active_players:
        states.append(
            PlayerState(
                player_id=player.player_id,
                pairing_no=player.pairing_no,
                score=player.score,
                opponents=frozenset(player.opponents),
                forbidden_opponents=frozenset(),
                color_history=tuple(player.color_history),
                unplayed_games=0,
                had_full_point_bye=player.had_full_point_bye,
                had_full_point_unplayed_round=player.had_full_point_unplayed_round,
                is_top_scorer=player.player_id in top_ids,
                is_topscorer_or_opponent=(
                    player.player_id in top_ids or bool(player.opponents & top_ids)
                ),
                float_history=tuple(player.float_history),
            )
        )
    return tuple(states)


def _apply_bye(*, player: _MutablePlayer, config: SyntheticConfig) -> None:
    score_before = player.score
    player.score += config.bye_points
    player.had_full_point_bye = True
    player.float_history.append(FloatKind.NONE)
    player.round_outcomes.append(
        SyntheticRoundOutcome(
            kind="bye",
            score_before=score_before,
            score_after=player.score,
            float_kind=FloatKind.NONE,
        )
    )


def _apply_game_result(
    *,
    white_player: _MutablePlayer,
    black_player: _MutablePlayer,
    config: SyntheticConfig,
    rng: random.Random,
    pre_round_scores: dict[str, int],
) -> None:
    white_outcome, black_outcome = sample_game_result(
        white_rating=white_player.rating,
        black_rating=black_player.rating,
        draw_probability=config.draw_probability,
        draw_scale=config.draw_scale,
        rng=rng,
    )

    white_before = white_player.score
    black_before = black_player.score
    white_player.score += _score_delta(white_outcome, config=config)
    black_player.score += _score_delta(black_outcome, config=config)

    white_player.opponents.add(black_player.player_id)
    black_player.opponents.add(white_player.player_id)
    white_player.color_history.append("white")
    black_player.color_history.append("black")

    white_float = _float_kind(
        player_score_before=pre_round_scores[white_player.player_id],
        opponent_score_before=pre_round_scores[black_player.player_id],
    )
    black_float = _float_kind(
        player_score_before=pre_round_scores[black_player.player_id],
        opponent_score_before=pre_round_scores[white_player.player_id],
    )
    white_player.float_history.append(white_float)
    black_player.float_history.append(black_float)

    white_player.round_outcomes.append(
        SyntheticRoundOutcome(
            kind="game",
            opponent_id=black_player.player_id,
            color="white",
            result=white_outcome,
            score_before=white_before,
            score_after=white_player.score,
            float_kind=white_float,
        )
    )
    black_player.round_outcomes.append(
        SyntheticRoundOutcome(
            kind="game",
            opponent_id=white_player.player_id,
            color="black",
            result=black_outcome,
            score_before=black_before,
            score_after=black_player.score,
            float_kind=black_float,
        )
    )


def _append_absent_outcome(player: _MutablePlayer) -> None:
    player.float_history.append(FloatKind.NONE)
    player.round_outcomes.append(
        SyntheticRoundOutcome(
            kind="absent",
            score_before=player.score,
            score_after=player.score,
            float_kind=FloatKind.NONE,
        )
    )


def _score_delta(result: GameResult, *, config: SyntheticConfig) -> int:
    if result == "win":
        return config.win_points
    if result == "draw":
        return config.draw_points
    return config.loss_points


def _float_kind(*, player_score_before: int, opponent_score_before: int) -> FloatKind:
    if opponent_score_before > player_score_before:
        return FloatKind.UP
    if opponent_score_before < player_score_before:
        return FloatKind.DOWN
    return FloatKind.NONE


def _apply_withdrawals(
    *,
    players: tuple[_MutablePlayer, ...],
    probability: float,
    rng: random.Random,
) -> None:
    if probability <= 0:
        return

    active = [player for player in players if not player.withdrawn]
    if len(active) <= 2:
        return

    remaining = len(active)
    for player in active:
        if remaining <= 2:
            break
        if rng.random() < probability:
            player.withdrawn = True
            remaining -= 1
