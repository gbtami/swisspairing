from __future__ import annotations

from datetime import UTC, datetime

from swisspairing.pychess_dump import (
    PychessTournamentPairingRecord,
    PychessTournamentPlayerRecord,
    group_pairings_by_round,
    infer_scoring_values,
    point_entry_at,
    point_value,
    result_outcome_for_color,
    select_snapshot_completed_rounds,
)


def _player(
    *,
    username: str,
    points_entries: tuple[int | str | tuple[object, ...], ...],
    rating: int = 1500,
) -> PychessTournamentPlayerRecord:
    return PychessTournamentPlayerRecord(
        tournament_id="t1",
        username=username,
        rating=rating,
        points_entries=points_entries,
        score_total=0,
        is_active=True,
    )


def _pairing(
    *,
    white: str,
    black: str,
    result_code: str,
    hour: int,
) -> PychessTournamentPairingRecord:
    return PychessTournamentPairingRecord(
        tournament_id="t1",
        white_username=white,
        black_username=black,
        result_code=result_code,
        played_at=datetime(2026, 3, 5, hour, 0, tzinfo=UTC),
    )


def test_group_pairings_by_round_keeps_player_unique_per_round() -> None:
    pairings = (
        _pairing(white="p1", black="p2", result_code="a", hour=10),
        _pairing(white="p3", black="p4", result_code="c", hour=10),
        _pairing(white="p1", black="p3", result_code="b", hour=11),
    )

    rounds = group_pairings_by_round(pairings)

    assert len(rounds) == 2
    assert rounds[0] == (pairings[0], pairings[1])
    assert rounds[1] == (pairings[2],)


def test_infer_scoring_values_from_pointsheets() -> None:
    players = {
        "p1": _player(username="p1", points_entries=((2, 1), (1, 1))),
        "p2": _player(username="p2", points_entries=((0, 1), (1, 1))),
        "p3": _player(username="p3", points_entries=((1, 1), (2, 1))),
        "p4": _player(username="p4", points_entries=((1, 1), (0, 1))),
    }
    rounds = (
        (
            _pairing(white="p1", black="p2", result_code="a", hour=10),
            _pairing(white="p3", black="p4", result_code="c", hour=10),
        ),
        (
            _pairing(white="p1", black="p3", result_code="c", hour=11),
            _pairing(white="p2", black="p4", result_code="a", hour=11),
        ),
    )

    assert infer_scoring_values(rounds, players) == (2, 1, 0)


def test_result_outcome_for_color_maps_known_codes() -> None:
    assert result_outcome_for_color("a", is_white=True) == "win"
    assert result_outcome_for_color("a", is_white=False) == "loss"
    assert result_outcome_for_color("b", is_white=True) == "loss"
    assert result_outcome_for_color("b", is_white=False) == "win"
    assert result_outcome_for_color("c", is_white=True) == "draw"
    assert result_outcome_for_color("x", is_white=True) is None


def test_point_helpers_handle_mixed_entries() -> None:
    player = _player(username="p1", points_entries=((2, 1), "-", 1))
    assert point_entry_at(player, 0) == (2, 1)
    assert point_entry_at(player, 1) == "-"
    assert point_entry_at(player, 2) == 1
    assert point_entry_at(player, 3) is None
    assert point_value((2, 1)) == 2
    assert point_value("-") is None
    assert point_value(1) == 1
    assert point_value(None) is None


def test_select_snapshot_completed_rounds_uses_latest_window() -> None:
    assert select_snapshot_completed_rounds(0, max_snapshots=3) == ()
    assert select_snapshot_completed_rounds(5, max_snapshots=0) == (1, 2, 3, 4)
    assert select_snapshot_completed_rounds(5, max_snapshots=2) == (3, 4)
    assert select_snapshot_completed_rounds(3, max_snapshots=5, min_completed_rounds=2) == (2,)
