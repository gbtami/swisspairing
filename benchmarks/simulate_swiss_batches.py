# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Generate synthetic Swiss TRF snapshot batches for benchmarking.

This script is intended for environments where production Swiss tournament
history is not available yet.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from py4swiss.trf import ParsedTrf
from py4swiss.trf.codes import PlayerCode
from py4swiss.trf.results import (
    ColorToken,
    ResultToken,
    RoundResult,
    ScoringPointSystem,
    ScoringPointSystemCode,
)
from py4swiss.trf.sections import PlayerSection, XSection
from py4swiss.trf.sections.x_section import XSectionConfiguration

from swisspairing.benchmarking import portable_path_str
from swisspairing.pychess_dump import select_snapshot_completed_rounds
from swisspairing.synthetic import (
    SyntheticConfig,
    SyntheticPlayerSnapshot,
    SyntheticRoundOutcome,
    SyntheticTournament,
    simulate_tournament,
)


def _build_scoring_system(config: SyntheticConfig) -> ScoringPointSystem:
    scoring = ScoringPointSystem()
    scoring.apply_code(ScoringPointSystemCode.WIN, config.win_points * 10)
    scoring.apply_code(ScoringPointSystemCode.DRAW, config.draw_points * 10)
    scoring.apply_code(ScoringPointSystemCode.LOSS, config.loss_points * 10)
    half_bye = (
        config.draw_points * 10 if config.draw_points > 0 else ((config.win_points * 10) // 2)
    )
    scoring.apply_code(ScoringPointSystemCode.ZERO_POINT_BYE, 0)
    scoring.apply_code(ScoringPointSystemCode.HALF_POINT_BYE, half_bye)
    scoring.apply_code(ScoringPointSystemCode.FULL_POINT_BYE, config.bye_points * 10)
    scoring.apply_code(ScoringPointSystemCode.PAIRING_ALLOCATED_BYE, config.bye_points * 10)
    return scoring


def _prefix_score(player: SyntheticPlayerSnapshot, *, completed_rounds: int) -> int:
    if completed_rounds <= 0:
        return 0
    if completed_rounds > len(player.round_outcomes):
        return player.score
    return player.round_outcomes[completed_rounds - 1].score_after


def _build_rank_map(
    players: tuple[SyntheticPlayerSnapshot, ...],
    *,
    completed_rounds: int,
) -> dict[str, int]:
    ordered = sorted(
        players,
        key=lambda player: (
            -_prefix_score(player, completed_rounds=completed_rounds),
            -player.rating,
            player.pairing_no,
            player.player_id,
        ),
    )
    return {player.player_id: index for index, player in enumerate(ordered, start=1)}


def _as_round_result(
    *,
    outcome: SyntheticRoundOutcome,
    ids_by_name: dict[str, int],
) -> RoundResult:
    if outcome.kind == "bye":
        return RoundResult(
            id=0,
            color=ColorToken.BYE_OR_NOT_PAIRED,
            result=ResultToken.PAIRING_ALLOCATED_BYE,
        )

    if outcome.kind == "absent":
        return RoundResult(
            id=0,
            color=ColorToken.BYE_OR_NOT_PAIRED,
            result=ResultToken.ZERO_POINT_BYE,
        )

    if outcome.opponent_id is None or outcome.color is None or outcome.result is None:
        raise ValueError("game outcome must include opponent/color/result")

    result_token: ResultToken
    if outcome.result == "win":
        result_token = ResultToken.WIN
    elif outcome.result == "loss":
        result_token = ResultToken.LOSS
    else:
        result_token = ResultToken.DRAW

    return RoundResult(
        id=ids_by_name[outcome.opponent_id],
        color=ColorToken.WHITE if outcome.color == "white" else ColorToken.BLACK,
        result=result_token,
    )


def _build_trf_snapshot(
    *,
    tournament: SyntheticTournament,
    config: SyntheticConfig,
    completed_rounds: int,
) -> ParsedTrf:
    if completed_rounds <= 0:
        raise ValueError("completed_rounds must be positive")
    if completed_rounds > tournament.completed_rounds:
        raise ValueError("completed_rounds exceeds simulated rounds")

    players = tuple(sorted(tournament.players, key=lambda player: player.pairing_no))
    ids_by_name = {player.player_id: index for index, player in enumerate(players, start=1)}
    scoring = _build_scoring_system(config)
    rank_by_name = _build_rank_map(players, completed_rounds=completed_rounds)

    sections: list[PlayerSection] = []
    for player in players:
        results: list[RoundResult] = []
        for round_index in range(completed_rounds):
            results.append(
                _as_round_result(
                    outcome=player.round_outcomes[round_index],
                    ids_by_name=ids_by_name,
                )
            )

        points_times_ten = sum(
            scoring.score_dict[(result.result, result.color)] for result in results
        )
        sections.append(
            PlayerSection(
                code=PlayerCode.PLAYER,
                starting_number=ids_by_name[player.player_id],
                name=player.player_id,
                fide_rating=player.rating,
                points_times_ten=points_times_ten,
                rank=rank_by_name[player.player_id],
                results=results,
            )
        )

    waiting_ids = (
        tournament.active_before_round[completed_rounds]
        if completed_rounds < len(tournament.active_before_round)
        else frozenset()
    )
    zeroed_ids = {
        ids_by_name[player.player_id] for player in players if player.player_id not in waiting_ids
    }

    x_section = XSection(
        number_of_rounds=max(tournament.planned_rounds, completed_rounds + 1),
        zeroed_ids=zeroed_ids,
        scoring_point_system=scoring,
        configuration=XSectionConfiguration(first_round_color=True, by_rank=False),
    )
    trf = ParsedTrf(player_sections=sections, x_section=x_section)
    trf.validate_contents()
    return trf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260306)
    parser.add_argument("--tournaments", type=int, default=20)
    parser.add_argument("--players-min", type=int, default=32)
    parser.add_argument("--players-max", type=int, default=256)
    parser.add_argument("--rounds-min", type=int, default=5)
    parser.add_argument("--rounds-max", type=int, default=11)
    parser.add_argument("--max-snapshots-per-tournament", type=int, default=3)
    parser.add_argument("--min-completed-rounds", type=int, default=1)
    parser.add_argument("--draw-probability", type=float, default=0.18)
    parser.add_argument("--draw-scale", type=float, default=600.0)
    parser.add_argument("--withdraw-probability", type=float, default=0.0)
    parser.add_argument("--rating-mean", type=float, default=1500.0)
    parser.add_argument("--rating-stddev", type=float, default=280.0)
    parser.add_argument("--rating-min", type=int, default=900)
    parser.add_argument("--rating-max", type=int, default=2600)
    parser.add_argument("--metadata-json", type=Path)
    parser.add_argument("--fail-on-empty", action="store_true")
    args = parser.parse_args()

    if args.players_min < 2:
        raise SystemExit("--players-min must be >= 2")
    if args.players_max < args.players_min:
        raise SystemExit("--players-max must be >= --players-min")
    if args.rounds_min <= 0:
        raise SystemExit("--rounds-min must be > 0")
    if args.rounds_max < args.rounds_min:
        raise SystemExit("--rounds-max must be >= --rounds-min")

    rng = random.Random(args.seed)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    exported_paths: list[str] = []
    exported_tournaments = 0
    skipped: list[dict[str, Any]] = []
    metadata_tournaments: list[dict[str, Any]] = []

    for tournament_index in range(1, args.tournaments + 1):
        tournament_id = f"sim{tournament_index:04d}"
        player_count = rng.randint(args.players_min, args.players_max)
        rounds = rng.randint(args.rounds_min, args.rounds_max)
        config = SyntheticConfig(
            tournament_id=tournament_id,
            player_count=player_count,
            rounds=rounds,
            draw_probability=args.draw_probability,
            draw_scale=args.draw_scale,
            withdraw_probability=args.withdraw_probability,
            rating_mean=args.rating_mean,
            rating_stddev=args.rating_stddev,
            rating_min=args.rating_min,
            rating_max=args.rating_max,
        )

        tournament = simulate_tournament(config, rng=rng)
        snapshots = select_snapshot_completed_rounds(
            tournament.completed_rounds,
            max_snapshots=args.max_snapshots_per_tournament,
            min_completed_rounds=args.min_completed_rounds,
        )
        if not snapshots:
            skipped.append(
                {
                    "tid": tournament_id,
                    "reason": "no_snapshot_rounds",
                    "completed_rounds": tournament.completed_rounds,
                    "stop_reason": tournament.stop_reason,
                }
            )
            continue

        written_for_tournament = 0
        for completed_rounds in snapshots:
            try:
                trf = _build_trf_snapshot(
                    tournament=tournament,
                    config=config,
                    completed_rounds=completed_rounds,
                )
            except Exception as exc:
                skipped.append(
                    {
                        "tid": tournament_id,
                        "reason": "snapshot_error",
                        "completed_rounds": completed_rounds,
                        "error": str(exc),
                    }
                )
                continue

            output_path = output_dir / f"{tournament_id}_r{completed_rounds + 1:02d}.trf"
            trf.write_to_file(output_path)
            exported_paths.append(portable_path_str(output_path))
            written_for_tournament += 1

        metadata_tournaments.append(
            {
                "tid": tournament_id,
                "players": player_count,
                "planned_rounds": rounds,
                "completed_rounds": tournament.completed_rounds,
                "stop_reason": tournament.stop_reason,
                "snapshots_written": written_for_tournament,
            }
        )
        if written_for_tournament > 0:
            exported_tournaments += 1

    summary = {
        "seed": args.seed,
        "requested_tournaments": args.tournaments,
        "exported_tournaments": exported_tournaments,
        "exported_files": len(exported_paths),
        "output_dir": portable_path_str(output_dir),
        "skipped": len(skipped),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    if skipped:
        print("Skipped examples:")
        for item in skipped[:20]:
            print(json.dumps(item, sort_keys=True))

    if args.metadata_json is not None:
        payload = {
            "summary": summary,
            "tournaments": metadata_tournaments,
            "exported_paths": exported_paths,
            "skipped": skipped,
        }
        args.metadata_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.metadata_json}")

    if args.fail_on_empty and not exported_paths:
        raise SystemExit("no TRF files generated")


if __name__ == "__main__":
    main()
