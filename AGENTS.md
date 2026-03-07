# AGENTS.md

This file is for code agents working in this repository. Keep `README.md`
human-facing and conventional; put repo-operator detail here instead.

## Mission

Build `swisspairing` into a FIDE Dutch Swiss pairing package that can
eventually replace `py4swiss` usage in `pychess-variants`.

## Rules Authority

Always treat the FIDE handbook as the source of truth, not external
implementations.

Relevant rule sources:

- C.04.1 Basic rules for Swiss Systems
- C.04.2 General handling rules for Swiss Tournaments
- C.04.3 FIDE Dutch System

Practical oracle order used in this repo:

1. FIDE handbook
2. `bbpPairings` as the stronger external 2026 Dutch oracle
3. `py4swiss` as the legacy compatibility oracle for pychess replacement risk

If `py4swiss` and FIDE/BBP disagree, do not silently follow parity. Flag the
case as a likely upstream-report candidate.

## Current State

As of 2026-03-07, the repo already has:

- round-level Dutch pairing with bracket chaining
- typed pychess adapter helpers
- parity and benchmark harnesses against `py4swiss` and `bbpPairings`
- checked-in synthetic, BBP-imported, and first real-world OTB fixture corpora

Current validation expectation:

- `uv run ruff check .` passes
- `uv run pyright` passes
- `uv run pytest` is green with one expected xfail:
  `tests/test_bbp_reference.py::test_bbp_reference_issue_7_matches_bbp_expected_output`

Important open items:

- `issue_7` remains the main checked 2026 Dutch gap
- full real-world Aeroflot sweep beyond the fixed round-2 / round-3 regressions
  has not been fully closed out yet
- pychess integration is still pending

## Repository Map

- `src/swisspairing/`
  Core implementation and public package surface.
- `tests/`
  Unit tests, golden parity fixtures, and BBP reference fixtures.
- `benchmarks/`
  Benchmark drivers, exporters, recurring baseline runner, and checked-in
  corpora.
- `docs/PLAN.md`
  Progress snapshot and remaining roadmap. Start here for project status.
- `README.md`
  Human-facing project overview.

Key fixture directories:

- `tests/golden/fixtures`
  Legacy `py4swiss` parity fixtures.
- `tests/reference_fixtures/bbp`
  Imported Dutch fixtures from `bbpPairings`.
- `benchmarks/fixtures/p64_regressions`
  Checked-in synthetic 64-player runtime tail cases.
- `benchmarks/fixtures/chess_results/aeroflot_open_2026`
  First checked-in real-world OTB corpus.

## Environment Notes

### Python

Use `uv` for setup, linting, typing, tests, and benchmark runners:

```bash
uv sync --group dev
uv run ruff check .
uv run pyright
uv run pytest
```

The `dev` dependency group now includes `py4swiss`, so a normal
`uv sync --group dev` should install the legacy comparison dependency as part
of project setup.

Reference and benchmark runners reuse the active interpreter. If comparison
runs start failing due to missing `py4swiss`, check:

```bash
uv run python -c "import py4swiss; print(py4swiss.__file__)"
```

### External Oracles

For 2026-rule comparison work, install `bbpPairings` from:

- `https://github.com/BieremaBoyzProgramming/bbpPairings`

Typical local layout:

- source: `~/bbpPairings`
- executable: `~/bbpPairings/bbpPairings.exe`

Build it with:

```bash
git clone https://github.com/BieremaBoyzProgramming/bbpPairings ~/bbpPairings
cd ~/bbpPairings
make
```

If the executable is somewhere else, set one of:

- `SWISSPAIRING_BBP_EXECUTABLE`
- `BBP_PAIRINGS_EXE`

## Commands That Matter

### Fast sanity checks

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

### Golden parity

```bash
uv run pytest tests/test_py4swiss_golden.py
```

### BBP-backed reference fixtures

```bash
uv run pytest tests/test_bbp_reference.py
```

### Single three-way reference compare

```bash
uv run python benchmarks/reference_compare_case_runner.py \
  --trf tests/reference_fixtures/bbp/dutch_2025_C5.trf \
  --warmup 0 \
  --repeats 1 \
  --swisspairing-mode fast \
  --bbp-executable ~/bbpPairings/bbpPairings.exe
```

### Full three-way catalog compare

```bash
uv run python benchmarks/benchmark_reference_compare.py \
  --fixtures-dir tests/golden/fixtures \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --bbp-executable ~/bbpPairings/bbpPairings.exe
```

### Recurring synthetic baselines

Current default size sweep:

- `16,32,64,128,256,512`

Current checked-in SLA preset:

- `post-fast-cap-6-plus-512-20260306`

Command:

```bash
uv run python benchmarks/run_recurring_baselines.py \
  --output-root benchmarks/results/recurring \
  --tournaments-per-profile 8 \
  --fast-sequential-search-max-players 6 \
  --repeats 1 \
  --warmup 0 \
  --timeout-seconds 120 \
  --sla-preset post-fast-cap-6-plus-512-20260306
```

### Real-world Chess-Results import

Reconstruct TRF snapshots from Chess-Results exports:

```bash
uv run python benchmarks/export_chess_results_trf_snapshots.py \
  --starting-list /path/to/chessResultsList.xlsx \
  --output-dir /tmp/chess_results_trf
```

If the standard `chessResultsList(1).xlsx`, `chessResultsList(2).xlsx`, ...
files live next to the starting list, the exporter auto-discovers them.

## Fixture Guidance

- Prefer checked-in fixtures before inventing new ad hoc repros.
- If a bug is already visible in Aeroflot or BBP fixtures, work from that
  corpus rather than from synthetic data.
- The first checked-in real-world corpus is
  `benchmarks/fixtures/chess_results/aeroflot_open_2026`.
- Aeroflot round 2 and round 3 mismatches are already fixed and covered in
  `tests/test_chess_results.py`.

## Integration Tuning

For pychess adapter usage:

```bash
export SWISSPAIRING_PAIRING_MODE=fast
export SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS=8
```

Precedence:

1. explicit function argument
2. `SWISSPAIRING_SEQUENTIAL_SEARCH_MAX_PLAYERS`
3. `SWISSPAIRING_PAIRING_MODE`

Current practical default:

- `fast` mode with cap `6`

## Known Reference Findings

- `dutch_2025_C5` is the clearest local case where `bbpPairings` and
  `swisspairing` agree while `py4swiss` disagrees
- `issue_7` remains the tracked BBP-backed xfail and is believed to live in the
  weighted heterogeneous plus round-collapse path, not the basic exact critical
  bracket itself
- late-entry default-color parity was previously misdiagnosed as a
  `py4swiss`/FIDE conflict; it was actually a local bug and is already fixed

## Agent Workflow

- Start from `docs/PLAN.md` for current roadmap status.
- Keep FIDE-first reasoning explicit whenever external engines disagree.
- After any material pairing-path change, rerun:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

- If a performance-related change touches the fast path, also rerun the
  relevant benchmark or recurring baseline slice instead of assuming the old
  preset still describes current behavior.
- Do not move AGENTS-level workflow detail back into `README.md`.
