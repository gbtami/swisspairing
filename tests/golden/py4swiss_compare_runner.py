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
from py4swiss.engines.dutch.engine import Engine as Py4SwissDutchEngine
from py4swiss.trf import TrfParser

from swisspairing.benchmarking import (
    build_player_states_from_trf,
    build_trf_initial_color,
    portable_path_str,
    sort_pairings_for_compare,
)
from swisspairing.exceptions import PairingError as SwissPairingError
from swisspairing.model import Pairing
from swisspairing.tournament import pair_round_dutch


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
        states = build_player_states_from_trf(trf)
        swisspairing_raw = pair_round_dutch(states, initial_color=build_trf_initial_color(trf))
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
