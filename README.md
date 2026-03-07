# swisspairing

`swisspairing` is a Python package for FIDE Dutch Swiss pairings.

It is being developed as a new pairing engine for eventual use in
`pychess-variants`, with correctness driven by the FIDE rules and validated
against external implementations such as `bbpPairings`, `py4swiss`, and
optionally `JaVaFo` for Swiss-Manager-lineage comparisons.

## Status

The project is already usable for Dutch pairing experiments and regression
work, but it is still under active development.

- Round-level Dutch pairing is implemented.
- A typed pychess adapter is included.
- Parity and benchmark harnesses are in place.
- Checked fixture corpora include synthetic cases, imported BBP fixtures, and
  a first real-world OTB corpus reconstructed from Aeroflot Open 2026.
- Full 2026-rule sign-off is not complete yet, and pychess integration is
  still pending.

For the current roadmap and progress notes, see [docs/PLAN.md](docs/PLAN.md).
For the rule-transition notes that matter for this repo, see
[docs/RULEBOOK_DIFF_2026.md](docs/RULEBOOK_DIFF_2026.md).

## Features

- Typed pairing model with explicit player state.
- Dutch bracket and round pairing entry points.
- pychess-oriented snapshot adapter helpers.
- Synthetic tournament generation for regression and benchmark work.
- Benchmark tooling against `py4swiss` and `bbpPairings`, with optional
  `JaVaFo` support for Swiss-Manager-lineage checks.

## Installation

This project is currently installed from source.

For development:

```bash
git clone https://github.com/gbtami/swisspairing.git
cd swisspairing
uv sync --group dev
```

The repo is pinned to Python `3.13` via [`.python-version`](/home/tami/swisspairing/.python-version),
so a normal `uv sync --group dev` should create the expected local environment.

The `dev` dependency group includes `py4swiss` for parity and benchmark work,
and `networkx` for local tooling such as `TieBreakServer` experiments.

For 2026 Dutch comparison work, install `bbpPairings` separately:

```bash
git clone https://github.com/BieremaBoyzProgramming/bbpPairings ~/bbpPairings
cd ~/bbpPairings
make
```

If the executable is not at `~/bbpPairings/bbpPairings.exe`, set
`SWISSPAIRING_BBP_EXECUTABLE`.

For optional Swiss-Manager-lineage comparisons, install the public
[`JaVaFo`](https://www.rrweb.org/javafo/) jar separately and either place it
at `~/JaVaFo/javafo.jar` or set `SWISSPAIRING_JAVAFO_JAR`.

## Quick Start

```python
from swisspairing import PlayerState, pair_round_dutch

players = (
    PlayerState(player_id="p1", pairing_no=1, score=10, color_history=("white",)),
    PlayerState(player_id="p2", pairing_no=2, score=10, color_history=("black",)),
    PlayerState(player_id="p3", pairing_no=3, score=5, color_history=("white",)),
    PlayerState(player_id="p4", pairing_no=4, score=5, color_history=("black",)),
)

result = pair_round_dutch(players)

for pairing in result.pairings:
    print(pairing.white_id, pairing.black_id)
```

Scores are represented in tenths, so `10` means `1.0` point and `5` means
`0.5`.

If you are integrating from pychess-style snapshots instead of raw
`PlayerState` objects, use `pair_snapshots_dutch`.

## Development

Normal local checks:

```bash
uv run ruff format .
uv run ruff check .
uv run pyright
uv run pytest
```

Benchmark and reference-compare tooling is documented in
[benchmarks/README.md](benchmarks/README.md).

## Project Notes

- FIDE remains the rules authority.
- `bbpPairings` is used as the stronger external 2026 Dutch reference.
- `JaVaFo` is useful as a Swiss-Manager-lineage reference, not as a stronger
  2026 rules oracle than `bbpPairings`.
- `py4swiss` is mainly a compatibility reference for pychess replacement work.
