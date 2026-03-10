"""Checked Lichess TRF reference fixtures (normalized TRF16 exports)."""

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
    discover_javafo_jar,
    javafo_runtime_probe,
    py4swiss_runtime_probe,
)

FIXTURES_DIRECTORY = Path(__file__).resolve().parents[1] / "benchmarks" / "fixtures" / "lichess"
RUNNER_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "reference_compare_case_runner.py"
)


def _build_runner_env() -> dict[str, str]:
    return build_pythonpath_env(Path(__file__).resolve().parents[1] / "src")


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


def _javafo_jar() -> Path:
    discovered = discover_javafo_jar()
    if discovered is None:
        return Path("~/JaVaFo/javafo.jar").expanduser()
    return discovered


def _has_javafo_runtime() -> bool:
    jar = _javafo_jar()
    if not jar.exists():
        return False
    ok, _ = javafo_runtime_probe(jar)
    return ok


def _run_fixture(filename: str, *, mode: str) -> dict[str, Any]:
    fixture_path = FIXTURES_DIRECTORY / filename
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
            "--swisspairing-mode",
            mode,
            "--bbp-executable",
            str(_bbp_executable()),
            "--javafo-jar",
            str(_javafo_jar()),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        env=_build_runner_env(),
    )
    return json.loads(completed.stdout)


pytestmark = pytest.mark.skipif(
    not (_has_py4swiss_runtime() and _has_bbp_executable() and _has_javafo_runtime()),
    reason=(
        "active Python interpreter, bbpPairings runtime, or JaVaFo runtime unavailable "
        "for Lichess reference fixtures"
    ),
)


@pytest.mark.parametrize(
    "filename",
    [
        "lichess_swiss_2026.02.14_cY3wR140_weekly-agca-prize-50-dollars.trf",
        "lichess_swiss_2026.02.28_KQYWuizM_weekly-agca-prize-50-dollars.trf",
        "lichess_swiss_2026.03.03_7TYuxURK_bullet-increment.trf",
    ],
)
def test_lichess_reference_py4swiss_and_javafo_agree(filename: str) -> None:
    payload = _run_fixture(filename, mode="fast")

    assert payload["py4swiss"]["ok"] is True
    assert payload["javafo"]["ok"] is True
    assert payload["bbp"]["ok"] is True
    assert payload["reference_pairings_equal_vs_javafo"] is True


def test_lichess_reference_bullet_increment_fast_matches_bbp_not_py4swiss_or_javafo() -> None:
    payload = _run_fixture("lichess_swiss_2026.03.03_7TYuxURK_bullet-increment.trf", mode="fast")

    assert payload["pairings_equal_vs_py4swiss"] is False
    assert payload["pairings_equal_vs_javafo"] is False
    assert payload["pairings_equal_vs_bbp"] is True


@pytest.mark.parametrize("mode", ["fast", "strict"])
def test_lichess_reference_weekly_20260214_matches_bbp_not_py4swiss_or_javafo(mode: str) -> None:
    payload = _run_fixture(
        "lichess_swiss_2026.02.14_cY3wR140_weekly-agca-prize-50-dollars.trf",
        mode=mode,
    )

    assert payload["pairings_equal_vs_py4swiss"] is False
    assert payload["pairings_equal_vs_javafo"] is False
    assert payload["pairings_equal_vs_bbp"] is True


def test_lichess_reference_bullet_increment_strict_matches_bbp_not_py4swiss_or_javafo() -> None:
    payload = _run_fixture("lichess_swiss_2026.03.03_7TYuxURK_bullet-increment.trf", mode="strict")

    assert payload["pairings_equal_vs_py4swiss"] is False
    assert payload["pairings_equal_vs_javafo"] is False
    assert payload["pairings_equal_vs_bbp"] is True


@pytest.mark.parametrize("mode", ["fast", "strict"])
def test_lichess_reference_weekly_20260228_matches_bbp_not_py4swiss_or_javafo(mode: str) -> None:
    payload_fast = _run_fixture(
        "lichess_swiss_2026.02.28_KQYWuizM_weekly-agca-prize-50-dollars.trf",
        mode=mode,
    )

    swisspairing = cast(dict[str, Any], payload_fast["swisspairing"])
    assert swisspairing["ok"] is True
    assert payload_fast["pairings_equal_vs_py4swiss"] is False
    assert payload_fast["pairings_equal_vs_javafo"] is False
    assert payload_fast["pairings_equal_vs_bbp"] is True
