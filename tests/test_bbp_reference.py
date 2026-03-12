"""Checked-in Dutch reference fixtures imported from bbpPairings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from swisspairing.benchmarking import (
    build_pythonpath_env,
    discover_bbp_executable,
    parse_bbp_pairings_output,
    py4swiss_runtime_probe,
)

FIXTURES_DIRECTORY = Path(__file__).parent / "reference_fixtures" / "bbp"
RUNNER_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "reference_compare_case_runner.py"
)


def _build_runner_env() -> dict[str, str]:
    return build_pythonpath_env(Path(__file__).parent.parent / "src")


def _has_py4swiss_runtime() -> bool:
    ok, _ = py4swiss_runtime_probe(sys.executable, env=_build_runner_env())
    return ok


def _bbp_executable() -> Path:
    discovered = discover_bbp_executable()
    if discovered is None:
        return Path("~/bbpPairings/bbpPairings.exe").expanduser()
    return discovered


def _has_bbp_executable() -> bool:
    return _bbp_executable().exists()


def _run_fixture(name: str) -> dict[str, Any]:
    fixture_path = FIXTURES_DIRECTORY / f"{name}.trf"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--trf",
            str(fixture_path),
            "--warmup",
            "0",
            "--repeats",
            "1",
            "--bbp-executable",
            str(_bbp_executable()),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
        env=_build_runner_env(),
    )
    return json.loads(completed.stdout)


def _expected_pairings(name: str) -> list[list[str | None]]:
    return parse_bbp_pairings_output(
        (FIXTURES_DIRECTORY / f"{name}.output.expected").read_text(encoding="utf-8")
    )


def _swisspairing_pairings(payload: dict[str, Any]) -> list[list[str | None]]:
    swisspairing = cast(dict[str, Any], payload["swisspairing"])
    return cast(list[list[str | None]], swisspairing["pairings"])


pytestmark = pytest.mark.skipif(
    not (_has_py4swiss_runtime() and _has_bbp_executable()),
    reason=(
        "active Python interpreter or bbpPairings runtime unavailable for imported "
        "reference fixtures"
    ),
)


def test_bbp_reference_dutch_2025_c5_matches_bbp_and_expected_output() -> None:
    payload = _run_fixture("dutch_2025_C5")

    assert payload["reference_pairings_equal"] is False
    assert payload["pairings_equal_vs_bbp"] is True
    assert payload["pairings_equal_vs_py4swiss"] is False
    assert _swisspairing_pairings(payload) == _expected_pairings("dutch_2025_C5")


def test_bbp_reference_dutch_2025_c9_matches_both_references_and_expected_output() -> None:
    payload = _run_fixture("dutch_2025_C9")

    assert payload["reference_pairings_equal"] is True
    assert payload["pairings_equal_vs_bbp"] is True
    assert payload["pairings_equal_vs_py4swiss"] is True
    assert _swisspairing_pairings(payload) == _expected_pairings("dutch_2025_C9")


def test_bbp_reference_issue_7_is_legacy_divergence_fixture() -> None:
    payload = _run_fixture("issue_7")

    # BBP issue 7 was opened in 2020, well before the 2026 Dutch ruleset.
    # Keep it checked in as a legacy diagnostic because the current references
    # still split on it, but do not treat it as a gating 2026 conformance case.
    assert payload["reference_pairings_equal"] is False
    assert payload["bbp"]["pairings"] == _expected_pairings("issue_7")
