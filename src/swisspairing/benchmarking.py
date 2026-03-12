"""Helpers for benchmark reporting, regression guardrails, and runtime probing."""

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

from swisspairing.model import Color, FloatKind

_PLAYED_TRF_RESULT_VALUES = frozenset({"1", "=", "0", "W", "D", "L"})
_NON_PAB_FULL_POINT_UNPLAYED_TRF_RESULT_VALUES = frozenset({"+", "F"})
_LENIENT_TRF_RESULT_PAIR_PATTERN = re.compile(
    r"^(?P<opponent>\d{1,4})\s+(?P<color>[wWbB-])\s+(?P<result>[+\-WDL10=HFUZwdlhfuz])$"
)
_LENIENT_TRF_SINGLE_RESULT_TOKENS = frozenset({"H", "F", "U", "Z", "-"})
_LENIENT_TRF16_XXR_MODES = frozenset({"preserve", "bbp-next-round"})


@dataclass(frozen=True, slots=True)
class BenchmarkSLA:
    """Optional benchmark guardrails for synthetic summary checks.

    These thresholds are useful for spotting accidental runtime regressions in
    the current pragmatic benchmark profiles. They are not a normative sign-off
    for exact/FIDE correctness.
    """

    min_success_rate: float | None = None
    max_runner_error_rate: float | None = None
    max_p95_ms: float | None = None
    max_p50_ratio: float | None = None
    min_equality_rate_when_both_ok: float | None = None


