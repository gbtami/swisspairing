# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Export pychess tournament dump snapshots into TRF benchmark cases.

Input files are newline-delimited JSON dumps from pychess collections:
- `tournament.json`
- `tournament_player.json`
- `tournament_pairing.json`
"""

from __future__ import annotations

import argparse
import json
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
from swisspairing.pychess_dump import (
    PychessTournamentPairingRecord,
    PychessTournamentPlayerRecord,
    PychessTournamentRecord,
    group_pairings_by_round,
    infer_scoring_values,
    is_pairing_bye,
    load_ndjson_records,
    parse_tournament_pairing_records,
    parse_tournament_player_records,
    parse_tournament_records,
    point_entry_at,
    result_outcome_for_color,
    select_snapshot_completed_rounds,
)


def _build_scoring_system(
    *,
    win_points: int,
    draw_points: int,
    loss_points: int,
) -> ScoringPointSystem:
    scoring = ScoringPointSystem()
    scoring.apply_code(ScoringPointSystemCode.WIN, win_points * 10)
    scoring.apply_code(ScoringPointSystemCode.DRAW, draw_points * 10)
    scoring.apply_code(ScoringPointSystemCode.LOSS, loss_points * 10)
    half_bye = draw_points * 10 if draw_points > 0 else ((win_points * 10) // 2)
    scoring.apply_code(ScoringPointSystemCode.ZERO_POINT_BYE, 0)
    scoring.apply_code(ScoringPointSystemCode.HALF_POINT_BYE, half_bye)
    scoring.apply_code(ScoringPointSystemCode.FULL_POINT_BYE, win_points * 10)
    scoring.apply_code(ScoringPointSystemCode.PAIRING_ALLOCATED_BYE, win_points * 10)
    return scoring


def _seed_player_ids(
    players: tuple[PychessTournamentPlayerRecord, ...],
) -> dict[str, int]:
    ordered = sorted(players, key=lambda player: (-player.rating, player.username))
    return {player.username: index for index, player in enumerate(ordered, start=1)}


def _prefix_points(
    player: PychessTournamentPlayerRecord,
    *,
    completed_rounds: int,
    bye_points: int,
) -> int:
    total = 0
    for round_index in range(completed_rounds):
        point_entry = point_entry_at(player, round_index)
        if point_entry is None:
            continue
        if is_pairing_bye(point_entry):
            total += bye_points
            continue
        if isinstance(point_entry, int):
            total += point_entry
            continue
        if isinstance(point_entry, tuple) and point_entry and isinstance(point_entry[0], int):
            total += point_entry[0]
    return total


def _build_rank_map(
    *,
    players: tuple[PychessTournamentPlayerRecord, ...],
    completed_rounds: int,
    bye_points: int,
) -> dict[str, int]:
    ordered = sorted(
        players,
        key=lambda player: (
            -_prefix_points(player, completed_rounds=completed_rounds, bye_points=bye_points),
            -player.rating,
            player.username,
        ),
    )
    return {player.username: index for index, player in enumerate(ordered, start=1)}


def _build_round_lookup(
    rounds: tuple[tuple[PychessTournamentPairingRecord, ...], ...],
) -> tuple[dict[str, tuple[str, bool, str]], ...]:
    lookup: list[dict[str, tuple[str, bool, str]]] = []
    for round_pairings in rounds:
        round_map: dict[str, tuple[str, bool, str]] = {}
        for pairing in round_pairings:
            round_map[pairing.white_username] = (
                pairing.black_username,
                True,
                pairing.result_code,
            )
            round_map[pairing.black_username] = (
                pairing.white_username,
                False,
                pairing.result_code,
            )
        lookup.append(round_map)
    return tuple(lookup)


def _result_token(result_code: str, *, is_white: bool) -> ResultToken:
    outcome = result_outcome_for_color(result_code, is_white=is_white)
    if outcome == "win":
        return ResultToken.WIN
    if outcome == "loss":
        return ResultToken.LOSS
    if outcome == "draw":
        return ResultToken.DRAW
    raise ValueError(f"unsupported result code {result_code!r}")


def _build_player_results(
    *,
    player: PychessTournamentPlayerRecord,
    ids_by_name: dict[str, int],
    completed_rounds: int,
    round_lookup: tuple[dict[str, tuple[str, bool, str]], ...],
) -> list[RoundResult]:
    results: list[RoundResult] = []
    for round_index in range(completed_rounds):
        seat = round_lookup[round_index].get(player.username)
        if seat is None:
            point_entry = point_entry_at(player, round_index)
            bye_token = (
                ResultToken.PAIRING_ALLOCATED_BYE
                if is_pairing_bye(point_entry)
                else ResultToken.ZERO_POINT_BYE
            )
            results.append(
                RoundResult(
                    id=0,
                    color=ColorToken.BYE_OR_NOT_PAIRED,
                    result=bye_token,
                )
            )
            continue

        opponent_name, is_white, result_code = seat
        results.append(
            RoundResult(
                id=ids_by_name[opponent_name],
                color=ColorToken.WHITE if is_white else ColorToken.BLACK,
                result=_result_token(result_code, is_white=is_white),
            )
        )
    return results


def _points_times_ten(results: list[RoundResult], scoring: ScoringPointSystem) -> int:
    total = 0
    for result in results:
        total += scoring.score_dict[(result.result, result.color)]
    return total


def _build_trf_snapshot(
    *,
    tournament: PychessTournamentRecord,
    players: tuple[PychessTournamentPlayerRecord, ...],
    rounds: tuple[tuple[PychessTournamentPairingRecord, ...], ...],
    completed_rounds: int,
) -> ParsedTrf:
    if completed_rounds <= 0:
        raise ValueError("completed_rounds must be positive")
    if completed_rounds > len(rounds):
        raise ValueError("completed_rounds exceeds available rounds")

    ids_by_name = _seed_player_ids(players)
    players_by_name = {player.username: player for player in players}
    win_points, draw_points, loss_points = infer_scoring_values(rounds, players_by_name)
    scoring = _build_scoring_system(
        win_points=win_points,
        draw_points=draw_points,
        loss_points=loss_points,
    )
    rank_by_name = _build_rank_map(
        players=players,
        completed_rounds=completed_rounds,
        bye_points=max(0, win_points),
    )
    round_lookup = _build_round_lookup(rounds)

    sections: list[PlayerSection] = []
    for player in sorted(players, key=lambda item: ids_by_name[item.username]):
        results = _build_player_results(
            player=player,
            ids_by_name=ids_by_name,
            completed_rounds=completed_rounds,
            round_lookup=round_lookup,
        )
        sections.append(
            PlayerSection(
                code=PlayerCode.PLAYER,
                starting_number=ids_by_name[player.username],
                name=player.username,
                fide_rating=player.rating,
                points_times_ten=_points_times_ten(results, scoring),
                rank=rank_by_name[player.username],
                results=results,
            )
        )

    x_section = XSection(
        number_of_rounds=max(tournament.rounds, completed_rounds + 1),
        zeroed_ids=set(),
        scoring_point_system=scoring,
        configuration=XSectionConfiguration(first_round_color=True, by_rank=False),
    )
    trf = ParsedTrf(player_sections=sections, x_section=x_section)
    trf.validate_contents()
    return trf


def _index_players(
    players: tuple[PychessTournamentPlayerRecord, ...],
) -> dict[str, tuple[PychessTournamentPlayerRecord, ...]]:
    indexed: dict[str, list[PychessTournamentPlayerRecord]] = {}
    for player in players:
        indexed.setdefault(player.tournament_id, []).append(player)
    return {key: tuple(value) for key, value in indexed.items()}


def _index_pairings(
    pairings: tuple[PychessTournamentPairingRecord, ...],
) -> dict[str, tuple[PychessTournamentPairingRecord, ...]]:
    indexed: dict[str, list[PychessTournamentPairingRecord]] = {}
    for pairing in pairings:
        indexed.setdefault(pairing.tournament_id, []).append(pairing)
    return {key: tuple(value) for key, value in indexed.items()}


def _write_snapshot(
    *,
    output_dir: Path,
    tournament_id: str,
    completed_rounds: int,
    trf: ParsedTrf,
) -> Path:
    output_path = output_dir / f"{tournament_id}_r{completed_rounds + 1:02d}.trf"
    trf.write_to_file(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("."),
        help="Directory containing tournament*.json ndjson dumps.",
    )
    parser.add_argument("--tournament-file", type=Path)
    parser.add_argument("--tournament-player-file", type=Path)
    parser.add_argument("--tournament-pairing-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--system", type=int, default=2, help="Tournament system code to export.")
    parser.add_argument("--tournament-id", action="append", default=[])
    parser.add_argument("--min-players", type=int, default=8)
    parser.add_argument("--min-completed-rounds", type=int, default=1)
    parser.add_argument("--max-snapshots-per-tournament", type=int, default=3)
    parser.add_argument("--max-tournaments", type=int, default=50)
    parser.add_argument("--fail-on-empty", action="store_true")
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    tournament_file = (
        args.tournament_file.resolve()
        if args.tournament_file is not None
        else source_root / "tournament.json"
    )
    tournament_player_file = (
        args.tournament_player_file.resolve()
        if args.tournament_player_file is not None
        else source_root / "tournament_player.json"
    )
    tournament_pairing_file = (
        args.tournament_pairing_file.resolve()
        if args.tournament_pairing_file is not None
        else source_root / "tournament_pairing.json"
    )

    tournaments = parse_tournament_records(load_ndjson_records(tournament_file))
    players = parse_tournament_player_records(load_ndjson_records(tournament_player_file))
    pairings = parse_tournament_pairing_records(load_ndjson_records(tournament_pairing_file))

    players_by_tournament = _index_players(players)
    pairings_by_tournament = _index_pairings(pairings)
    requested_ids = set(args.tournament_id)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    matching_system = [t for t in tournaments if t.system == args.system]

    exported_files: list[Path] = []
    skipped: list[dict[str, Any]] = []
    exported_tournaments = 0

    for tournament in sorted(tournaments, key=lambda item: item.tournament_id):
        if tournament.system != args.system:
            continue
        if requested_ids and tournament.tournament_id not in requested_ids:
            continue
        if exported_tournaments >= args.max_tournaments:
            break

        tournament_players = players_by_tournament.get(tournament.tournament_id, ())
        if len(tournament_players) < args.min_players:
            skipped.append(
                {
                    "tid": tournament.tournament_id,
                    "reason": "min_players",
                    "players": len(tournament_players),
                }
            )
            continue

        tournament_pairings = pairings_by_tournament.get(tournament.tournament_id, ())
        if not tournament_pairings:
            skipped.append({"tid": tournament.tournament_id, "reason": "no_pairings"})
            continue

        rounds = group_pairings_by_round(tournament_pairings)
        completed_rounds_to_export = select_snapshot_completed_rounds(
            len(rounds),
            max_snapshots=args.max_snapshots_per_tournament,
            min_completed_rounds=args.min_completed_rounds,
        )
        if not completed_rounds_to_export:
            skipped.append(
                {
                    "tid": tournament.tournament_id,
                    "reason": "no_snapshot_rounds",
                    "rounds": len(rounds),
                }
            )
            continue

        written_for_tournament = 0
        for completed_rounds in completed_rounds_to_export:
            try:
                trf = _build_trf_snapshot(
                    tournament=tournament,
                    players=tournament_players,
                    rounds=rounds,
                    completed_rounds=completed_rounds,
                )
                written = _write_snapshot(
                    output_dir=output_dir,
                    tournament_id=tournament.tournament_id,
                    completed_rounds=completed_rounds,
                    trf=trf,
                )
                exported_files.append(written)
                written_for_tournament += 1
            except Exception as exc:
                skipped.append(
                    {
                        "tid": tournament.tournament_id,
                        "reason": "snapshot_error",
                        "completed_rounds": completed_rounds,
                        "error": str(exc),
                    }
                )

        if written_for_tournament > 0:
            exported_tournaments += 1

    summary = {
        "source_root": portable_path_str(source_root),
        "tournament_file": portable_path_str(tournament_file),
        "tournament_player_file": portable_path_str(tournament_player_file),
        "tournament_pairing_file": portable_path_str(tournament_pairing_file),
        "requested_system": args.system,
        "tournaments_total": len(tournaments),
        "tournaments_matching_system": len(matching_system),
        "exported_files": len(exported_files),
        "exported_tournaments": exported_tournaments,
        "skipped": len(skipped),
        "output_dir": portable_path_str(output_dir),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    if skipped:
        print("Skipped examples:")
        for item in skipped[:20]:
            print(json.dumps(item, sort_keys=True))

    if args.fail_on_empty and not exported_files:
        raise SystemExit("no TRF snapshots were exported")


if __name__ == "__main__":
    main()
