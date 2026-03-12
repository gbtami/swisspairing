# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Benchmark one TRF case for py4swiss, bbpPairings, and swisspairing."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from py4swiss.engines.common.exceptions import PairingError as Py4SwissPairingError
from py4swiss.engines.dutch.engine import Engine as Py4SwissDutchEngine
from py4swiss.trf import TrfParser

from swisspairing.benchmarking import (
    build_player_states_from_trf,
    build_trf_initial_color,
    parse_bbp_pairings_output,
    parse_javafo_pairings_output,
    percentile,
    portable_path_str,
    sort_pairings_for_compare,
)
from swisspairing.exceptions import PairingError as SwissPairingError
from swisspairing.model import Color, Pairing, PlayerState
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


def _timed_result(
    *,
    ok: bool,
    error: str | None,
    timings_ms: list[float],
    pairings: list[list[str | None]],
) -> dict[str, Any]:
    return {
        "ok": ok,
        "error": error,
        "timings_ms": timings_ms,
        "p50_ms": percentile(timings_ms, 0.50),
        "p95_ms": percentile(timings_ms, 0.95),
        "pairings": pairings,
    }


def _time_py4swiss(trf: Any, *, warmup: int, repeats: int) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] = []
    error: str | None = None

    for _ in range(warmup):
        try:
            last_pairings = _normalize_py4swiss_pairings(Py4SwissDutchEngine.generate_pairings(trf))
        except Py4SwissPairingError:
            error = "PairingError"
            break

    if error is None:
        for _ in range(repeats):
            start_ns = time.perf_counter_ns()
            try:
                last_pairings = _normalize_py4swiss_pairings(
                    Py4SwissDutchEngine.generate_pairings(trf)
                )
            except Py4SwissPairingError:
                error = "PairingError"
                break
            timings_ms.append((time.perf_counter_ns() - start_ns) / 1_000_000)

    return _timed_result(
        ok=error is None,
        error=error,
        timings_ms=timings_ms,
        pairings=last_pairings,
    )


