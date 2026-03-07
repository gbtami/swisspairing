"""Golden comparisons against py4swiss Dutch pairings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from swisspairing.benchmarking import build_pythonpath_env, py4swiss_runtime_probe

GOLDEN_DIRECTORY = Path(__file__).parent / "golden"
FIXTURES_DIRECTORY = GOLDEN_DIRECTORY / "fixtures"
RUNNER_PATH = GOLDEN_DIRECTORY / "py4swiss_compare_runner.py"

def _build_runner_env() -> dict[str, str]:
    return build_pythonpath_env(Path(__file__).parent.parent / "src")


def _has_py4swiss_runtime() -> bool:
    ok, _ = py4swiss_runtime_probe(sys.executable, env=_build_runner_env())
    return ok


def _run_fixture(name: str) -> dict[str, object]:
    fixture_path = FIXTURES_DIRECTORY / name
    completed = subprocess.run(
        [sys.executable, str(RUNNER_PATH), str(fixture_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=_build_runner_env(),
    )
    return json.loads(completed.stdout)


pytestmark = pytest.mark.skipif(
    not _has_py4swiss_runtime(),
    reason="active Python interpreter does not provide py4swiss runtime",
)


def test_py4swiss_golden_parity_lower_favored() -> None:
    payload = _run_fixture("dutch_e2_both_absolute_lower_favored.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]


def test_py4swiss_golden_parity_no_legal_pairings_odd() -> None:
    payload = _run_fixture("no_legal_pairings_odd.trf")
    assert payload["py4swiss_error"] == "PairingError"
    assert payload["swisspairing_error"] == "PairingError"


def test_py4swiss_golden_parity_d2_criterion_d() -> None:
    payload = _run_fixture("dutch_d2_criterion_d.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]


def test_py4swiss_golden_parity_e2_higher_favored() -> None:
    payload = _run_fixture("dutch_e2_both_absolute_higher_favored.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]


def test_py4swiss_golden_parity_no_legal_pairings_even() -> None:
    payload = _run_fixture("no_legal_pairings.trf")
    assert payload["py4swiss_error"] == "PairingError"
    assert payload["swisspairing_error"] == "PairingError"


def test_py4swiss_golden_parity_late_entries_black() -> None:
    payload = _run_fixture("burstein_late_entries_black.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]


def test_py4swiss_golden_parity_late_entries_default_color() -> None:
    payload = _run_fixture("burstein_late_entries.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]


def test_py4swiss_golden_parity_bye_for_high_tpn() -> None:
    payload = _run_fixture("dubov_bye_for_high_tpn.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]


def test_py4swiss_golden_parity_invalid_code_tolerated() -> None:
    payload = _run_fixture("invalid_code.trf")
    assert payload["py4swiss_error"] is None
    assert payload["swisspairing_error"] is None
    assert payload["py4swiss_pairings"] == payload["swisspairing_pairings"]
