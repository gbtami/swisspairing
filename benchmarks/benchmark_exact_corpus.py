# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Benchmark the canonical exact solver on a checked real-world corpus."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from py4swiss.trf import TrfParser

from swisspairing.benchmarking import (
    build_player_states_from_trf,
    build_trf_initial_color,
    percentile,
    portable_path_str,
)
from swisspairing.exceptions import PairingError
from swisspairing.tournament import pair_round_dutch


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_manifest_path() -> Path:
    return _repo_root() / "benchmarks" / "fixtures" / "exact_runtime_cases.json"


def _load_manifest(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SystemExit(f"manifest {path} must contain a non-empty 'cases' list")
    normalized: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for entry in cases:
        if not isinstance(entry, dict):
            raise SystemExit(f"manifest entry must be an object, got {entry!r}")
        label = entry.get("label")
        trf = entry.get("trf")
        if not isinstance(label, str) or not label:
            raise SystemExit(f"manifest entry missing non-empty 'label': {entry!r}")
        if not isinstance(trf, str) or not trf:
            raise SystemExit(f"manifest entry missing non-empty 'trf': {entry!r}")
        if label in seen_labels:
            raise SystemExit(f"duplicate manifest label {label!r}")
        seen_labels.add(label)
        normalized.append({"label": label, "trf": trf})
    return normalized


def _time_case(
    *,
    trf_path: Path,
    warmup: int,
    repeats: int,
) -> dict[str, Any]:
    trf = TrfParser.parse(trf_path)
    states = build_player_states_from_trf(trf)
    initial_color = build_trf_initial_color(trf)

    timings_ms: list[float] = []
    error: str | None = None

    for _ in range(warmup):
        try:
            pair_round_dutch(states, initial_color=initial_color)
        except PairingError as exc:
            error = type(exc).__name__
            break

    if error is None:
        for _ in range(repeats):
            start_ns = time.perf_counter_ns()
            try:
                pair_round_dutch(states, initial_color=initial_color)
            except PairingError as exc:
                error = type(exc).__name__
                break
            timings_ms.append((time.perf_counter_ns() - start_ns) / 1_000_000)

    return {
        "ok": error is None,
        "error": error,
        "timings_ms": timings_ms,
        "p50_ms": percentile(timings_ms, 0.50),
        "p95_ms": percentile(timings_ms, 0.95),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=_default_manifest_path())
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    if args.repeats <= 0:
        raise SystemExit("--repeats must be > 0")
    if args.warmup < 0:
        raise SystemExit("--warmup must be >= 0")

    manifest_path = args.manifest.resolve()
    manifest_cases = _load_manifest(manifest_path)
    if args.case:
        selected_labels = set(args.case)
        cases = [case for case in manifest_cases if case["label"] in selected_labels]
        missing = sorted(selected_labels - {case["label"] for case in cases})
        if missing:
            raise SystemExit(f"unknown manifest case labels: {', '.join(missing)}")
    else:
        cases = manifest_cases

    payload_cases: list[dict[str, Any]] = []
    print(
        f"Running {len(cases)} exact corpus cases | warmup={args.warmup} repeats={args.repeats}",
        flush=True,
    )

    for case in cases:
        trf_path = (_repo_root() / case["trf"]).resolve()
        result = _time_case(
            trf_path=trf_path,
            warmup=args.warmup,
            repeats=args.repeats,
        )
        payload = {
            "label": case["label"],
            "trf": portable_path_str(trf_path),
            **result,
        }
        payload_cases.append(payload)
        if result["ok"]:
            print(
                f"{case['label']:24} p50={result['p50_ms']:.2f}ms p95={result['p95_ms']:.2f}ms",
                flush=True,
            )
        else:
            print(f"{case['label']:24} error={result['error']}", flush=True)

    ok_cases = [case for case in payload_cases if case["ok"]]
    slowest_case = max(ok_cases, key=lambda case: case["p95_ms"], default=None)
    summary = {
        "cases_total": len(payload_cases),
        "cases_ok": len(ok_cases),
        "cases_failed": len(payload_cases) - len(ok_cases),
        "suite_p50_ms": percentile([case["p50_ms"] for case in ok_cases], 0.50),
        "suite_p95_ms": percentile([case["p95_ms"] for case in ok_cases], 0.95),
        "slowest_case_label": None if slowest_case is None else slowest_case["label"],
        "slowest_case_p95_ms": None if slowest_case is None else slowest_case["p95_ms"],
    }

    print("")
    print("Summary")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.json_output is not None:
        output_payload = {
            "manifest": portable_path_str(manifest_path),
            "warmup": args.warmup,
            "repeats": args.repeats,
            "cases": payload_cases,
            "summary": summary,
        }
        args.json_output.write_text(json.dumps(output_payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json_output}")

    if len(ok_cases) != len(payload_cases):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
