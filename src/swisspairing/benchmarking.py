"""Helpers for benchmark reporting, SLA checks, and runtime probing."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

_PLAYED_TRF_RESULT_VALUES = frozenset({"1", "=", "0", "W", "D", "L"})


@dataclass(frozen=True, slots=True)
class BenchmarkSLA:
    """Optional SLA thresholds for benchmark summaries."""

    min_fast_success_rate: float | None = None
    max_runner_error_rate: float | None = None
    max_fast_p95_ms: float | None = None
    max_fast_p50_ratio: float | None = None
    min_fast_equality_rate_when_both_ok: float | None = None


RECURRING_SYNTHETIC_SLA_PRESETS: dict[str, dict[int, BenchmarkSLA]] = {
    # Current recommended recurring synthetic baseline after lowering the fast
    # sequential-search cap to 6 and extending the checked-in sweep to p512.
    "post-fast-cap-6-plus-512-20260306": {
        16: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=10.0,
            max_fast_p50_ratio=0.75,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        32: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=40.0,
            max_fast_p50_ratio=0.8,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        64: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=35.0,
            max_fast_p50_ratio=0.15,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        128: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=60.0,
            max_fast_p50_ratio=0.18,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        256: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=325.0,
            max_fast_p50_ratio=0.25,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        512: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=3000.0,
            max_fast_p50_ratio=0.6,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
    },
    # Historical synthetic baseline kept for reference before p512 was folded
    # into the default recurring sweep.
    "post-fast-cap-6-20260306": {
        16: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=10.0,
            max_fast_p50_ratio=0.75,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        32: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=40.0,
            max_fast_p50_ratio=0.8,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        64: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=35.0,
            max_fast_p50_ratio=0.15,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        128: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=60.0,
            max_fast_p50_ratio=0.18,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        256: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=325.0,
            max_fast_p50_ratio=0.25,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
    },
    # Historical synthetic baseline kept for reference after the C8
    # next-bracket-key runtime cut in the round-level collapse solver.
    "post-c8-next-bracket-key-cut-20260306": {
        16: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=85.0,
            max_fast_p50_ratio=2.0,
            min_fast_equality_rate_when_both_ok=0.9,
        ),
        32: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=170.0,
            max_fast_p50_ratio=0.9,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        64: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=70.0,
            max_fast_p50_ratio=0.6,
            min_fast_equality_rate_when_both_ok=0.8,
        ),
        128: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=220.0,
            max_fast_p50_ratio=0.2,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        256: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=325.0,
            max_fast_p50_ratio=0.25,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
    },
    # Historical synthetic baseline kept for reference after the runtime fix.
    "post-parity-sweep-20260306b": {
        16: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=60.0,
            max_fast_p50_ratio=2.5,
            min_fast_equality_rate_when_both_ok=0.9,
        ),
        32: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=80.0,
            max_fast_p50_ratio=0.5,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        64: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=40.0,
            max_fast_p50_ratio=0.5,
            min_fast_equality_rate_when_both_ok=0.8,
        ),
        128: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=220.0,
            max_fast_p50_ratio=0.2,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
        256: BenchmarkSLA(
            min_fast_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_fast_p95_ms=325.0,
            max_fast_p50_ratio=0.25,
            min_fast_equality_rate_when_both_ok=1.0,
        ),
    }
}


def percentile(values: Sequence[float], percentile_value: float) -> float:
    """Return a simple rounded-rank percentile for a timing series."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * percentile_value))
    return ordered[index]


def parse_bbp_pairings_output(output_text: str) -> list[list[str | None]]:
    """Parse bbpPairings `-p` output into normalized unordered pairings."""
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("bbpPairings output is empty")

    header = lines[0].split()
    if len(header) != 1 or not header[0].isdigit():
        raise ValueError("bbpPairings output header must be a round number")

    normalized: list[list[str | None]] = []
    for line in lines[1:]:
        pair = line.split()
        if len(pair) != 2 or not pair[0].isdigit() or not pair[1].isdigit():
            raise ValueError(f"invalid bbpPairings pairing line: {line!r}")
        white_id, black_id = pair
        if black_id == "0":
            normalized.append([white_id, None])
            continue
        ordered = sorted((white_id, black_id))
        normalized.append([ordered[0], ordered[1]])

    normalized.sort(key=lambda pair: (pair[1] is None, pair[0], pair[1] or ""))
    return normalized


