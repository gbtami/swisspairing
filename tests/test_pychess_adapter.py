"""Tests for pychess integration adapter helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import swisspairing.pychess_adapter as pychess_adapter
from swisspairing.model import Pairing, PairingResult
from swisspairing.pychess_adapter import (
    PychessPairingPlan,
    PychessPlayerSnapshot,
    build_player_states_from_snapshots,
    map_plan_to_users,
    pair_snapshots_dutch,
    pair_snapshots_dutch_exact,
)


@dataclass(frozen=True, slots=True)
class _User:
    username: str


def test_build_player_states_rejects_duplicate_usernames() -> None:
    snapshots = (
        PychessPlayerSnapshot(username="alice", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="alice", pairing_no=2, score=20),
    )
    with pytest.raises(ValueError, match="usernames"):
        build_player_states_from_snapshots(snapshots)


def test_build_player_states_derives_topscorer_or_opponent_marker() -> None:
    snapshots = (
        PychessPlayerSnapshot(username="top", pairing_no=1, score=30, is_top_scorer=True),
        PychessPlayerSnapshot(
            username="opp",
            pairing_no=2,
            score=20,
            opponents=frozenset({"top"}),
        ),
        PychessPlayerSnapshot(username="other", pairing_no=3, score=20),
    )
    states = build_player_states_from_snapshots(snapshots)
    by_id = {state.player_id: state for state in states}

    assert by_id["top"].is_topscorer_or_opponent
    assert by_id["opp"].is_topscorer_or_opponent
    assert not by_id["other"].is_topscorer_or_opponent


def test_build_player_states_preserves_full_point_unplayed_round_marker() -> None:
    snapshots = (
        PychessPlayerSnapshot(
            username="player",
            pairing_no=1,
            score=30,
            had_full_point_unplayed_round=True,
        ),
    )

    (state,) = build_player_states_from_snapshots(snapshots)

    assert state.had_full_point_unplayed_round is True


def test_pair_snapshots_dutch_returns_pairings_and_bye() -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
        PychessPlayerSnapshot(username="p3", pairing_no=3, score=10),
    )
    plan = pair_snapshots_dutch(snapshots)

    assert plan.pairings == (("p1", "p2"),)
    assert plan.bye_usernames == ("p3",)


def test_pair_snapshots_dutch_reads_sequential_search_limit_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.setenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", "9")
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", fake_pair_round_dutch)

    plan = pair_snapshots_dutch(snapshots)
    assert captured["limit"] == 9
    assert captured["initial_color"] == "white"
    assert plan.pairings == (("p1", "p2"),)


def test_pair_snapshots_dutch_limit_env_overrides_pairing_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.setenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", "9")
    monkeypatch.setenv("SWISSPAIRING_PAIRING_MODE", "strict")
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", fake_pair_round_dutch)

    pair_snapshots_dutch(snapshots)
    assert captured["limit"] == 9
    assert captured["initial_color"] == "white"


def test_pair_snapshots_dutch_defaults_to_fast_mode_limit_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.delenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", raising=False)
    monkeypatch.delenv("SWISSPAIRING_PAIRING_MODE", raising=False)
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", fake_pair_round_dutch)

    pair_snapshots_dutch(snapshots)
    assert captured["limit"] == 6
    assert captured["initial_color"] == "white"


def test_pair_snapshots_dutch_strict_mode_disables_default_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.delenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", raising=False)
    monkeypatch.setenv("SWISSPAIRING_PAIRING_MODE", "strict")
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", fake_pair_round_dutch)

    pair_snapshots_dutch(snapshots)
    assert captured["limit"] is None
    assert captured["initial_color"] == "white"


def test_pair_snapshots_dutch_exact_mode_uses_exact_round_solver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def unexpected_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        del sequential_search_max_players, initial_color
        raise AssertionError("exact mode should not route through pair_round_dutch")

    def fake_pair_round_dutch_exact(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.delenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", raising=False)
    monkeypatch.setenv("SWISSPAIRING_PAIRING_MODE", "exact")
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", unexpected_pair_round_dutch)
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch_exact", fake_pair_round_dutch_exact)

    plan = pair_snapshots_dutch(snapshots)

    assert captured["limit"] is None
    assert captured["initial_color"] == "white"
    assert plan.pairings == (("p1", "p2"),)


def test_pair_snapshots_dutch_explicit_limit_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.setenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", "9")
    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", fake_pair_round_dutch)

    pair_snapshots_dutch(snapshots, sequential_search_max_players=7)
    assert captured["limit"] == 7
    assert captured["initial_color"] == "white"


def test_pair_snapshots_dutch_forwards_initial_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.setattr(pychess_adapter, "pair_round_dutch", fake_pair_round_dutch)

    pair_snapshots_dutch(snapshots, initial_color="black")

    assert captured["limit"] == 6
    assert captured["initial_color"] == "black"


def test_pair_snapshots_dutch_rejects_invalid_sequential_search_limit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    monkeypatch.setenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", "not-a-number")

    with pytest.raises(ValueError, match="SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS"):
        pair_snapshots_dutch(snapshots)


def test_pair_snapshots_dutch_rejects_invalid_pairing_mode_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    monkeypatch.delenv("SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS", raising=False)
    monkeypatch.setenv("SWISSPAIRING_PAIRING_MODE", "turbo")

    with pytest.raises(ValueError, match="SWISSPAIRING_PAIRING_MODE"):
        pair_snapshots_dutch(snapshots)


def test_pair_snapshots_dutch_exact_wrapper_uses_exact_round_solver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=30),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=20),
    )
    captured: dict[str, int | str | None] = {}

    def fake_pair_round_dutch_exact(
        _states: tuple[object, ...],
        *,
        sequential_search_max_players: int | None = None,
        initial_color: str = "white",
    ) -> PairingResult:
        captured["limit"] = sequential_search_max_players
        captured["initial_color"] = initial_color
        return PairingResult(
            pairings=(Pairing(white_id="p1", black_id="p2"),),
            unpaired_ids=(),
        )

    monkeypatch.setattr(pychess_adapter, "pair_round_dutch_exact", fake_pair_round_dutch_exact)

    plan = pair_snapshots_dutch_exact(
        snapshots,
        sequential_search_max_players=9,
        initial_color="black",
    )

    assert captured == {"limit": 9, "initial_color": "black"}
    assert plan.pairings == (("p1", "p2"),)


def test_map_plan_to_users_maps_user_instances() -> None:
    users = (_User("alice"), _User("bob"), _User("carol"))
    plan = PychessPairingPlan(
        pairings=(("alice", "bob"),),
        bye_usernames=("carol",),
    )
    pairings, byes = map_plan_to_users(plan, users)

    assert pairings == ((users[0], users[1]),)
    assert byes == (users[2],)


def test_map_plan_to_users_raises_for_unknown_user() -> None:
    users = (_User("alice"), _User("bob"))
    plan = PychessPairingPlan(
        pairings=(("alice", "carol"),),
        bye_usernames=(),
    )
    with pytest.raises(ValueError, match="unknown"):
        map_plan_to_users(plan, users)
