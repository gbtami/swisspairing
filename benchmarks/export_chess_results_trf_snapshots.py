# pyright: reportMissingImports=false
"""Export Chess-Results XLSX pairings/results sheets into TRF snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from swisspairing.chess_results_export import (
    discover_chess_results_round_exports,
    export_chess_results_trf_snapshots,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--starting-list", type=Path, required=True)
    parser.add_argument("--round-export", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--event-slug")
    args = parser.parse_args()

    starting_list = args.starting_list.resolve()
    round_exports = (
        tuple(path.resolve() for path in args.round_export)
        if args.round_export
        else discover_chess_results_round_exports(starting_list)
    )
    if not round_exports:
        raise SystemExit("no round exports found")

    summary = export_chess_results_trf_snapshots(
        starting_list_path=starting_list,
        round_paths=round_exports,
        output_root=args.output_dir.resolve(),
        event_slug=args.event_slug,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
