# pyright: reportMissingImports=false
"""Run recurring synthetic baseline benchmarks and persist trend artifacts."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swisspairing.benchmarking import (
    RECURRING_SYNTHETIC_SLA_PRESETS,
    benchmark_sla_to_dict,
    build_pythonpath_env,
    current_python_executable,
    evaluate_benchmark_sla,
    portable_path_str,
)
from swisspairing.recurring_baseline import append_trend_rows, parse_profile_sizes


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_output_root() -> Path:
    return Path(__file__).resolve().parent / "results" / "recurring"


def _run_id_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _timestamp_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runner_env(repo_root: Path) -> dict[str, str]:
    return build_pythonpath_env(repo_root / "src")


def _git_metadata(repo_root: Path) -> tuple[str | None, bool]:
    commit_probe = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    commit = commit_probe.stdout.strip() if commit_probe.returncode == 0 else None

    dirty_probe = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    dirty = bool(dirty_probe.stdout.strip()) if dirty_probe.returncode == 0 else False
    return commit, dirty


def _run_checked(*, command: list[str], env: dict[str, str]) -> None:
    print("$ " + " ".join(shlex.quote(part) for part in command), flush=True)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.stdout.strip():
        print(completed.stdout.rstrip())
    if completed.returncode == 0:
        return

    message = completed.stderr.strip() or f"command failed with exit code {completed.returncode}"
    raise RuntimeError(message)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", default="16,32,64,128,256,512")
    parser.add_argument("--tournaments-per-profile", type=int, default=8)
    parser.add_argument("--rounds-min", type=int, default=5)
    parser.add_argument("--rounds-max", type=int, default=11)
    parser.add_argument("--max-snapshots-per-tournament", type=int, default=2)
    parser.add_argument("--seed-base", type=int, default=20260306)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--output-root", type=Path, default=_default_output_root())
    parser.add_argument("--run-id")
    parser.add_argument("--python-executable")
    parser.add_argument("--sla-preset")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    if args.tournaments_per_profile <= 0:
        raise SystemExit("--tournaments-per-profile must be > 0")
    if args.rounds_min <= 0:
        raise SystemExit("--rounds-min must be > 0")
    if args.rounds_max < args.rounds_min:
        raise SystemExit("--rounds-max must be >= --rounds-min")
    if args.max_snapshots_per_tournament <= 0:
        raise SystemExit("--max-snapshots-per-tournament must be > 0")
    if args.repeats <= 0:
        raise SystemExit("--repeats must be > 0")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be > 0")

    profile_sizes = parse_profile_sizes(args.profiles)
    if args.sla_preset is None:
        profile_sla_by_size: dict[int, Any] = {}
    else:
        profile_sla_by_size = RECURRING_SYNTHETIC_SLA_PRESETS.get(args.sla_preset, {})
        if not profile_sla_by_size:
            available = ", ".join(sorted(RECURRING_SYNTHETIC_SLA_PRESETS))
            raise SystemExit(
                f"unknown --sla-preset {args.sla_preset!r}; available presets: {available}"
            )

    repo_root = _repo_root()
    python_executable = args.python_executable or current_python_executable()
    output_root = args.output_root.resolve()
    run_id = args.run_id or _run_id_now()
    timestamp_utc = _timestamp_now()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = _runner_env(repo_root)
    commit, dirty = _git_metadata(repo_root)

    simulate_script = repo_root / "benchmarks" / "simulate_swiss_batches.py"
    benchmark_script = repo_root / "benchmarks" / "benchmark_py4swiss_compare.py"
    trend_csv_path = output_root / "trend.csv"

    trend_rows: list[dict[str, Any]] = []
    profile_results: list[dict[str, Any]] = []
    pending_sla_failure: str | None = None

    print(
        "Running recurring baseline profiles: " + ", ".join(str(size) for size in profile_sizes),
        flush=True,
    )
    print(f"output_run_dir={run_dir}", flush=True)
    print(f"python={python_executable}", flush=True)

    for size in profile_sizes:
        profile_label = f"p{size}"
        profile_dir = run_dir / profile_label
        profile_dir.mkdir(parents=True, exist_ok=True)
        fixtures_dir = profile_dir / "fixtures"
        simulate_json = profile_dir / "simulate.json"
        benchmark_json = profile_dir / "benchmark.json"
        seed = args.seed_base + size

        simulate_cmd = [
            python_executable,
            str(simulate_script),
            "--output-dir",
            str(fixtures_dir),
            "--seed",
            str(seed),
            "--tournaments",
            str(args.tournaments_per_profile),
            "--players-min",
            str(size),
            "--players-max",
            str(size),
            "--rounds-min",
            str(args.rounds_min),
            "--rounds-max",
            str(args.rounds_max),
            "--max-snapshots-per-tournament",
            str(args.max_snapshots_per_tournament),
            "--metadata-json",
            str(simulate_json),
            "--fail-on-empty",
        ]
        benchmark_cmd = [
            python_executable,
            str(benchmark_script),
            "--fixtures-dir",
            str(fixtures_dir),
            "--pattern",
            "*.trf",
            "--warmup",
            str(args.warmup),
            "--repeats",
            str(args.repeats),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--json-output",
            str(benchmark_json),
        ]

        print(f"\n[{profile_label}] size={size}", flush=True)
        try:
            _run_checked(command=simulate_cmd, env=env)
            _run_checked(command=benchmark_cmd, env=env)
        except Exception as exc:
            profile_results.append(
                {
                    "profile": profile_label,
                    "size": size,
                    "status": "error",
                    "error": str(exc),
                }
            )
            if args.fail_fast:
                raise SystemExit(str(exc)) from exc
            continue

        simulate_payload = _load_json(simulate_json)
        benchmark_payload = _load_json(benchmark_json)
        simulate_summary = simulate_payload.get("summary", {})
        benchmark_summary = benchmark_payload.get("summary", {})
        benchmark_sla: dict[str, Any] | None = None
        profile_status = "ok"

        profile_sla = profile_sla_by_size.get(size)
        if profile_sla is not None:
            sla_failures = evaluate_benchmark_sla(benchmark_summary, profile_sla)
            benchmark_sla = {
                "passed": not sla_failures,
                "failures": sla_failures,
                "thresholds": benchmark_sla_to_dict(profile_sla),
                "preset": args.sla_preset,
            }
            if sla_failures:
                profile_status = "sla_failed"
                if args.fail_fast and pending_sla_failure is None:
                    pending_sla_failure = (
                        f"{profile_label} failed SLA preset {args.sla_preset}: "
                        + "; ".join(sla_failures)
                    )

        profile_results.append(
            {
                "profile": profile_label,
                "size": size,
                "status": profile_status,
                "simulate_summary": simulate_summary,
                "benchmark_summary": benchmark_summary,
                "benchmark_sla": benchmark_sla,
                "fixtures_dir": portable_path_str(fixtures_dir),
            }
        )
        trend_rows.append(
            {
                "run_id": run_id,
                "timestamp_utc": timestamp_utc,
                "profile": profile_label,
                "players_min": size,
                "players_max": size,
                "seed": seed,
                "requested_tournaments": simulate_summary.get("requested_tournaments"),
                "exported_tournaments": simulate_summary.get("exported_tournaments"),
                "exported_files": simulate_summary.get("exported_files"),
                "cases_total": benchmark_summary.get("cases_total"),
                "cases_executed": benchmark_summary.get("cases_executed"),
                "cases_runner_error": benchmark_summary.get("cases_runner_error"),
                "cases_both_ok": benchmark_summary.get("cases_both_ok"),
                "runner_error_rate": benchmark_summary.get("runner_error_rate"),
                "py4swiss_success_rate": benchmark_summary.get("py4swiss_success_rate"),
                "swisspairing_success_rate": benchmark_summary.get("swisspairing_success_rate"),
                "pairing_equal_rate_when_both_ok": benchmark_summary.get(
                    "pairing_equal_rate_when_both_ok"
                ),
                "pairing_equal_rate_over_all_cases": benchmark_summary.get(
                    "pairing_equal_rate_over_all_cases"
                ),
                "py4swiss_p50_ms": benchmark_summary.get("py4swiss_p50_ms"),
                "py4swiss_p95_ms": benchmark_summary.get("py4swiss_p95_ms"),
                "swisspairing_p50_ms": benchmark_summary.get("swisspairing_p50_ms"),
                "swisspairing_p95_ms": benchmark_summary.get("swisspairing_p95_ms"),
                "p50_ratio_swisspairing_over_py4swiss": benchmark_summary.get(
                    "p50_ratio_swisspairing_over_py4swiss"
                ),
                "sla_preset": args.sla_preset or "",
                "sla_passed": ("" if benchmark_sla is None else int(bool(benchmark_sla["passed"]))),
                "sla_failures": (
                    "" if benchmark_sla is None else " | ".join(benchmark_sla["failures"])
                ),
                "git_commit": commit,
                "git_dirty": int(dirty),
            }
        )

    append_trend_rows(trend_csv_path, trend_rows)

    run_payload = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "profiles": list(profile_sizes),
        "git_commit": commit,
        "git_dirty": dirty,
        "python_executable": portable_path_str(python_executable),
        "trend_csv": portable_path_str(trend_csv_path),
        "results": profile_results,
        "args": {
            "profiles": args.profiles,
            "tournaments_per_profile": args.tournaments_per_profile,
            "rounds_min": args.rounds_min,
            "rounds_max": args.rounds_max,
            "max_snapshots_per_tournament": args.max_snapshots_per_tournament,
            "seed_base": args.seed_base,
            "warmup": args.warmup,
            "repeats": args.repeats,
            "timeout_seconds": args.timeout_seconds,
            "sla_preset": args.sla_preset,
        },
    }
    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {summary_path}", flush=True)
    if trend_rows:
        print(f"updated {trend_csv_path}", flush=True)
    if pending_sla_failure is not None:
        raise SystemExit(pending_sla_failure)


if __name__ == "__main__":
    main()
