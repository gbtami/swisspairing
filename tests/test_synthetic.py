from __future__ import annotations

import random

from swisspairing.synthetic import (
    SyntheticConfig,
    generate_players,
    sample_game_result,
    simulate_tournament,
)


def test_generate_players_assigns_sorted_pairing_numbers() -> None:
    config = SyntheticConfig(tournament_id="sim", player_count=16, rounds=5)
    players = generate_players(config, rng=random.Random(7))

    assert len(players) == 16
    assert [player.pairing_no for player in players] == list(range(1, 17))
    ratings = [player.rating for player in players]
    assert ratings == sorted(ratings, reverse=True)


def test_sample_game_result_with_zero_draw_probability_never_draws() -> None:
    rng = random.Random(11)
    outcomes = [
        sample_game_result(
            white_rating=1500,
            black_rating=1500,
            draw_probability=0.0,
            draw_scale=600.0,
            rng=rng,
        )
        for _ in range(200)
    ]
    assert all(
        white_result != "draw" and black_result != "draw" for white_result, black_result in outcomes
    )


def test_sample_game_result_favors_higher_rated_player() -> None:
    rng = random.Random(19)
    white_wins = 0
    black_wins = 0
    for _ in range(1200):
        white_result, black_result = sample_game_result(
            white_rating=2100,
            black_rating=1700,
            draw_probability=0.18,
            draw_scale=600.0,
            rng=rng,
        )
        if white_result == "win":
            white_wins += 1
        if black_result == "win":
            black_wins += 1
    assert white_wins > black_wins


def test_simulate_tournament_is_seed_deterministic() -> None:
    config = SyntheticConfig(
        tournament_id="simdet",
        player_count=12,
        rounds=4,
        draw_probability=0.2,
        withdraw_probability=0.03,
    )
    tournament_one = simulate_tournament(config, rng=random.Random(1234))
    tournament_two = simulate_tournament(config, rng=random.Random(1234))

    signature_one = tuple(
        (
            player.player_id,
            player.score,
            player.withdrawn,
            tuple(
                (
                    outcome.kind,
                    outcome.opponent_id,
                    outcome.color,
                    outcome.result,
                    outcome.score_after,
                )
                for outcome in player.round_outcomes
            ),
        )
        for player in tournament_one.players
    )
    signature_two = tuple(
        (
            player.player_id,
            player.score,
            player.withdrawn,
            tuple(
                (
                    outcome.kind,
                    outcome.opponent_id,
                    outcome.color,
                    outcome.result,
                    outcome.score_after,
                )
                for outcome in player.round_outcomes
            ),
        )
        for player in tournament_two.players
    )
    assert signature_one == signature_two


def test_simulate_tournament_round_lengths_match_completed_rounds() -> None:
    config = SyntheticConfig(tournament_id="simlen", player_count=12, rounds=3)
    tournament = simulate_tournament(config, rng=random.Random(88))

    assert tournament.completed_rounds > 0
    assert len(tournament.active_before_round) == tournament.completed_rounds + 1
    assert all(
        len(player.round_outcomes) == tournament.completed_rounds for player in tournament.players
    )


def test_simulate_tournament_withdraw_probability_can_reduce_field() -> None:
    config = SyntheticConfig(
        tournament_id="simwd",
        player_count=10,
        rounds=3,
        withdraw_probability=1.0,
    )
    tournament = simulate_tournament(config, rng=random.Random(42))
    withdrawn_count = sum(1 for player in tournament.players if player.withdrawn)
    assert withdrawn_count >= 4
