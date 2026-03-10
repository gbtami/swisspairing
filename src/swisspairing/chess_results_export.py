# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Helpers for exporting Chess-Results XLSX downloads into TRF snapshots."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

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
from swisspairing.chess_results import (
    ChessResultsSnapshot,
    build_chess_results_snapshot,
    load_chess_results_tournament,
    published_pairings_for_round,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def export_chess_results_trf_snapshots(
    *,
    starting_list_path: Path,
    round_paths: Sequence[Path],
    output_root: Path,
    event_slug: str | None = None,
) -> dict[str, object]:
    tournament = load_chess_results_tournament(
        starting_list_path=starting_list_path,
        round_paths=round_paths,
    )

    resolved_event_slug = event_slug or slugify_chess_results_event_name(tournament.name)
    output_dir = output_root.resolve() / resolved_event_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    rounds_manifest: list[dict[str, object]] = []
    written_files: list[Path] = []

    for round_record in tournament.rounds:
        snapshot = build_chess_results_snapshot(
            tournament,
            target_round_number=round_record.round_number,
        )
        trf = _snapshot_to_trf(snapshot)
        output_path = output_dir / f"{resolved_event_slug}_r{round_record.round_number:02d}.trf"
        trf.write_to_file(output_path)
        written_files.append(output_path)
        rounds_manifest.append(
            {
                "round_number": round_record.round_number,
                "label": round_record.label,
                "trf": output_path.name,
                "published_pairings": [
                    [left, right] for left, right in published_pairings_for_round(round_record)
                ],
            }
        )

    manifest_path = _write_manifest(
        output_dir=output_dir,
        tournament_name=tournament.name,
        last_update=tournament.last_update,
        first_round_color_white1=tournament.first_round_color_white1,
        source_files=(starting_list_path, *round_paths),
        rounds=rounds_manifest,
    )

    return {
        "event_slug": resolved_event_slug,
        "tournament_name": tournament.name,
        "players": len(tournament.players),
        "rounds": len(tournament.rounds),
        "output_dir": portable_path_str(output_dir),
        "written_trf_files": len(written_files),
        "manifest": portable_path_str(manifest_path),
    }


def slugify_chess_results_event_name(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    return lowered.strip("_") or "chess_results_event"


def discover_chess_results_round_exports(starting_list_path: Path) -> tuple[Path, ...]:
    stem = starting_list_path.stem
    directory = starting_list_path.parent
    pattern = re.compile(rf"^{re.escape(stem)}\((\d+)\)\.xlsx$")
    indexed: list[tuple[int, Path]] = []
    for candidate in directory.iterdir():
        if not candidate.is_file():
            continue
        match = pattern.match(candidate.name)
        if match is None:
            continue
        indexed.append((int(match.group(1)), candidate))
    return tuple(path for _, path in sorted(indexed))


def _standard_scoring_system() -> ScoringPointSystem:
    scoring = ScoringPointSystem()
    scoring.apply_code(ScoringPointSystemCode.WIN, 10)
    scoring.apply_code(ScoringPointSystemCode.DRAW, 5)
    scoring.apply_code(ScoringPointSystemCode.LOSS, 0)
    scoring.apply_code(ScoringPointSystemCode.ZERO_POINT_BYE, 0)
    scoring.apply_code(ScoringPointSystemCode.HALF_POINT_BYE, 5)
    scoring.apply_code(ScoringPointSystemCode.FULL_POINT_BYE, 10)
    scoring.apply_code(ScoringPointSystemCode.PAIRING_ALLOCATED_BYE, 10)
    return scoring


def _to_round_result(result: str, color: str, opponent_starting_number: int) -> RoundResult:
    return RoundResult(
        id=opponent_starting_number,
        color=ColorToken(color),
        result=ResultToken(result),
    )


def _snapshot_to_trf(snapshot: ChessResultsSnapshot) -> ParsedTrf:
    sections = [
        PlayerSection(
            code=PlayerCode.PLAYER,
            starting_number=player.player.starting_number,
            name=player.player.name,
            fide_rating=player.player.rating,
            points_times_ten=player.points_times_ten,
            rank=player.rank,
            results=[
                _to_round_result(
                    result=result.result,
                    color=result.color,
                    opponent_starting_number=result.opponent_starting_number,
                )
                for result in player.results
            ],
        )
        for player in snapshot.players
    ]
    trf = ParsedTrf(
        player_sections=sections,
        x_section=XSection(
            number_of_rounds=snapshot.target_round_number,
            zeroed_ids=set(),
            scoring_point_system=_standard_scoring_system(),
            configuration=XSectionConfiguration(
                first_round_color=snapshot.first_round_color_white1,
                by_rank=False,
            ),
        ),
    )
    trf.validate_contents()
    return trf


def _write_manifest(
    *,
    output_dir: Path,
    tournament_name: str,
    last_update: str,
    first_round_color_white1: bool,
    source_files: tuple[Path, ...],
    rounds: list[dict[str, object]],
) -> Path:
    manifest_path = output_dir / "published_pairings.json"
    payload = {
        "tournament_name": tournament_name,
        "last_update": last_update,
        "first_round_color": "white1" if first_round_color_white1 else "black1",
        "source_files": [path.name for path in source_files],
        "rounds": rounds,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path
