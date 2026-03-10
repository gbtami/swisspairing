# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Benchmark one TRF case for py4swiss and swisspairing.

Run this script with the active project interpreter so both `py4swiss` and
`swisspairing` are importable.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from py4swiss.engines.common.exceptions import PairingError as Py4SwissPairingError
from py4swiss.engines.common.float import Float as PyFloat
from py4swiss.engines.dutch.engine import Engine as Py4SwissDutchEngine
from py4swiss.engines.dutch.player import Player as Py4SwissPlayer
from py4swiss.engines.dutch.player import get_player_infos_from_trf
from py4swiss.trf import TrfParser

from swisspairing.benchmarking import (
    build_trf_had_full_point_unplayed_round_by_player_id,
    build_trf_initial_color,
    build_trf_unplayed_games_by_player_id,
    portable_path_str,
    sort_pairings_for_compare,
)
from swisspairing.exceptions import PairingError as SwissPairingError
from swisspairing.model import Color, FloatKind, Pairing, PlayerState
from swisspairing.tournament import pair_round_dutch

_DEFAULT_FAST_SEQUENTIAL_SEARCH_MAX_PLAYERS = 6


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


def _to_float_kind(float_value: PyFloat) -> FloatKind:
    if float_value == PyFloat.UP:
        return FloatKind.UP
    if float_value == PyFloat.DOWN:
        return FloatKind.DOWN
    return FloatKind.NONE


def _build_forbidden_map(trf: Any) -> dict[int, set[int]]:
    forbidden_map: dict[int, set[int]] = {}
    for left_id, right_id in trf.x_section.forbidden_pairs:
        forbidden_map.setdefault(left_id, set()).add(right_id)
        forbidden_map.setdefault(right_id, set()).add(left_id)
    return forbidden_map


def _build_player_states_from_trf(trf: Any) -> tuple[PlayerState, ...]:
    py4swiss_players = get_player_infos_from_trf(trf)
    top_ids = {player.id for player in py4swiss_players if player.top_scorer}
    forbidden_map = _build_forbidden_map(trf)
    unplayed_games_by_id = build_trf_unplayed_games_by_player_id(trf)
    full_point_unplayed_round_by_id = build_trf_had_full_point_unplayed_round_by_player_id(trf)
    states: list[PlayerState] = []

    for player in py4swiss_players:
        states.append(
            _build_player_state(
                player,
                top_ids,
                forbidden_map,
                unplayed_games=unplayed_games_by_id.get(player.id, 0),
                had_full_point_unplayed_round=full_point_unplayed_round_by_id.get(player.id, False),
            )
        )
    return tuple(states)


def _build_player_state(
    player: Py4SwissPlayer,
    top_ids: set[int],
    forbidden_map: dict[int, set[int]],
    *,
    unplayed_games: int,
    had_full_point_unplayed_round: bool,
) -> PlayerState:
    float_history = (
        _to_float_kind(player.float_2),
        _to_float_kind(player.float_1),
    )
    return PlayerState(
        player_id=str(player.id),
        pairing_no=player.number,
        score=player.points_with_acceleration,
        opponents=frozenset(str(opponent_id) for opponent_id in player.opponents),
        forbidden_opponents=frozenset(
            str(opponent_id) for opponent_id in forbidden_map.get(player.id, set())
        ),
        color_history=tuple("white" if is_white else "black" for is_white in player.colors),
        unplayed_games=unplayed_games,
        had_full_point_bye=player.bye_received,
        had_full_point_unplayed_round=had_full_point_unplayed_round,
        is_top_scorer=player.top_scorer,
        is_topscorer_or_opponent=player.top_scorer or bool(player.opponents & top_ids),
        float_history=float_history,
    )


def _normalize_py4swiss_pairings(pairings: list[Any]) -> list[list[str | None]]:
    normalized: list[list[str | None]] = []
    for pairing in pairings:
        if pairing.black == 0:
            normalized.append([str(pairing.white), None])
            continue
        normalized.append([str(pairing.white), str(pairing.black)])
    return sort_pairings_for_compare(normalized)


