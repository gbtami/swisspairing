"""Run py4swiss vs bbpPairings vs swisspairing comparisons over TRF cases."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from swisspairing.benchmarking import (
    build_pythonpath_env,
    current_python_executable,
    discover_bbp_executable,
    discover_javafo_jar,
    javafo_runtime_probe,
    percentile,
    portable_path_str,
    py4swiss_runtime_probe,
)


def _discover_cases(fixtures_dir: Path, pattern: str) -> list[Path]:
    return sorted(fixtures_dir.glob(pattern))


def _default_bbp_executable() -> str | None:
    discovered = discover_bbp_executable()
    return None if discovered is None else str(discovered)


def _default_javafo_jar() -> str | None:
    discovered = discover_javafo_jar()
    return None if discovered is None else str(discovered)


def _bbp_runtime_probe(bbp_executable: str) -> tuple[bool, str]:
    probe = subprocess.run(
        [bbp_executable, "-r"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        message = probe.stdout.strip().splitlines()[0] if probe.stdout.strip() else bbp_executable
        return True, message
    message = probe.stderr.strip() or probe.stdout.strip()
    if not message:
        message = f"bbpPairings probe failed with exit code {probe.returncode}"
    return False, message


def _run_case(
    *,
    python_executable: str,
    runner_script: Path,
    trf_path: Path,
    warmup: int,
    repeats: int,
    timeout_seconds: int,
    bbp_executable: str,
    javafo_jar: str | None,
    env: dict[str, str],
) -> dict[str, Any]:
    command = [
        python_executable,
        str(runner_script),
        "--trf",
        str(trf_path),
        "--warmup",
        str(warmup),
        "--repeats",
        str(repeats),
        "--bbp-executable",
        bbp_executable,
    ]
    if javafo_jar:
        command.extend(("--javafo-jar", javafo_jar))
    try:
        completed = subprocess.run(
            command,
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


def _ratio_text(*, base: dict[str, Any] | None, other: dict[str, Any] | None) -> str:
    if base is None or other is None:
        return "-"
    if not base["ok"] or not other["ok"] or base["p50_ms"] <= 0:
        return "-"
    return f"{other['p50_ms'] / base['p50_ms']:.2f}x"


def _print_case_row(case_payload: dict[str, Any]) -> None:
    trf_name = Path(case_payload["trf"]).name
    if "py4swiss" not in case_payload or "bbp" not in case_payload:
        print(f"{trf_name:40} runner_error={case_payload['runner_error']}")
        return

    py4 = case_payload["py4swiss"]
    bbp = case_payload["bbp"]
    javafo = case_payload.get("javafo")
    swisspairing = case_payload.get("swisspairing")
    print(
        f"{trf_name:40} py4[{_result_text(py4)}] "
        f"bbp[{_result_text(bbp)}] ref_equal={case_payload.get('reference_pairings_equal')} "
        f"javafo[{_result_text(javafo)}] "
        f"ref_equal_vs_javafo={case_payload.get('reference_pairings_equal_vs_javafo')} "
        f"sp[{_result_text(swisspairing)}] "
        f"ratio_vs_py4={_ratio_text(base=py4, other=swisspairing)} "
        f"ratio_vs_bbp={_ratio_text(base=bbp, other=swisspairing)} "
        f"ratio_vs_javafo={_ratio_text(base=javafo, other=swisspairing)} "
        f"equal_vs_py4={case_payload.get('pairings_equal_vs_py4swiss')} "
        f"equal_vs_bbp={case_payload.get('pairings_equal_vs_bbp')} "
        f"equal_vs_javafo={case_payload.get('pairings_equal_vs_javafo')}"
    )


def _collect_timings(payloads: list[dict[str, Any]], key: str) -> list[float]:
    timings: list[float] = []
    for payload in payloads:
        result = payload.get(key)
        if isinstance(result, dict) and result.get("ok"):
            timings.extend(float(value) for value in result["timings_ms"])
    return timings


def _rate(values: list[dict[str, Any]], key: str) -> float:
    if not values:
        return 0.0
    success_count = 0
    for payload in values:
        result = payload.get(key)
        if isinstance(result, dict) and result.get("ok"):
            success_count += 1
    return success_count / len(values)


def _equality_rate(payloads: list[dict[str, Any]], key: str) -> float:
    candidates = [payload for payload in payloads if isinstance(payload.get(key), bool)]
    if not candidates:
        return 0.0
    matches = [payload for payload in candidates if payload[key] is True]
    return len(matches) / len(candidates)


def _timing_summary(payloads: list[dict[str, Any]], key: str) -> tuple[float, float]:
    timings = _collect_timings(payloads, key)
    return percentile(timings, 0.50), percentile(timings, 0.95)


def _ratio(base: float, other: float) -> float | None:
    if base <= 0:
        return None
    return other / base


def _build_summary(payloads: list[dict[str, Any]], *, total_cases: int) -> dict[str, Any]:
    py4_p50, py4_p95 = _timing_summary(payloads, "py4swiss")
    bbp_p50, bbp_p95 = _timing_summary(payloads, "bbp")
    javafo_p50, javafo_p95 = _timing_summary(payloads, "javafo")
    swisspairing_p50, swisspairing_p95 = _timing_summary(payloads, "swisspairing")
    runner_error_cases = sum(1 for payload in payloads if "runner_error" in payload)

    return {
        "cases_total": total_cases,
        "cases_executed_py4swiss": sum(
            1
            for payload in payloads
            if isinstance(payload.get("py4swiss"), dict) and payload["py4swiss"]["ok"]
        ),
        "cases_executed_bbp": sum(
            1
            for payload in payloads
            if isinstance(payload.get("bbp"), dict) and payload["bbp"]["ok"]
        ),
        "cases_executed_javafo": sum(
            1
            for payload in payloads
            if isinstance(payload.get("javafo"), dict) and payload["javafo"]["ok"]
        ),
        "cases_executed_swisspairing": sum(
            1
            for payload in payloads
            if isinstance(payload.get("swisspairing"), dict) and payload["swisspairing"]["ok"]
        ),
        "cases_runner_error": runner_error_cases,
        "runner_error_rate": runner_error_cases / total_cases,
        "py4swiss_success_rate": _rate(payloads, "py4swiss"),
        "bbp_success_rate": _rate(payloads, "bbp"),
        "javafo_success_rate": _rate(payloads, "javafo"),
        "swisspairing_success_rate": _rate(payloads, "swisspairing"),
        "pairing_equal_rate_py4swiss_vs_bbp_when_both_ok": _equality_rate(
            payloads,
            "reference_pairings_equal",
        ),
        "pairing_equal_rate_py4swiss_vs_javafo_when_both_ok": _equality_rate(
            payloads,
            "reference_pairings_equal_vs_javafo",
        ),
        "pairing_equal_rate_swisspairing_vs_py4swiss_when_both_ok": _equality_rate(
            payloads,
            "pairings_equal_vs_py4swiss",
        ),
        "pairing_equal_rate_swisspairing_vs_bbp_when_both_ok": _equality_rate(
            payloads,
            "pairings_equal_vs_bbp",
        ),
        "pairing_equal_rate_swisspairing_vs_javafo_when_both_ok": _equality_rate(
            payloads,
            "pairings_equal_vs_javafo",
        ),
        "py4swiss_p50_ms": py4_p50,
        "py4swiss_p95_ms": py4_p95,
        "bbp_p50_ms": bbp_p50,
        "bbp_p95_ms": bbp_p95,
        "javafo_p50_ms": javafo_p50,
        "javafo_p95_ms": javafo_p95,
        "swisspairing_p50_ms": swisspairing_p50,
        "swisspairing_p95_ms": swisspairing_p95,
        "p50_ratio_swisspairing_over_py4swiss": _ratio(py4_p50, swisspairing_p50),
        "p50_ratio_swisspairing_over_bbp": _ratio(bbp_p50, swisspairing_p50),
        "p50_ratio_swisspairing_over_javafo": _ratio(javafo_p50, swisspairing_p50),
    }


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
    parser.add_argument("--bbp-executable", default=_default_bbp_executable())
    parser.add_argument("--javafo-jar", default=_default_javafo_jar())
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    if not args.bbp_executable:
        raise SystemExit(
            "--bbp-executable is required; set SWISSPAIRING_BBP_EXECUTABLE "
            "or BBP_PAIRINGS_EXE, or pass the path explicitly"
        )

    repo_root = Path(__file__).resolve().parents[1]
    runner_script = Path(__file__).with_name("reference_compare_case_runner.py")
    python_executable = current_python_executable()
    env = build_pythonpath_env(repo_root / "src")
    py4swiss_ok, py4swiss_probe_message = py4swiss_runtime_probe(python_executable, env=env)
    if not py4swiss_ok:
        raise SystemExit(f"{python_executable} cannot import py4swiss: {py4swiss_probe_message}")
    bbp_ok, bbp_probe_message = _bbp_runtime_probe(args.bbp_executable)
    if not bbp_ok:
        raise SystemExit(
            f"{args.bbp_executable} cannot run bbpPairings Dutch probe: {bbp_probe_message}"
        )
    javafo_probe_message: str | None = None
    if args.javafo_jar:
        javafo_ok, javafo_probe_message = javafo_runtime_probe(args.javafo_jar)
        if not javafo_ok:
            raise SystemExit(
                f"{args.javafo_jar} cannot run JaVaFo Dutch probe: {javafo_probe_message}"
            )

    if args.case:
        cases = [Path(case).resolve() for case in args.case]
    else:
        cases = _discover_cases(args.fixtures_dir.resolve(), args.pattern)
    if not cases:
        raise SystemExit("no comparison cases found")

    payloads: list[dict[str, Any]] = []
    print(
        "Running "
        f"{len(cases)} cases | warmup={args.warmup} repeats={args.repeats} "
        f"timeout={args.timeout_seconds}s",
        flush=True,
    )
    print(f"python={python_executable}", flush=True)
    print(f"py4swiss={py4swiss_probe_message}", flush=True)
    print(f"bbpPairings={bbp_probe_message}", flush=True)
    if javafo_probe_message is not None:
        print(f"JaVaFo={javafo_probe_message}", flush=True)

    for case in cases:
        payload = _run_case(
            python_executable=python_executable,
            runner_script=runner_script,
            trf_path=case,
            warmup=args.warmup,
            repeats=args.repeats,
            timeout_seconds=args.timeout_seconds,
            bbp_executable=args.bbp_executable,
            javafo_jar=args.javafo_jar,
            env=env,
        )
        payloads.append(payload)
        _print_case_row(payload)

    summary = _build_summary(payloads, total_cases=len(cases))
    print("")
    print("Summary")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.json_output is not None:
        output_payload = {
            "summary": summary,
            "cases": payloads,
            "bbp_executable": args.bbp_executable,
        }
        if args.javafo_jar:
            output_payload["javafo_jar"] = portable_path_str(args.javafo_jar)
        args.json_output.write_text(json.dumps(output_payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json_output}")


if __name__ == "__main__":
    main()
