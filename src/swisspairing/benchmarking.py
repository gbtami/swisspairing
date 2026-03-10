"""Helpers for benchmark reporting, SLA checks, and runtime probing."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from swisspairing.model import Color

_PLAYED_TRF_RESULT_VALUES = frozenset({"1", "=", "0", "W", "D", "L"})
_NON_PAB_FULL_POINT_UNPLAYED_TRF_RESULT_VALUES = frozenset({"+", "F"})
_LENIENT_TRF_RESULT_PAIR_PATTERN = re.compile(
    r"^(?P<opponent>\d{1,4})\s+(?P<color>[wWbB-])\s+(?P<result>[+\-WDL10=HFUZwdlhfuz])$"
)
_LENIENT_TRF_SINGLE_RESULT_TOKENS = frozenset({"H", "F", "U", "Z", "-"})
_LENIENT_TRF16_XXR_MODES = frozenset({"preserve", "bbp-next-round"})


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
    },
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


def sort_pairings_for_compare(
    pairings: Sequence[Sequence[str | None]],
) -> list[list[str | None]]:
    """Return pairings in deterministic compare order without changing colors."""

    def _sort_key(pair: Sequence[str | None]) -> tuple[bool, str, str, str, str]:
        left = pair[0]
        right = pair[1]
        if left is None:
            raise ValueError("pairing compare rows must always include a white-side player id")
        if right is None:
            return True, left, left, left, ""
        first, second = sorted((left, right))
        return False, first, second, left, right

    normalized = [[pair[0], pair[1]] for pair in pairings]
    normalized.sort(key=_sort_key)
    return normalized


def build_trf_initial_color(trf: Any) -> Color:
    """Return the TRF-configured first-round color (`white` or `black`)."""
    first_round_color = getattr(
        getattr(getattr(trf, "x_section", None), "configuration", None),
        "first_round_color",
        True,
    )
    return "white" if first_round_color else "black"


def parse_bbp_pairings_output(output_text: str) -> list[list[str | None]]:
    """Parse bbpPairings `-p` output into compare-ready oriented pairings."""
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
        normalized.append([white_id, black_id])

    return sort_pairings_for_compare(normalized)


def parse_javafo_pairings_output(output_text: str) -> list[list[str | None]]:
    """Parse JaVaFo `-p` output into compare-ready oriented pairings."""
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("JaVaFo output is empty")

    header = lines[0].split()
    if len(header) != 1 or not header[0].isdigit():
        raise ValueError("JaVaFo output header must be a pair count")

    expected_pairs = int(header[0])
    normalized: list[list[str | None]] = []
    for line in lines[1:]:
        pair = line.split()
        if len(pair) != 2 or not pair[0].isdigit() or not pair[1].isdigit():
            raise ValueError(f"invalid JaVaFo pairing line: {line!r}")
        white_id, black_id = pair
        if black_id == "0":
            normalized.append([white_id, None])
            continue
        normalized.append([white_id, black_id])

    if len(normalized) != expected_pairs:
        raise ValueError(
            f"JaVaFo output expected {expected_pairs} pairs but contained {len(normalized)}"
        )

    return sort_pairings_for_compare(normalized)


def _parse_trf16_points_times_ten(points_text: str) -> int:
    """Parse a TRF16 points field and return points times ten."""
    try:
        decimal_points = Decimal(points_text)
    except InvalidOperation as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"invalid TRF points value {points_text!r}") from exc

    scaled = decimal_points * 10
    if scaled != scaled.to_integral_value():
        raise ValueError(f"TRF points value must be in tenths, got {points_text!r}")
    return int(scaled)


def _format_trf16_points(points_times_ten: int) -> str:
    """Format points-times-ten into the 4-char TRF16 points field."""
    whole = points_times_ten // 10
    tenths = abs(points_times_ten) % 10
    return f"{whole}.{tenths}"


def _normalize_lenient_trf_result_token(token: str) -> str:
    """Normalize one lenient result token into an 8-char strict TRF16 chunk."""
    compact = token.strip()
    if not compact:
        raise ValueError("empty TRF result token")

    single_token = compact.upper()
    if single_token in _LENIENT_TRF_SINGLE_RESULT_TOKENS:
        # Lichess-style single "-" means no opponent and no game in practice.
        result_value = "Z" if single_token == "-" else single_token
        return f"0000 - {result_value}"

    pair_match = _LENIENT_TRF_RESULT_PAIR_PATTERN.fullmatch(compact)
    if pair_match is None:
        raise ValueError(f"unsupported TRF result token {compact!r}")

    opponent = int(pair_match.group("opponent"))
    color = pair_match.group("color").lower()
    result = pair_match.group("result").upper()
    opponent_field = "0000" if opponent == 0 else f"{opponent:>4}"
    return f"{opponent_field} {color} {result}"


def _extract_lenient_result_tokens(blob: str) -> list[str]:
    """Split a lenient results blob into per-round tokens."""
    stripped = blob.strip()
    if not stripped:
        return []
    return [token.strip() for token in re.split(r"\s{2,}", stripped) if token.strip()]


def _normalize_lenient_player_line(
    line: str,
    *,
    rounds: int,
    fallback_rank: int,
) -> str:
    """Normalize one lenient `001` line into strict fixed-column TRF16 format."""
    if rounds < 0:
        raise ValueError("round count must be non-negative")

    padded = line.ljust(91)
    starting_number_text = padded[4:8].strip()
    if not starting_number_text.isdigit():
        raise ValueError(f"invalid starting number field in player line: {line!r}")
    starting_number = int(starting_number_text)

    sex = padded[9:10]
    title = padded[10:13]
    name = padded[14:47].strip()
    if not name:
        raise ValueError(f"missing player name in player line: {line!r}")
    federation = padded[53:56]
    fide_number = padded[57:68]
    birth_date = padded[69:79]

    rating_text = padded[47:52].strip()
    rating_field = rating_text if rating_text else ""
    if rating_field and not rating_field.isdigit():
        raise ValueError(f"invalid rating field in player line: {line!r}")

    points_text = padded[80:85].strip()
    if not points_text:
        raise ValueError(f"missing points field in player line: {line!r}")
    points_times_ten = _parse_trf16_points_times_ten(points_text)
    points_field = _format_trf16_points(points_times_ten)

    rank_text = padded[85:89].strip()
    rank_value = fallback_rank if not rank_text else int(rank_text)
    if rank_value <= 0:
        raise ValueError(f"rank must be positive in player line: {line!r}")

    raw_result_tokens = _extract_lenient_result_tokens(line[91:] if len(line) > 91 else "")
    if len(raw_result_tokens) > rounds:
        raise ValueError(
            "player line has more round tokens than XXR allows: "
            f"starting_number={starting_number} rounds={rounds} tokens={len(raw_result_tokens)}"
        )

    padded_tokens = [*raw_result_tokens, *(["Z"] * (rounds - len(raw_result_tokens)))]
    round_chunks = [_normalize_lenient_trf_result_token(token) for token in padded_tokens]

    prefix = (
        f"001 {starting_number:>4} "
        f"{sex[:1]}{title[:3]:>3} "
        f"{name[:33]:<33}"
        f"{rating_field:>5} "
        f"{federation[:3]:<3} "
        f"{fide_number[:11]:>11} "
        f"{birth_date[:10]:<10} "
        f"{points_field:>4} "
        f"{rank_value:>4}"
    )
    if not round_chunks:
        return prefix
    return f"{prefix}  {'  '.join(round_chunks)}"


def _extract_trf_round_count(lines: Sequence[str]) -> int:
    for line in lines:
        stripped = line.strip()
        if not stripped.upper().startswith("XXR"):
            continue
        tail = stripped[3:].strip()
        if not tail:
            raise ValueError("XXR field is missing round count")
        first_token = tail.split()[0]
        if not first_token.isdigit():
            raise ValueError(f"invalid XXR round count {first_token!r}")
        return int(first_token)
    raise ValueError("TRF file does not contain XXR round count")


def _transform_trf_round_count_line(line: str, *, xxr_mode: str) -> str:
    """Transform an `XXR` line according to the selected mode."""
    if xxr_mode not in _LENIENT_TRF16_XXR_MODES:
        raise ValueError(
            f"xxr_mode must be one of {sorted(_LENIENT_TRF16_XXR_MODES)!r}, got {xxr_mode!r}"
        )

    stripped = line.strip()
    if not stripped.upper().startswith("XXR"):
        return line

    parts = stripped.split()
    if len(parts) < 2 or not parts[1].isdigit():
        raise ValueError(f"invalid XXR line {line!r}")

    reported_round = int(parts[1])
    if xxr_mode == "bbp-next-round":
        reported_round += 1

    return " ".join(("XXR", str(reported_round), *parts[2:]))


def normalize_lenient_trf16_text(text: str, *, xxr_mode: str = "preserve") -> str:
    """Normalize lenient TRF16 player lines to strict fixed-column TRF16 format."""
    if xxr_mode not in _LENIENT_TRF16_XXR_MODES:
        raise ValueError(
            f"xxr_mode must be one of {sorted(_LENIENT_TRF16_XXR_MODES)!r}, got {xxr_mode!r}"
        )

    trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    rounds = _extract_trf_round_count(lines)

    normalized_lines: list[str] = []
    player_index = 0
    for line in lines:
        if line.startswith("001"):
            player_index += 1
            normalized_lines.append(
                _normalize_lenient_player_line(
                    line,
                    rounds=rounds,
                    fallback_rank=player_index,
                )
            )
            continue
        if line.strip().upper().startswith("XXR"):
            normalized_lines.append(_transform_trf_round_count_line(line, xxr_mode=xxr_mode))
            continue
        normalized_lines.append(line)

    normalized = "\n".join(normalized_lines)
    if trailing_newline:
        normalized += "\n"
    return normalized


def normalize_lenient_trf16_file(
    source_path: str | Path,
    target_path: str | Path,
    *,
    xxr_mode: str = "preserve",
) -> None:
    """Normalize a lenient TRF16 file and write the strict-form output."""
    source = Path(source_path).expanduser()
    target = Path(target_path).expanduser()
    normalized_text = normalize_lenient_trf16_text(
        source.read_text(encoding="utf-8"),
        xxr_mode=xxr_mode,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(normalized_text, encoding="utf-8")


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


def discover_javafo_jar() -> Path | None:
    """Return the local JaVaFo jar if it can be discovered.

    Resolution order:
    1. `SWISSPAIRING_JAVAFO_JAR`
    2. `JAVAFO_JAR` (legacy name kept for compatibility)
    3. `~/JaVaFo/javafo.jar`
    """

    for env_name in ("SWISSPAIRING_JAVAFO_JAR", "JAVAFO_JAR"):
        env_value = os.environ.get(env_name)
        if env_value:
            return Path(env_value).expanduser()

    home_default = Path.home() / "JaVaFo" / "javafo.jar"
    if home_default.exists():
        return home_default

    return None


def javafo_runtime_probe(javafo_jar: str | Path) -> tuple[bool, str]:
    """Return whether the given JaVaFo jar can be executed."""
    probe = subprocess.run(
        ["java", "-jar", str(Path(javafo_jar).expanduser()), "-r"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        message = probe.stdout.strip() or "JaVaFo probe succeeded"
        return True, message

    message = probe.stderr.strip() or probe.stdout.strip()
    if not message:
        message = f"JaVaFo probe failed with exit code {probe.returncode}"
    return False, message


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
                getattr(getattr(result, "result", None), "value", None) in _PLAYED_TRF_RESULT_VALUES
            )
            for result in results
        )
        counts[player_id] = max(completed_rounds - played_games, 0)

    return counts


def build_trf_had_full_point_unplayed_round_by_player_id(trf: Any) -> dict[int, bool]:
    """Return whether each player has a prior non-PAB full-point unplayed round.

    This covers FIDE Basic Rule 4 / Dutch [C2] history beyond pairing-allocated
    byes, which are already tracked separately from TRF player metadata.
    """

    flags: dict[int, bool] = {}

    for section in cast(Sequence[Any], getattr(trf, "player_sections", ())):
        player_id = int(section.starting_number)
        flags[player_id] = any(
            getattr(getattr(result, "result", None), "value", None)
            in _NON_PAB_FULL_POINT_UNPLAYED_TRF_RESULT_VALUES
            for result in cast(Sequence[Any], section.results)
        )

    return flags


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
