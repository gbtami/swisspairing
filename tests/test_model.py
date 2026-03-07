"""Unit tests for the pairing domain model."""

from swisspairing.model import FloatKind, PlayerState


def test_color_difference_counts_white_minus_black() -> None:
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("white", "black", "white", "white"),
    )
    assert player.color_difference == 2


def test_absolute_preference_from_positive_color_difference() -> None:
    # C.04.3 section 1.7.1: color difference > +1 gives absolute black preference.
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("white", "white", "white", "black"),
    )
    assert player.absolute_color_preference == "black"


def test_absolute_preference_from_negative_color_difference() -> None:
    # C.04.3 section 1.7.1: color difference < -1 gives absolute white preference.
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("black", "black", "black", "white"),
    )
    assert player.absolute_color_preference == "white"


def test_absolute_preference_from_last_two_whites() -> None:
    # C.04.3 section 1.7.1: two consecutive same colors imply absolute opposite preference.
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("black", "white", "white"),
    )
    assert player.absolute_color_preference == "black"


def test_absolute_preference_from_last_two_blacks() -> None:
    # C.04.3 section 1.7.1: two consecutive same colors imply absolute opposite preference.
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("white", "black", "black"),
    )
    assert player.absolute_color_preference == "white"


def test_absolute_preference_none_without_absolute_conditions() -> None:
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=3,
        color_history=("white", "black", "white", "black"),
    )
    assert player.absolute_color_preference is None


def test_strong_preference_when_color_difference_is_plus_one() -> None:
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=2,
        color_history=("white", "black", "white"),
    )
    assert player.strong_color_preference == "black"


def test_mild_preference_when_color_difference_is_zero() -> None:
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=2,
        color_history=("white", "black"),
    )
    assert player.mild_color_preference == "white"


def test_color_preference_priority_absolute_then_strong_then_mild() -> None:
    absolute = PlayerState(
        player_id="a",
        pairing_no=1,
        score=2,
        color_history=("white", "white"),
    )
    strong = PlayerState(
        player_id="b",
        pairing_no=2,
        score=2,
        color_history=("white", "black", "white"),
    )
    mild = PlayerState(
        player_id="c",
        pairing_no=3,
        score=2,
        color_history=("white", "black"),
    )
    assert absolute.color_preference == "black"
    assert strong.color_preference == "black"
    assert mild.color_preference == "white"


def test_had_float_reports_recent_rounds() -> None:
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=2,
        float_history=(FloatKind.NONE, FloatKind.UP, FloatKind.DOWN),
    )
    assert player.had_float(rounds_ago=1, kind=FloatKind.DOWN)
    assert player.had_float(rounds_ago=2, kind=FloatKind.UP)
    assert not player.had_float(rounds_ago=3, kind=FloatKind.DOWN)


def test_forbidden_opponents_defaults_to_empty_set() -> None:
    player = PlayerState(
        player_id="p1",
        pairing_no=1,
        score=2,
    )
    assert player.forbidden_opponents == frozenset()
