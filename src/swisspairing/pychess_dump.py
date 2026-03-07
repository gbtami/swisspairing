"""Utilities for processing pychess tournament dump records.

These helpers intentionally avoid direct py4swiss dependencies so they can be
unit-tested in this package without requiring external engines.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

PointEntry = int | str | tuple[object, ...]


@dataclass(frozen=True, slots=True)
class PychessTournamentRecord:
    tournament_id: str
    system: int
    rounds: int
    name: str


@dataclass(frozen=True, slots=True)
class PychessTournamentPlayerRecord:
    tournament_id: str
    username: str
    rating: int
    points_entries: tuple[PointEntry, ...]
    score_total: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class PychessTournamentPairingRecord:
    tournament_id: str
    white_username: str
    black_username: str
    result_code: str
    played_at: datetime


def load_ndjson_records(path: Path) -> tuple[dict[str, object], ...]:
    """Load newline-delimited JSON records from `path`."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            rows.append(cast(dict[str, object], payload))
    return tuple(rows)


def parse_tournament_records(
    rows: tuple[dict[str, object], ...],
) -> tuple[PychessTournamentRecord, ...]:
    records: list[PychessTournamentRecord] = []
    for row in rows:
        tournament_id = row.get("_id")
        if not isinstance(tournament_id, str):
            continue

        raw_system = row.get("system", 0)
        raw_rounds = row.get("rounds", 0)
        system = int(raw_system) if isinstance(raw_system, int | float) else 0
        rounds = int(raw_rounds) if isinstance(raw_rounds, int | float) else 0

        raw_name = row.get("name")
        name = raw_name if isinstance(raw_name, str) else tournament_id
        records.append(
            PychessTournamentRecord(
                tournament_id=tournament_id,
                system=system,
                rounds=rounds,
                name=name,
            )
        )
    return tuple(records)


def parse_tournament_player_records(
    rows: tuple[dict[str, object], ...],
) -> tuple[PychessTournamentPlayerRecord, ...]:
    records: list[PychessTournamentPlayerRecord] = []
    for row in rows:
        tournament_id = row.get("tid")
        username = row.get("uid")
        if not isinstance(tournament_id, str) or not isinstance(username, str):
            continue

        raw_rating = row.get("r", 0)
        rating = int(raw_rating) if isinstance(raw_rating, int | float) else 0

        raw_points = row.get("p")
        points_entries = _normalize_points_entries(raw_points)

        raw_total = row.get("s", 0)
        score_total = int(raw_total) if isinstance(raw_total, int | float) else 0

        raw_active = row.get("a", True)
        is_active = bool(raw_active)

        records.append(
            PychessTournamentPlayerRecord(
                tournament_id=tournament_id,
                username=username,
                rating=rating,
                points_entries=points_entries,
                score_total=score_total,
                is_active=is_active,
            )
        )
    return tuple(records)


def parse_tournament_pairing_records(
    rows: tuple[dict[str, object], ...],
) -> tuple[PychessTournamentPairingRecord, ...]:
    records: list[PychessTournamentPairingRecord] = []
    for row in rows:
        tournament_id = row.get("tid")
        users = _as_user_pair(row.get("u"))
        result_code = row.get("r")
        played_at = _parse_mongo_datetime(row.get("d"))
        if (
            not isinstance(tournament_id, str)
            or users is None
            or not isinstance(result_code, str)
            or played_at is None
        ):
            continue

        records.append(
            PychessTournamentPairingRecord(
                tournament_id=tournament_id,
                white_username=users[0],
                black_username=users[1],
                result_code=result_code,
                played_at=played_at,
            )
        )

    records.sort(
        key=lambda record: (
            record.played_at,
            record.white_username,
            record.black_username,
        )
    )
    return tuple(records)


def group_pairings_by_round(
    pairings: tuple[PychessTournamentPairingRecord, ...],
) -> tuple[tuple[PychessTournamentPairingRecord, ...], ...]:
    """Greedy round reconstruction from timestamped pairings.

    Each round bucket contains pairings where each username appears at most once.
    """
    round_buckets: list[list[PychessTournamentPairingRecord]] = []
    used_users_per_round: list[set[str]] = []

    for pairing in pairings:
        placed = False
        for index, used_users in enumerate(used_users_per_round):
            if pairing.white_username in used_users or pairing.black_username in used_users:
                continue
            round_buckets[index].append(pairing)
            used_users.add(pairing.white_username)
            used_users.add(pairing.black_username)
            placed = True
            break

        if placed:
            continue

        round_buckets.append([pairing])
        used_users_per_round.append({pairing.white_username, pairing.black_username})

    return tuple(tuple(bucket) for bucket in round_buckets)


