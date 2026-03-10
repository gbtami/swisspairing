# pyright: reportMissingImports=false
"""Download a complete Chess-Results event and export it as TRF snapshots."""

from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from swisspairing.benchmarking import portable_path_str
from swisspairing.chess_results_export import export_chess_results_trf_snapshots
from swisspairing.chess_results_site import (
    download_chess_results_import_plan,
    load_chess_results_import_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Chess-Results event page URL")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path)
    parser.add_argument("--event-slug")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()

    plan = load_chess_results_import_plan(
        args.url,
        timeout_seconds=args.timeout_seconds,
    )

    download_context = (
        nullcontext(args.download_dir.resolve())
        if args.download_dir is not None
        else TemporaryDirectory(prefix="swisspairing_chess_results_")
    )
    with download_context as raw_download_dir:
        download_dir = Path(raw_download_dir)
        downloaded = download_chess_results_import_plan(
            plan,
            download_dir=download_dir,
            timeout_seconds=args.timeout_seconds,
        )
        summary = export_chess_results_trf_snapshots(
            starting_list_path=downloaded.starting_list_path,
            round_paths=downloaded.round_paths,
            output_root=args.output_dir.resolve(),
            event_slug=args.event_slug,
        )

    summary.update(
        {
            "event_url": plan.event_url,
            "tournament_type": plan.tournament_type,
            "declared_round_count": plan.declared_round_count,
            "available_round_numbers": list(plan.round_numbers),
        }
    )
    if args.download_dir is not None:
        summary["download_dir"] = portable_path_str(args.download_dir.resolve())

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
