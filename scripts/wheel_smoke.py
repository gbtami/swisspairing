"""Smoke-test the installed swisspairing wheel in a clean environment."""

from __future__ import annotations

from pathlib import Path

import swisspairing
from swisspairing import PlayerState, PychessPlayerSnapshot, pair_round_dutch, pair_snapshots_dutch


def _module_path_looks_installed() -> bool:
    module_path = Path(swisspairing.__file__).resolve()
    parts = set(module_path.parts)
    return "site-packages" in parts or "dist-packages" in parts


def main() -> None:
    if not _module_path_looks_installed():
        raise SystemExit(f"expected installed wheel import, got {swisspairing.__file__}")

    players = (
        PlayerState(player_id="p1", pairing_no=1, score=10),
        PlayerState(player_id="p2", pairing_no=2, score=10),
        PlayerState(player_id="p3", pairing_no=3, score=5),
        PlayerState(player_id="p4", pairing_no=4, score=5),
    )
    result = pair_round_dutch(players)
    normalized_pairings = sorted(
        (min(pairing.white_id, pairing.black_id), max(pairing.white_id, pairing.black_id))
        for pairing in result.pairings
        if pairing.black_id is not None
    )
    if normalized_pairings != [("p1", "p2"), ("p3", "p4")]:
        raise SystemExit(f"unexpected pair_round_dutch result: {normalized_pairings}")

    snapshots = (
        PychessPlayerSnapshot(username="p1", pairing_no=1, score=10),
        PychessPlayerSnapshot(username="p2", pairing_no=2, score=10),
        PychessPlayerSnapshot(username="p3", pairing_no=3, score=5),
        PychessPlayerSnapshot(username="p4", pairing_no=4, score=5),
    )
    plan = pair_snapshots_dutch(snapshots)
    normalized_plan = sorted((min(a, b), max(a, b)) for a, b in plan.pairings)
    if normalized_plan != [("p1", "p2"), ("p3", "p4")]:
        raise SystemExit(f"unexpected pair_snapshots_dutch result: {normalized_plan}")
    if plan.bye_usernames:
        raise SystemExit(f"unexpected byes from pair_snapshots_dutch: {plan.bye_usernames}")


if __name__ == "__main__":
    main()
