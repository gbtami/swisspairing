"""Run py4swiss vs swisspairing benchmark over multiple TRF cases.

This driver uses subprocess isolation with per-case timeout so one pathological
case cannot hang the full benchmark run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from swisspairing.benchmarking import (
    BenchmarkSLA,
    benchmark_sla_to_dict,
    build_benchmark_summary,
    build_pythonpath_env,
    case_pairings_equal,
    case_swisspairing_result,
    current_python_executable,
    evaluate_benchmark_sla,
    portable_path_str,
    py4swiss_runtime_probe,
)


def _discover_cases(fixtures_dir: Path, pattern: str) -> list[Path]:
    return sorted(fixtures_dir.glob(pattern))


def _run_case(
    *,
    python_executable: str,
    runner_script: Path,
    trf_path: Path,
    warmup: int,
    repeats: int,
    timeout_seconds: int,
    env: dict[str, str],
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                python_executable,
                str(runner_script),
                "--trf",
                str(trf_path),
                "--warmup",
                str(warmup),
                "--repeats",
                str(repeats),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "trf": portable_path_str(trf_path),
            "runner_error": f"runner timed out after {timeout_seconds}s",
        }
    if completed.returncode != 0:
        return {
            "trf": portable_path_str(trf_path),
            "runner_error": (
                completed.stderr.strip()
                if completed.stderr.strip()
                else f"runner exited with code {completed.returncode}"
            ),
        }
    return json.loads(completed.stdout)


def _result_text(result: dict[str, Any] | None) -> str:
    if result is None:
        return "n/a"
    if result["ok"]:
        return f"ok p50={result['p50_ms']:.2f}ms p95={result['p95_ms']:.2f}ms"
    return f"err={result['error']}"


def _ratio_text(
    *,
    base: dict[str, Any],
    other: dict[str, Any] | None,
) -> str:
    if other is None:
        return "-"
    if not base["ok"] or not other["ok"]:
        return "-"
    if base["p50_ms"] <= 0:
        return "-"
    return f"{other['p50_ms'] / base['p50_ms']:.2f}x"


def _print_case_row(case_payload: dict[str, Any]) -> None:
    trf_name = Path(case_payload["trf"]).name
    if "py4swiss" not in case_payload:
        print(f"{trf_name:40} runner_error={case_payload['runner_error']}")
        return

    py4 = case_payload["py4swiss"]
    swisspairing = case_swisspairing_result(case_payload)

    py4_text = _result_text(py4)
    swisspairing_text = _result_text(swisspairing)

    ratio = _ratio_text(base=py4, other=swisspairing)
    equal = case_pairings_equal(case_payload)
    runner_error = case_payload.get("runner_error")

    print(
        f"{trf_name:40} py4[{py4_text}] "
        f"sp[{swisspairing_text}] ratio={ratio} equal={equal} "
        f"runner_error={runner_error}"
    )


def _validate_rate(name: str, value: float | None) -> None:
    if value is None:
        return
    if value < 0.0 or value > 1.0:
        raise SystemExit(f"{name} must be in [0.0, 1.0]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests" / "golden" / "fixtures",
    )
    parser.add_argument("--pattern", default="*.trf")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--sla-min-success-rate", type=float)
    parser.add_argument("--sla-max-runner-error-rate", type=float)
    parser.add_argument("--sla-max-p95-ms", type=float)
    parser.add_argument("--sla-max-p50-ratio", type=float)
    parser.add_argument("--sla-min-equality-rate-when-both-ok", type=float)
    args = parser.parse_args()
    _validate_rate("--sla-min-success-rate", args.sla_min_success_rate)
    _validate_rate("--sla-max-runner-error-rate", args.sla_max_runner_error_rate)
    _validate_rate(
        "--sla-min-equality-rate-when-both-ok",
        args.sla_min_equality_rate_when_both_ok,
    )

    repo_root = Path(__file__).resolve().parents[1]
    runner_script = Path(__file__).with_name("py4swiss_bench_case_runner.py")
    python_executable = current_python_executable()
    env = build_pythonpath_env(repo_root / "src")
    py4swiss_ok, py4swiss_probe_message = py4swiss_runtime_probe(python_executable, env=env)
    if not py4swiss_ok:
        raise SystemExit(f"{python_executable} cannot import py4swiss: {py4swiss_probe_message}")

    if args.case:
        cases = [Path(case).resolve() for case in args.case]
    else:
        cases = _discover_cases(args.fixtures_dir.resolve(), args.pattern)

    if not cases:
        raise SystemExit("no benchmark cases found")

    payloads: list[dict[str, Any]] = []
    print(
        "Running "
        f"{len(cases)} cases | warmup={args.warmup} repeats={args.repeats} "
        f"timeout={args.timeout_seconds}s",
        flush=True,
    )
    print(f"python={python_executable}", flush=True)
    print(f"py4swiss={py4swiss_probe_message}", flush=True)

    for case in cases:
        payload = _run_case(
            python_executable=python_executable,
            runner_script=runner_script,
            trf_path=case,
            warmup=args.warmup,
            repeats=args.repeats,
            timeout_seconds=args.timeout_seconds,
            env=env,
        )
        payloads.append(payload)
        _print_case_row(payload)

    summary = build_benchmark_summary(payloads, total_cases=len(cases))
    sla = BenchmarkSLA(
        min_success_rate=args.sla_min_success_rate,
        max_runner_error_rate=args.sla_max_runner_error_rate,
        max_p95_ms=args.sla_max_p95_ms,
        max_p50_ratio=args.sla_max_p50_ratio,
        min_equality_rate_when_both_ok=args.sla_min_equality_rate_when_both_ok,
    )
    sla_failures = evaluate_benchmark_sla(summary, sla)

    print("")
    print("Summary")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.json_output is not None:
        output_payload = {
            "summary": summary,
            "cases": payloads,
            "sla": {
                "passed": not sla_failures,
                "failures": sla_failures,
                "thresholds": benchmark_sla_to_dict(sla),
            },
        }
        args.json_output.write_text(json.dumps(output_payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json_output}")

    if sla_failures:
        print("")
        print("SLA violations")
        for failure in sla_failures:
            print(f"- {failure}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