def _run_bbp_once(bbp_executable: str, trf_path: Path) -> tuple[str | None, list[list[str | None]]]:
    with tempfile.TemporaryDirectory(prefix="bbp_pairings_") as temp_dir:
        output_path = Path(temp_dir) / "pairings.out"
        completed = subprocess.run(
            [bbp_executable, "--dutch", str(trf_path), "-p", str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 1:
            return "PairingError", []
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            return message or f"bbpPairings exited with code {completed.returncode}", []
        return None, parse_bbp_pairings_output(output_path.read_text(encoding="utf-8"))


def _time_bbp(
    trf_path: Path,
    *,
    warmup: int,
    repeats: int,
    bbp_executable: str,
) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] = []
    error: str | None = None

    for _ in range(warmup):
        error, last_pairings = _run_bbp_once(bbp_executable, trf_path)
        if error is not None:
            break

    if error is None:
        for _ in range(repeats):
            start_ns = time.perf_counter_ns()
            error, last_pairings = _run_bbp_once(bbp_executable, trf_path)
            if error is not None:
                break
            timings_ms.append((time.perf_counter_ns() - start_ns) / 1_000_000)

    return _timed_result(
        ok=error is None,
        error=error,
        timings_ms=timings_ms,
        pairings=last_pairings,
    )


def _run_javafo_once(
    javafo_jar: str,
    trf_path: Path,
) -> tuple[str | None, list[list[str | None]]]:
    with tempfile.TemporaryDirectory(prefix="javafo_pairings_") as temp_dir:
        output_path = Path(temp_dir) / "pairings.out"
        completed = subprocess.run(
            ["java", "-jar", javafo_jar, str(trf_path), "-p", str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            return message or f"JaVaFo exited with code {completed.returncode}", []
        if not output_path.exists():
            message = completed.stderr.strip() or completed.stdout.strip()
            return message or "JaVaFo did not produce an output file", []
        return None, parse_javafo_pairings_output(output_path.read_text(encoding="utf-8"))


def _time_javafo(
    trf_path: Path,
    *,
    warmup: int,
    repeats: int,
    javafo_jar: str,
) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] = []
    error: str | None = None

    for _ in range(warmup):
        error, last_pairings = _run_javafo_once(javafo_jar, trf_path)
        if error is not None:
            break

    if error is None:
        for _ in range(repeats):
            start_ns = time.perf_counter_ns()
            error, last_pairings = _run_javafo_once(javafo_jar, trf_path)
            if error is not None:
                break
            timings_ms.append((time.perf_counter_ns() - start_ns) / 1_000_000)

    return _timed_result(
        ok=error is None,
        error=error,
        timings_ms=timings_ms,
        pairings=last_pairings,
    )


def _time_swisspairing(
    states: tuple[PlayerState, ...],
    *,
    warmup: int,
    repeats: int,
    initial_color: Color,
) -> dict[str, Any]:
    timings_ms: list[float] = []
    last_pairings: list[list[str | None]] = []
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
            timings_ms.append((time.perf_counter_ns() - start_ns) / 1_000_000)

    return _timed_result(
        ok=error is None,
        error=error,
        timings_ms=timings_ms,
        pairings=last_pairings,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trf", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--bbp-executable", required=True)
    parser.add_argument("--javafo-jar")
    args = parser.parse_args()

    trf_path = args.trf.resolve()
    trf = TrfParser.parse(trf_path)
    states = build_player_states_from_trf(trf)
    initial_color = build_trf_initial_color(trf)

    py4swiss_result = _time_py4swiss(trf, warmup=args.warmup, repeats=args.repeats)
    bbp_result = _time_bbp(
        trf_path,
        warmup=args.warmup,
        repeats=args.repeats,
        bbp_executable=args.bbp_executable,
    )
    javafo_result: dict[str, Any] | None = None
    if args.javafo_jar:
        javafo_result = _time_javafo(
            trf_path,
            warmup=args.warmup,
            repeats=args.repeats,
            javafo_jar=args.javafo_jar,
        )
    swisspairing_result = _time_swisspairing(
        states,
        warmup=args.warmup,
        repeats=args.repeats,
        initial_color=initial_color,
    )

    pairings_equal_vs_py4swiss: bool | None = None
    pairings_equal_vs_bbp: bool | None = None
    pairings_equal_vs_javafo: bool | None = None
    reference_pairings_equal: bool | None = None
    reference_pairings_equal_vs_javafo: bool | None = None
    if py4swiss_result["ok"] and swisspairing_result["ok"]:
        pairings_equal_vs_py4swiss = py4swiss_result["pairings"] == swisspairing_result["pairings"]
    if bbp_result["ok"] and swisspairing_result["ok"]:
        pairings_equal_vs_bbp = bbp_result["pairings"] == swisspairing_result["pairings"]
    if javafo_result is not None and javafo_result["ok"] and swisspairing_result["ok"]:
        pairings_equal_vs_javafo = javafo_result["pairings"] == swisspairing_result["pairings"]
    if py4swiss_result["ok"] and bbp_result["ok"]:
        reference_pairings_equal = py4swiss_result["pairings"] == bbp_result["pairings"]
    if javafo_result is not None and py4swiss_result["ok"] and javafo_result["ok"]:
        reference_pairings_equal_vs_javafo = (
            py4swiss_result["pairings"] == javafo_result["pairings"]
        )

    payload = {
        "trf": portable_path_str(trf_path),
        "warmup": args.warmup,
        "repeats": args.repeats,
        "bbp_executable": args.bbp_executable,
        "py4swiss": py4swiss_result,
        "bbp": bbp_result,
        "swisspairing": swisspairing_result,
        "pairings_equal_vs_py4swiss": pairings_equal_vs_py4swiss,
        "pairings_equal_vs_bbp": pairings_equal_vs_bbp,
        "reference_pairings_equal": reference_pairings_equal,
    }
    if javafo_result is not None:
        payload["javafo_jar"] = portable_path_str(args.javafo_jar)
        payload["javafo"] = javafo_result
        payload["pairings_equal_vs_javafo"] = pairings_equal_vs_javafo
        payload["reference_pairings_equal_vs_javafo"] = reference_pairings_equal_vs_javafo
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