RECURRING_SYNTHETIC_SLA_PRESETS: dict[str, dict[int, BenchmarkSLA]] = {
    # Synthetic recurring presets are regression guardrails. Exact solver work
    # should be evaluated primarily against checked rule/corpus behavior and
    # real-world exact runtimes, not against holding these values constant.
    # The checked-in `post-bounded-c8-20260311` artifacts are historical
    # py4swiss-compare data from before the exact-only cleanup.
    "post-bounded-c8-20260311": {
        16: BenchmarkSLA(
            min_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_p95_ms=10.0,
            max_p50_ratio=1.05,
            min_equality_rate_when_both_ok=0.75,
        ),
        32: BenchmarkSLA(
            min_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_p95_ms=120.0,
            max_p50_ratio=2.6,
            min_equality_rate_when_both_ok=0.3,
        ),
        64: BenchmarkSLA(
            min_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_p95_ms=160.0,
            max_p50_ratio=0.4,
            min_equality_rate_when_both_ok=0.55,
        ),
        128: BenchmarkSLA(
            min_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_p95_ms=500.0,
            max_p50_ratio=0.6,
            min_equality_rate_when_both_ok=0.4,
        ),
        256: BenchmarkSLA(
            min_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_p95_ms=950.0,
            max_p50_ratio=0.6,
            min_equality_rate_when_both_ok=0.6,
        ),
        512: BenchmarkSLA(
            min_success_rate=1.0,
            max_runner_error_rate=0.0,
            max_p95_ms=1500.0,
            max_p50_ratio=0.3,
            min_equality_rate_when_both_ok=0.8,
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


def build_trf_float_history_by_player_id(trf: Any) -> dict[int, tuple[FloatKind, ...]]:
    """Derive per-player float history directly from parsed TRF rounds.

    The compare harness must derive this from the TRF itself instead of
    inheriting another engine's internal float bookkeeping.
    """

    x_section = getattr(trf, "x_section", None)
    scoring_point_system = getattr(x_section, "scoring_point_system", None)
    completed_rounds = max(int(getattr(x_section, "number_of_rounds", 0)) - 1, 0)
    sections = cast(Sequence[Any], getattr(trf, "player_sections", ()))
    results_by_number = {
        int(section.starting_number): tuple(cast(Sequence[Any], section.results))
        for section in sections
    }
    points_by_number = {number: 0 for number in results_by_number}
    history_by_number: dict[int, list[FloatKind]] = {number: [] for number in results_by_number}

    for round_index in range(completed_rounds):
        round_assignments = {number: FloatKind.NONE for number in results_by_number}

        for number, results in results_by_number.items():
            round_result = _trf_round_result_for_index(results, round_index)
            if round_result is None:
                continue

            opponent_number = int(getattr(round_result, "id", 0) or 0)
            color_value = _trf_round_result_color_value(round_result)

            if color_value == "w" and opponent_number != 0:
                opponent_result = _trf_round_result_for_index(
                    results_by_number.get(opponent_number, ()),
                    round_index,
                )
                if opponent_result is None:
                    continue

                if _trf_round_result_is_played(round_result) and _trf_round_result_is_played(
                    opponent_result
                ):
                    white_score = points_by_number[number]
                    black_score = points_by_number[opponent_number]
                    if white_score != black_score:
                        higher_number, lower_number = (
                            (number, opponent_number)
                            if (-white_score, number) <= (-black_score, opponent_number)
                            else (opponent_number, number)
                        )
                        round_assignments[higher_number] = FloatKind.DOWN
                        round_assignments[lower_number] = FloatKind.UP
                else:
                    for assignee_number, assignee_result in (
                        (number, round_result),
                        (opponent_number, opponent_result),
                    ):
                        if not _trf_round_result_is_played(assignee_result) and (
                            _trf_round_result_points_times_ten(
                                assignee_result,
                                scoring_point_system=scoring_point_system,
                            )
                            > 0
                        ):
                            round_assignments[assignee_number] = FloatKind.DOWN
                continue

            if opponent_number == 0 and (
                _trf_round_result_points_times_ten(
                    round_result,
                    scoring_point_system=scoring_point_system,
                )
                > 0
            ):
                round_assignments[number] = FloatKind.DOWN

        for number, history in history_by_number.items():
            history.append(round_assignments[number])
            round_result = _trf_round_result_for_index(results_by_number[number], round_index)
            if round_result is not None:
                points_by_number[number] += _trf_round_result_points_times_ten(
                    round_result,
                    scoring_point_system=scoring_point_system,
                )

    return {number: tuple(history) for number, history in history_by_number.items()}


def _trf_round_result_for_index(results: Sequence[Any], round_index: int) -> Any | None:
    if round_index < 0 or round_index >= len(results):
        return None
    return results[round_index]


def _trf_round_result_color_value(round_result: Any) -> str:
    color = getattr(round_result, "color", None)
    return cast(str, getattr(color, "value", color) or "")


def _trf_round_result_is_played(round_result: Any) -> bool:
    result = getattr(round_result, "result", None)
    is_played = getattr(result, "is_played", None)
    if callable(is_played):
        return bool(is_played())
    return getattr(result, "value", None) in _PLAYED_TRF_RESULT_VALUES


def _trf_round_result_points_times_ten(
    round_result: Any,
    *,
    scoring_point_system: Any,
) -> int:
    scoring_getter = getattr(scoring_point_system, "get_points_times_ten", None)
    if callable(scoring_getter):
        return cast(int, scoring_getter(round_result))

    result_value = getattr(getattr(round_result, "result", None), "value", None)
    if result_value in {"1", "W", "+", "F", "U"}:
        return 10
    if result_value in {"=", "D", "H"}:
        return 5
    return 0


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


def case_swisspairing_result(case_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract the swisspairing payload from a case report."""
    return _as_payload_dict(case_payload.get("swisspairing"))


def case_pairings_equal(case_payload: Mapping[str, Any]) -> bool | None:
    """Extract the swisspairing vs py4swiss equality flag from a case report."""
    value = case_payload.get("pairings_equal")
    return value if isinstance(value, bool) else None


def build_benchmark_summary(
    payloads: Sequence[Mapping[str, Any]],
    *,
    total_cases: int,
) -> dict[str, Any]:
    """Build aggregate benchmark metrics from per-case payloads."""
    py4_available = [payload for payload in payloads if "py4swiss" in payload]
    py4_ok = [payload for payload in py4_available if payload["py4swiss"]["ok"]]
    swisspairing_ok = [
        payload for payload in payloads if (case_swisspairing_result(payload) or {}).get("ok")
    ]

    both_ok = [
        payload
        for payload in payloads
        if ("py4swiss" in payload and payload["py4swiss"]["ok"])
        and (case_swisspairing_result(payload) or {}).get("ok")
    ]
    equal_ok = [payload for payload in both_ok if case_pairings_equal(payload) is True]

    py4_timings = [timing for payload in py4_ok for timing in payload["py4swiss"]["timings_ms"]]
    swisspairing_timings = [
        timing
        for payload in swisspairing_ok
        for timing in (case_swisspairing_result(payload) or {}).get("timings_ms", [])
    ]

    runner_error_count = len([payload for payload in payloads if payload.get("runner_error")])

    summary: dict[str, Any] = {
        "cases_total": total_cases,
        "cases_executed": total_cases - runner_error_count,
        "cases_runner_error": runner_error_count,
        "cases_both_ok": len(both_ok),
        "runner_error_rate": runner_error_count / total_cases if total_cases else 0.0,
        "py4swiss_success_rate": len(py4_ok) / total_cases if total_cases else 0.0,
        "swisspairing_success_rate": len(swisspairing_ok) / total_cases if total_cases else 0.0,
        "pairing_equal_rate_when_both_ok": len(equal_ok) / len(both_ok) if both_ok else 0.0,
        "pairing_equal_rate_over_all_cases": len(equal_ok) / total_cases if total_cases else 0.0,
        "py4swiss_p50_ms": percentile(py4_timings, 0.50),
        "py4swiss_p95_ms": percentile(py4_timings, 0.95),
        "swisspairing_p50_ms": percentile(swisspairing_timings, 0.50),
        "swisspairing_p95_ms": percentile(swisspairing_timings, 0.95),
    }

    if summary["py4swiss_p50_ms"] > 0:
        summary["p50_ratio_swisspairing_over_py4swiss"] = (
            summary["swisspairing_p50_ms"] / summary["py4swiss_p50_ms"]
            if swisspairing_timings
            else None
        )
    else:
        summary["p50_ratio_swisspairing_over_py4swiss"] = None

    return summary


def evaluate_benchmark_sla(summary: Mapping[str, Any], sla: BenchmarkSLA) -> list[str]:
    """Return human-readable SLA violations for a benchmark summary."""
    failures: list[str] = []

    if sla.min_success_rate is not None:
        observed = float(summary["swisspairing_success_rate"])
        if observed < sla.min_success_rate:
            failures.append(
                f"success rate {observed:.3f} is below minimum {sla.min_success_rate:.3f}"
            )

    if sla.max_runner_error_rate is not None:
        observed = float(summary["runner_error_rate"])
        if observed > sla.max_runner_error_rate:
            failures.append(
                f"runner error rate {observed:.3f} exceeds maximum {sla.max_runner_error_rate:.3f}"
            )

    if sla.max_p95_ms is not None:
        observed = float(summary["swisspairing_p95_ms"])
        if observed > sla.max_p95_ms:
            failures.append(f"p95 {observed:.2f}ms exceeds maximum {sla.max_p95_ms:.2f}ms")

    if sla.max_p50_ratio is not None:
        observed = summary["p50_ratio_swisspairing_over_py4swiss"]
        if observed is None:
            failures.append("p50 ratio is unavailable (py4swiss p50 is zero)")
        elif float(observed) > sla.max_p50_ratio:
            failures.append(
                f"p50 ratio {float(observed):.3f}x exceeds maximum {sla.max_p50_ratio:.3f}x"
            )

    if sla.min_equality_rate_when_both_ok is not None:
        observed = float(summary["pairing_equal_rate_when_both_ok"])
        if observed < sla.min_equality_rate_when_both_ok:
            failures.append(
                "equality rate when both ok "
                f"{observed:.3f} is below minimum "
                f"{sla.min_equality_rate_when_both_ok:.3f}"
            )

    return failures


def benchmark_sla_to_dict(sla: BenchmarkSLA) -> dict[str, float | None]:
    """Serialize an SLA dataclass for JSON output."""
    return cast(dict[str, float | None], asdict(sla))


def _as_payload_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None