def _normalize_swisspairing_pairings(pairings: tuple[Pairing, ...]) -> list[list[str | None]]:
    normalized: list[list[str | None]] = []
    for pairing in pairings:
        if pairing.black_id is None:
            normalized.append([pairing.white_id, None])
            continue
        normalized.append([pairing.white_id, pairing.black_id])
    return sort_pairings_for_compare(normalized)


def _time_py4swiss(trf: Any, *, warmup: int, repeats: int) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] | None = None
    error: str | None = None

    for _ in range(warmup):
        try:
            raw = Py4SwissDutchEngine.generate_pairings(trf)
            last_pairings = _normalize_py4swiss_pairings(raw)
        except Py4SwissPairingError:
            error = "PairingError"
            break

    if error is None:
        for _ in range(repeats):
            start_ns = time.perf_counter_ns()
            try:
                raw = Py4SwissDutchEngine.generate_pairings(trf)
                last_pairings = _normalize_py4swiss_pairings(raw)
            except Py4SwissPairingError:
                error = "PairingError"
                break
            end_ns = time.perf_counter_ns()
            timings_ms.append((end_ns - start_ns) / 1_000_000)

    return {
        "ok": error is None,
        "error": error,
        "timings_ms": timings_ms,
        "p50_ms": _percentile(timings_ms, 0.50),
        "p95_ms": _percentile(timings_ms, 0.95),
        "pairings": last_pairings or [],
    }


def _time_swisspairing(
    states: tuple[PlayerState, ...],
    *,
    warmup: int,
    repeats: int,
    sequential_search_max_players: int | None,
    initial_color: Color,
) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] | None = None
    error: str | None = None

    for _ in range(warmup):
        try:
            raw = pair_round_dutch(
                states,
                sequential_search_max_players=sequential_search_max_players,
                initial_color=initial_color,
            )
            last_pairings = _normalize_swisspairing_pairings(raw.pairings)
        except SwissPairingError:
            error = "PairingError"
            break

    if error is None:
        for _ in range(repeats):
            start_ns = time.perf_counter_ns()
            try:
                raw = pair_round_dutch(
                    states,
                    sequential_search_max_players=sequential_search_max_players,
                    initial_color=initial_color,
                )
                last_pairings = _normalize_swisspairing_pairings(raw.pairings)
            except SwissPairingError:
                error = "PairingError"
                break
            end_ns = time.perf_counter_ns()
            timings_ms.append((end_ns - start_ns) / 1_000_000)

    return {
        "ok": error is None,
        "error": error,
        "timings_ms": timings_ms,
        "p50_ms": _percentile(timings_ms, 0.50),
        "p95_ms": _percentile(timings_ms, 0.95),
        "pairings": last_pairings or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trf", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--swisspairing-mode",
        choices=("fast", "strict"),
        default="fast",
    )
    parser.add_argument(
        "--fast-sequential-search-max-players",
        type=int,
        default=_DEFAULT_FAST_SEQUENTIAL_SEARCH_MAX_PLAYERS,
    )
    args = parser.parse_args()
    if args.fast_sequential_search_max_players < 0:
        raise SystemExit("--fast-sequential-search-max-players must be >= 0")

    trf_path = args.trf.resolve()
    trf = TrfParser.parse(trf_path)
    states = _build_player_states_from_trf(trf)
    initial_color = build_trf_initial_color(trf)

    py4swiss_result = _time_py4swiss(trf, warmup=args.warmup, repeats=args.repeats)
    swisspairing_limit = (
        None if args.swisspairing_mode == "strict" else args.fast_sequential_search_max_players
    )
    swisspairing_result = _time_swisspairing(
        states,
        warmup=args.warmup,
        repeats=args.repeats,
        sequential_search_max_players=swisspairing_limit,
        initial_color=initial_color,
    )

    pairings_equal: bool | None = None
    if py4swiss_result["ok"] and swisspairing_result["ok"]:
        pairings_equal = py4swiss_result["pairings"] == swisspairing_result["pairings"]

    payload = {
        "trf": portable_path_str(trf_path),
        "warmup": args.warmup,
        "repeats": args.repeats,
        "swisspairing_mode": args.swisspairing_mode,
        "fast_sequential_search_max_players": args.fast_sequential_search_max_players,
        "py4swiss": py4swiss_result,
        "swisspairing": swisspairing_result,
        "pairings_equal": pairings_equal,
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
