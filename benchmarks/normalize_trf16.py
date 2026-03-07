"""Normalize lenient TRF16 exports into strict fixed-column TRF16 files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from swisspairing.benchmarking import normalize_lenient_trf16_file, portable_path_str


def _target_path(*, source: Path, output_dir: Path | None, in_place: bool) -> Path:
    if in_place:
        return source
    if output_dir is not None:
        return output_dir / source.name
    return source.with_suffix(".normalized.trf")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument(
        "--xxr-mode",
        choices=("preserve", "bbp-next-round"),
        default="preserve",
    )
    args = parser.parse_args()

    sources = [path.expanduser().resolve() for path in args.input]
    if not args.in_place and args.output_dir is None and len(sources) > 1:
        raise SystemExit("use --output-dir or --in-place when normalizing multiple files")

    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else None
    results: list[dict[str, str]] = []
    for source in sources:
        target = _target_path(source=source, output_dir=output_dir, in_place=args.in_place)
        normalize_lenient_trf16_file(source, target, xxr_mode=args.xxr_mode)
        results.append(
            {
                "source": portable_path_str(source),
                "normalized": portable_path_str(target),
            }
        )

    print(json.dumps({"normalized_files": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
