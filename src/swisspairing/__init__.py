"""Swiss pairing package based on rustworkx.

The package currently exposes a first Dutch-oriented bracket pairing API.
"""

from swisspairing.dutch import BracketContext, pair_bracket
from swisspairing.exceptions import PairingError
from swisspairing.model import Color, Pairing, PairingResult, PlayerState
from swisspairing.pychess_adapter import (
    PychessPairingPlan,
    PychessPlayerSnapshot,
    build_player_states_from_snapshots,
    map_plan_to_users,
    pair_snapshots_dutch,
    pairing_result_to_pychess_plan,
)
from swisspairing.synthetic import SyntheticConfig, SyntheticTournament, simulate_tournament
from swisspairing.tournament import pair_round_dutch

__all__ = [
    "Color",
    "BracketContext",
    "Pairing",
    "PairingError",
    "PairingResult",
    "PlayerState",
    "PychessPairingPlan",
    "PychessPlayerSnapshot",
    "SyntheticConfig",
    "SyntheticTournament",
    "build_player_states_from_snapshots",
    "map_plan_to_users",
    "pair_snapshots_dutch",
    "pair_bracket",
    "pair_round_dutch",
    "pairing_result_to_pychess_plan",
    "simulate_tournament",
]
