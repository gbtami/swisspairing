# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Run a single py4swiss-vs-swisspairing golden comparison.

This runner is executed with the active project interpreter so both
`py4swiss` and `swisspairing` are available from the same environment.
"""

from __future__ import annotations

import json
import sys
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
    build_trf_unplayed_games_by_player_id,
    portable_path_str,
)
from swisspairing.exceptions import PairingError as SwissPairingError
from swisspairing.model import FloatKind, Pairing, PlayerState
from swisspairing.tournament import pair_round_dutch


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
        ordered = sorted((str(pairing.white), str(pairing.black)))
        normalized.append([ordered[0], ordered[1]])
    normalized.sort(key=lambda pair: (pair[1] is None, pair[0], pair[1] or ""))
    return normalized


def _normalize_swisspairing_pairings(pairings: tuple[Pairing, ...]) -> list[list[str | None]]:
    normalized: list[list[str | None]] = []
    for pairing in pairings:
        if pairing.black_id is None:
            normalized.append([pairing.white_id, None])
            continue
        ordered = sorted((pairing.white_id, pairing.black_id))
        normalized.append([ordered[0], ordered[1]])
    normalized.sort(key=lambda pair: (pair[1] is None, pair[0], pair[1] or ""))
    return normalized


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python py4swiss_compare_runner.py <trf_path>")

    trf_path = Path(sys.argv[1]).resolve()
    trf = TrfParser.parse(trf_path)

    py4swiss_error: str | None = None
    swisspairing_error: str | None = None
    py4swiss_pairings: list[list[str | None]] = []
    swisspairing_pairings: list[list[str | None]] = []

    try:
        py4swiss_raw = Py4SwissDutchEngine.generate_pairings(trf)
        py4swiss_pairings = _normalize_py4swiss_pairings(py4swiss_raw)
    except Py4SwissPairingError:
        py4swiss_error = "PairingError"

    try:
        states = _build_player_states_from_trf(trf)
        swisspairing_raw = pair_round_dutch(states)
        swisspairing_pairings = _normalize_swisspairing_pairings(swisspairing_raw.pairings)
    except SwissPairingError:
        swisspairing_error = "PairingError"

    payload = {
        "trf": portable_path_str(trf_path),
        "py4swiss_error": py4swiss_error,
        "swisspairing_error": swisspairing_error,
        "py4swiss_pairings": py4swiss_pairings,
        "swisspairing_pairings": swisspairing_pairings,
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