def point_entry_at(player: PychessTournamentPlayerRecord, round_index: int) -> PointEntry | None:
    if round_index < 0 or round_index >= len(player.points_entries):
        return None
    return player.points_entries[round_index]


def point_value(entry: PointEntry | None) -> int | None:
    if entry is None:
        return None
    if isinstance(entry, int):
        return entry
    if isinstance(entry, tuple) and entry and isinstance(entry[0], int):
        return entry[0]
    return None


def is_pairing_bye(entry: PointEntry | None) -> bool:
    return isinstance(entry, str) and entry == "-"


def infer_scoring_values(
    rounds: tuple[tuple[PychessTournamentPairingRecord, ...], ...],
    players_by_name: dict[str, PychessTournamentPlayerRecord],
) -> tuple[int, int, int]:
    """Infer win/draw/loss points from point sheets.

    Result codes follow pychess conventions:
    - `a`: white win
    - `b`: black win
    - `c`: draw
    """
    winner_points: list[int] = []
    loser_points: list[int] = []
    draw_points: list[int] = []

    for round_index, round_pairings in enumerate(rounds):
        for pairing in round_pairings:
            white = players_by_name.get(pairing.white_username)
            black = players_by_name.get(pairing.black_username)
            if white is None or black is None:
                continue

            white_points = point_value(point_entry_at(white, round_index))
            black_points = point_value(point_entry_at(black, round_index))

            white_outcome = result_outcome_for_color(pairing.result_code, is_white=True)
            black_outcome = result_outcome_for_color(pairing.result_code, is_white=False)
            if white_outcome is None or black_outcome is None:
                continue

            if white_outcome == "win" and white_points is not None:
                winner_points.append(white_points)
            if black_outcome == "win" and black_points is not None:
                winner_points.append(black_points)

            if white_outcome == "loss" and white_points is not None:
                loser_points.append(white_points)
            if black_outcome == "loss" and black_points is not None:
                loser_points.append(black_points)

            if white_outcome == "draw" and white_points is not None:
                draw_points.append(white_points)
            if black_outcome == "draw" and black_points is not None:
                draw_points.append(black_points)

    win_points = _mode_or_default(winner_points, default=2)
    draw_points_value = _mode_or_default(draw_points, default=max(0, win_points // 2))
    loss_points = _mode_or_default(loser_points, default=0)
    return (win_points, draw_points_value, loss_points)


def result_outcome_for_color(
    result_code: str, *, is_white: bool
) -> Literal["win", "loss", "draw"] | None:
    if result_code == "a":
        return "win" if is_white else "loss"
    if result_code == "b":
        return "loss" if is_white else "win"
    if result_code == "c":
        return "draw"
    return None


def select_snapshot_completed_rounds(
    total_rounds: int,
    *,
    max_snapshots: int,
    min_completed_rounds: int = 1,
) -> tuple[int, ...]:
    """Pick completed-round indices for TRF snapshot export."""
    if total_rounds <= 0:
        return ()

    candidates = [
        round_index for round_index in range(total_rounds) if round_index >= min_completed_rounds
    ]
    if max_snapshots <= 0 or len(candidates) <= max_snapshots:
        return tuple(candidates)
    return tuple(candidates[-max_snapshots:])


def _normalize_points_entries(raw_points: object) -> tuple[PointEntry, ...]:
    if not isinstance(raw_points, list):
        return ()
    normalized: list[PointEntry] = []
    for entry in cast(list[object], raw_points):
        if isinstance(entry, int):
            normalized.append(entry)
        elif isinstance(entry, str):
            normalized.append(entry)
        elif isinstance(entry, list):
            normalized.append(tuple(cast(list[object], entry)))
        elif isinstance(entry, tuple):
            normalized.append(tuple(cast(tuple[object, ...], entry)))
    return tuple(normalized)


def _mode_or_default(values: list[int], *, default: int) -> int:
    if not values:
        return default
    counts = Counter(values)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    return ordered[0][0]


def _parse_mongo_datetime(raw_value: object) -> datetime | None:
    if isinstance(raw_value, datetime):
        return _to_utc(raw_value)

    if isinstance(raw_value, dict):
        date_value = cast(dict[str, object], raw_value).get("$date")
        if isinstance(date_value, str):
            parsed = _parse_datetime_string(date_value)
            if parsed is not None:
                return parsed
        return None

    if isinstance(raw_value, str):
        return _parse_datetime_string(raw_value)

    return None


def _parse_datetime_string(value: str) -> datetime | None:
    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _to_utc(parsed)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_user_pair(raw_users: object) -> tuple[str, str] | None:
    if not isinstance(raw_users, list):
        return None
    users = cast(list[object], raw_users)
    if len(users) != 2:
        return None
    first = users[0]
    second = users[1]
    if not isinstance(first, str) or not isinstance(second, str):
        return None
    return (first, second)
