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
from py4swiss.engines.dutch.engine import Engine as Py4SwissDutchEngine
from py4swiss.trf import TrfParser

from swisspairing.benchmarking import (
    build_player_states_from_trf,
    build_trf_initial_color,
    portable_path_str,
    sort_pairings_for_compare,
)
from swisspairing.exceptions import PairingError as SwissPairingError
from swisspairing.model import Color, Pairing, PlayerState
from swisspairing.tournament import pair_round_dutch


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


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
    initial_color: Color,
) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] | None = None
    error: str | None = None

    for _ in range(warmup):
        try:
            raw = pair_round_dutch(
                states,
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
    args = parser.parse_args()

    trf_path = args.trf.resolve()
    trf = TrfParser.parse(trf_path)
    states = build_player_states_from_trf(trf)
    initial_color = build_trf_initial_color(trf)

    py4swiss_result = _time_py4swiss(trf, warmup=args.warmup, repeats=args.repeats)
    swisspairing_result = _time_swisspairing(
        states,
        warmup=args.warmup,
        repeats=args.repeats,
        initial_color=initial_color,
    )

    pairings_equal: bool | None = None
    if py4swiss_result["ok"] and swisspairing_result["ok"]:
        pairings_equal = py4swiss_result["pairings"] == swisspairing_result["pairings"]

    payload = {
        "trf": portable_path_str(trf_path),
        "warmup": args.warmup,
        "repeats": args.repeats,
        "py4swiss": py4swiss_result,
        "swisspairing": swisspairing_result,
        "pairings_equal": pairings_equal,
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