def portable_path_str(path: str | Path) -> str:
    """Render paths under the current home directory with a `~/` prefix."""

    path_obj = Path(path).expanduser()
    path_text = str(path_obj)
    if not path_obj.is_absolute():
        return path_text

    try:
        relative = path_obj.relative_to(Path.home())
    except ValueError:
        return path_text

    if not relative.parts:
        return "~"
    return f"~/{relative.as_posix()}"


def current_python_executable() -> str:
    """Return the current Python interpreter used for this process."""

    executable = sys.executable
    if executable:
        return executable

    discovered = shutil.which("python3")
    if discovered is None:
        raise RuntimeError("python3 executable not found")
    return discovered


def build_pythonpath_env(
    *entries: str | Path,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an environment with the given entries prepended to `PYTHONPATH`."""

    env = dict(os.environ if base_env is None else base_env)
    python_path_entries = [str(Path(entry)) for entry in entries]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        python_path_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(python_path_entries)
    return env


def discover_bbp_executable() -> Path | None:
    """Return the local bbpPairings executable if it can be discovered.

    Resolution order:
    1. `SWISSPAIRING_BBP_EXECUTABLE`
    2. `BBP_PAIRINGS_EXE` (legacy name kept for compatibility)
    3. `~/bbpPairings/bbpPairings.exe`
    4. executable found on `PATH`
    """

    for env_name in ("SWISSPAIRING_BBP_EXECUTABLE", "BBP_PAIRINGS_EXE"):
        env_value = os.environ.get(env_name)
        if env_value:
            return Path(env_value).expanduser()

    home_default = Path.home() / "bbpPairings" / "bbpPairings.exe"
    if home_default.exists():
        return home_default

    for candidate in ("bbpPairings.exe", "bbpPairings"):
        discovered = shutil.which(candidate)
        if discovered:
            return Path(discovered)
    return None


def build_trf_unplayed_games_by_player_id(trf: Any) -> dict[int, int]:
    """Count unplayed games for each player from a parsed TRF snapshot.

    `XXR` stores the next round number, so completed rounds equal
    `number_of_rounds - 1` for the snapshot currently being paired. For [C9],
    only actually played games count; byes and forfeits remain unplayed games.
    """

    x_section = getattr(trf, "x_section", None)
    completed_rounds = max(int(getattr(x_section, "number_of_rounds", 0)) - 1, 0)
    counts: dict[int, int] = {}

    for section in cast(Sequence[Any], getattr(trf, "player_sections", ())):
        player_id = int(section.starting_number)
        results = cast(Sequence[Any], section.results)
        played_games = sum(
            int(
                getattr(getattr(result, "result", None), "value", None)
                in _PLAYED_TRF_RESULT_VALUES
            )
            for result in results
        )
        counts[player_id] = max(completed_rounds - played_games, 0)

    return counts


def py4swiss_runtime_probe(
    python_executable: str,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    """Return whether the given interpreter can import py4swiss."""
    probe = subprocess.run(
        [python_executable, "-c", "import py4swiss; print(py4swiss.__file__)"],
        check=False,
        capture_output=True,
        text=True,
        env=cast(Any, env),
    )
    if probe.returncode == 0:
        return True, probe.stdout.strip() or "py4swiss import succeeded"

    message = probe.stderr.strip() or probe.stdout.strip()
    if not message:
        message = "py4swiss import failed without stderr output"
    return False, message


def case_swisspairing_result(
    case_payload: Mapping[str, Any],
    mode: str,
) -> dict[str, Any] | None:
    """Extract a swisspairing mode payload from a merged case report."""
    if mode == "fast":
        value = case_payload.get("swisspairing_fast") or case_payload.get("swisspairing")
        return _as_payload_dict(value)
    if mode == "strict":
        return _as_payload_dict(case_payload.get("swisspairing_strict"))
    raise ValueError(f"unknown mode: {mode}")


def case_pairings_equal(case_payload: Mapping[str, Any], mode: str) -> bool | None:
    """Extract equality flag for the requested swisspairing mode."""
    if mode == "fast":
        value = case_payload.get("pairings_equal_fast", case_payload.get("pairings_equal"))
    elif mode == "strict":
        value = case_payload.get("pairings_equal_strict")
    else:
        raise ValueError(f"unknown mode: {mode}")
    return value if isinstance(value, bool) else None


def build_benchmark_summary(
    payloads: Sequence[Mapping[str, Any]],
    *,
    total_cases: int,
) -> dict[str, Any]:
    """Build aggregate benchmark metrics from per-case payloads."""
    py4_available = [payload for payload in payloads if "py4swiss" in payload]
    py4_ok = [payload for payload in py4_available if payload["py4swiss"]["ok"]]
    sp_fast_ok = [
        payload
        for payload in payloads
        if (case_swisspairing_result(payload, "fast") or {}).get("ok")
    ]
    sp_strict_ok = [
        payload
        for payload in payloads
        if (case_swisspairing_result(payload, "strict") or {}).get("ok")
    ]

    both_ok_fast = [
        payload
        for payload in payloads
        if ("py4swiss" in payload and payload["py4swiss"]["ok"])
        and (case_swisspairing_result(payload, "fast") or {}).get("ok")
    ]
    both_ok_strict = [
        payload
        for payload in payloads
        if ("py4swiss" in payload and payload["py4swiss"]["ok"])
        and (case_swisspairing_result(payload, "strict") or {}).get("ok")
    ]
    equal_fast_ok = [
        payload for payload in both_ok_fast if case_pairings_equal(payload, "fast") is True
    ]
    equal_strict_ok = [
        payload for payload in both_ok_strict if case_pairings_equal(payload, "strict") is True
    ]

    py4_timings = [timing for payload in py4_ok for timing in payload["py4swiss"]["timings_ms"]]
    sp_fast_timings = [
        timing
        for payload in sp_fast_ok
        for timing in (case_swisspairing_result(payload, "fast") or {}).get("timings_ms", [])
    ]
    sp_strict_timings = [
        timing
        for payload in sp_strict_ok
        for timing in (case_swisspairing_result(payload, "strict") or {}).get("timings_ms", [])
    ]

    fast_runner_error_count = len(
        [payload for payload in payloads if payload.get("runner_error_fast")]
    )
    strict_runner_error_count = len(
        [payload for payload in payloads if payload.get("runner_error_strict")]
    )
    any_runner_error_count = len(
        [
            payload
            for payload in payloads
            if payload.get("runner_error")
            or payload.get("runner_error_fast")
            or payload.get("runner_error_strict")
        ]
    )

    summary: dict[str, Any] = {
        "cases_total": total_cases,
        "cases_executed": total_cases - any_runner_error_count,
        "cases_executed_fast": total_cases - fast_runner_error_count,
        "cases_executed_strict": total_cases - strict_runner_error_count,
        "cases_runner_error": any_runner_error_count,
        "cases_runner_error_fast": fast_runner_error_count,
        "cases_runner_error_strict": strict_runner_error_count,
        "cases_both_ok_fast": len(both_ok_fast),
        "cases_both_ok_strict": len(both_ok_strict),
        "runner_error_rate": any_runner_error_count / total_cases if total_cases else 0.0,
        "runner_error_rate_fast": fast_runner_error_count / total_cases if total_cases else 0.0,
        "runner_error_rate_strict": (
            strict_runner_error_count / total_cases if total_cases else 0.0
        ),
        "py4swiss_success_rate": len(py4_ok) / total_cases if total_cases else 0.0,
        "swisspairing_fast_success_rate": len(sp_fast_ok) / total_cases if total_cases else 0.0,
        "swisspairing_strict_success_rate": (
            len(sp_strict_ok) / total_cases if total_cases else 0.0
        ),
        "pairing_equal_rate_fast_when_both_ok": (
            len(equal_fast_ok) / len(both_ok_fast) if both_ok_fast else 0.0
        ),
        "pairing_equal_rate_strict_when_both_ok": (
            len(equal_strict_ok) / len(both_ok_strict) if both_ok_strict else 0.0
        ),
        "pairing_equal_rate_fast_over_all_cases": (
            len(equal_fast_ok) / total_cases if total_cases else 0.0
        ),
        "pairing_equal_rate_strict_over_all_cases": (
            len(equal_strict_ok) / total_cases if total_cases else 0.0
        ),
        "py4swiss_p50_ms": percentile(py4_timings, 0.50),
        "py4swiss_p95_ms": percentile(py4_timings, 0.95),
        "swisspairing_fast_p50_ms": percentile(sp_fast_timings, 0.50),
        "swisspairing_fast_p95_ms": percentile(sp_fast_timings, 0.95),
        "swisspairing_strict_p50_ms": percentile(sp_strict_timings, 0.50),
        "swisspairing_strict_p95_ms": percentile(sp_strict_timings, 0.95),
    }

    if summary["py4swiss_p50_ms"] > 0:
        summary["p50_ratio_fast_over_py4swiss"] = (
            summary["swisspairing_fast_p50_ms"] / summary["py4swiss_p50_ms"]
            if sp_fast_timings
            else None
        )
        summary["p50_ratio_strict_over_py4swiss"] = (
            summary["swisspairing_strict_p50_ms"] / summary["py4swiss_p50_ms"]
            if sp_strict_timings
            else None
        )
    else:
        summary["p50_ratio_fast_over_py4swiss"] = None
        summary["p50_ratio_strict_over_py4swiss"] = None

    summary["swisspairing_success_rate"] = summary["swisspairing_fast_success_rate"]
    summary["pairing_equal_rate_when_both_ok"] = summary["pairing_equal_rate_fast_when_both_ok"]
    summary["swisspairing_p50_ms"] = summary["swisspairing_fast_p50_ms"]
    summary["swisspairing_p95_ms"] = summary["swisspairing_fast_p95_ms"]
    summary["p50_ratio_swisspairing_over_py4swiss"] = summary["p50_ratio_fast_over_py4swiss"]

    return summary


def evaluate_benchmark_sla(summary: Mapping[str, Any], sla: BenchmarkSLA) -> list[str]:
    """Return human-readable SLA violations for a benchmark summary."""
    failures: list[str] = []

    if sla.min_fast_success_rate is not None:
        observed = float(summary["swisspairing_fast_success_rate"])
        if observed < sla.min_fast_success_rate:
            failures.append(
                f"fast success rate {observed:.3f} is below minimum {sla.min_fast_success_rate:.3f}"
            )

    if sla.max_runner_error_rate is not None:
        observed = float(summary["runner_error_rate"])
        if observed > sla.max_runner_error_rate:
            failures.append(
                f"runner error rate {observed:.3f} exceeds maximum {sla.max_runner_error_rate:.3f}"
            )

    if sla.max_fast_p95_ms is not None:
        observed = float(summary["swisspairing_fast_p95_ms"])
        if observed > sla.max_fast_p95_ms:
            failures.append(
                f"fast p95 {observed:.2f}ms exceeds maximum {sla.max_fast_p95_ms:.2f}ms"
            )

    if sla.max_fast_p50_ratio is not None:
        observed = summary["p50_ratio_fast_over_py4swiss"]
        if observed is None:
            failures.append("fast p50 ratio is unavailable (py4swiss p50 is zero)")
        elif float(observed) > sla.max_fast_p50_ratio:
            failures.append(
                f"fast p50 ratio {float(observed):.3f}x exceeds maximum "
                f"{sla.max_fast_p50_ratio:.3f}x"
            )

    if sla.min_fast_equality_rate_when_both_ok is not None:
        observed = float(summary["pairing_equal_rate_fast_when_both_ok"])
        if observed < sla.min_fast_equality_rate_when_both_ok:
            failures.append(
                "fast equality rate when both ok "
                f"{observed:.3f} is below minimum "
                f"{sla.min_fast_equality_rate_when_both_ok:.3f}"
            )

    return failures


def benchmark_sla_to_dict(sla: BenchmarkSLA) -> dict[str, float | None]:
    """Serialize an SLA dataclass for JSON output."""
    return cast(dict[str, float | None], asdict(sla))


def _as_payload_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None
