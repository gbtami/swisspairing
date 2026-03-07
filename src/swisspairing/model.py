"""Typed domain model for Swiss pairing.

The model is intentionally compact but explicit. It keeps only the information
needed by the current pairing core and validation tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

Color = Literal["white", "black"]


class FloatKind(StrEnum):
    """Player float markers used by later Dutch criteria layers."""

    UP = "up"
    DOWN = "down"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class PlayerState:
    """Pairing-relevant state for one participant.

    References:
    - C.04.2 section 2: Tournament Pairing Number and ranking handling.
    - C.04.3 section 1.6 and 1.7: color difference and color preference.
    - C.04.2 section 1.5: organizer-provided forbidden pair constraints.
    """

    player_id: str
    pairing_no: int
    score: int
    opponents: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    forbidden_opponents: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    color_history: tuple[Color, ...] = ()
    unplayed_games: int = 0
    had_full_point_bye: bool = False
    is_top_scorer: bool = False
    is_topscorer_or_opponent: bool = False
    float_history: tuple[FloatKind, ...] = ()
    _color_difference: int = field(init=False, repr=False, compare=False)
    _absolute_color_preference: Color | None = field(init=False, repr=False, compare=False)
    _strong_color_preference: Color | None = field(init=False, repr=False, compare=False)
    _mild_color_preference: Color | None = field(init=False, repr=False, compare=False)
    _color_preference: Color | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Precompute color-preference state used heavily during candidate scoring."""
        whites = self.color_history.count("white")
        blacks = self.color_history.count("black")
        color_difference = whites - blacks

        absolute_color_preference: Color | None = None
        if color_difference > 1:
            absolute_color_preference = "black"
        elif color_difference < -1:
            absolute_color_preference = "white"
        elif len(self.color_history) >= 2 and self.color_history[-1] == self.color_history[-2]:
            absolute_color_preference = "black" if self.color_history[-1] == "white" else "white"

        strong_color_preference: Color | None = None
        if color_difference == 1:
            strong_color_preference = "black"
        elif color_difference == -1:
            strong_color_preference = "white"

        mild_color_preference: Color | None = None
        if color_difference == 0 and self.color_history:
            mild_color_preference = "black" if self.color_history[-1] == "white" else "white"

        object.__setattr__(self, "_color_difference", color_difference)
        object.__setattr__(self, "_absolute_color_preference", absolute_color_preference)
        object.__setattr__(self, "_strong_color_preference", strong_color_preference)
        object.__setattr__(self, "_mild_color_preference", mild_color_preference)
        object.__setattr__(
            self,
            "_color_preference",
            absolute_color_preference or strong_color_preference or mild_color_preference,
        )

    @property
    def color_difference(self) -> int:
        """White games minus black games in played-game history."""
        return self._color_difference

    @property
    def absolute_color_preference(self) -> Color | None:
        """Return absolute preference side per C.04.3 section 1.7.1.

        C.04.3 section 1.7.1 defines absolute preference when:
        - color difference > +1 or < -1, or
        - last two played games had the same color.
        """
        return self._absolute_color_preference

    @property
    def strong_color_preference(self) -> Color | None:
        """Return strong preference side per C.04.3 section 1.7.2."""
        return self._strong_color_preference

    @property
    def mild_color_preference(self) -> Color | None:
        """Return mild preference side per C.04.3 section 1.7.3."""
        return self._mild_color_preference

    @property
    def color_preference(self) -> Color | None:
        """Return preference side with absolute > strong > mild priority."""
        return self._color_preference

    def had_float(self, *, rounds_ago: int, kind: FloatKind) -> bool:
        """Return whether player received the given float `rounds_ago` rounds before."""
        if rounds_ago <= 0:
            raise ValueError("rounds_ago must be positive")
        if len(self.float_history) < rounds_ago:
            return False
        return self.float_history[-rounds_ago] == kind


@dataclass(frozen=True, slots=True)
class Pairing:
    """One published pairing.

    `black_id` is `None` for a pairing-allocated bye.
    """

    white_id: str
    black_id: str | None


@dataclass(frozen=True, slots=True)
class PairingResult:
    """Pairing output with explicit unresolved players."""

    pairings: tuple[Pairing, ...]
    unpaired_ids: tuple[str, ...]
