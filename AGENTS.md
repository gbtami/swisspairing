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
3. `JaVaFo` as an optional Swiss-Manager-lineage oracle for real-world event
   investigation, not as a stronger 2026 authority than BBP
4. `py4swiss` as the legacy compatibility oracle for pychess replacement risk

If `py4swiss` and FIDE/BBP disagree, do not silently follow parity. Flag the
case as a likely upstream-report candidate.

## Current State

As of 2026-03-10, the repo already has:

- round-level Dutch pairing with bracket chaining
- typed pychess adapter helpers
- parity and benchmark harnesses against `py4swiss`, `bbpPairings`, and
  optional `JaVaFo`
- checked-in synthetic, BBP-imported, and multiple real-world OTB fixture corpora

Current validation expectation:

- `uv run ruff format --check .` passes
- `uv run ruff check .` passes
- `uv run pyright` passes
- `uv run pytest` is green

Important open items:

- pychess integration is still pending
- checked 2026-specific BBP coverage is still thin; we need more frozen Dutch
  fixtures beyond the current `dutch_2025_C5` / `dutch_2025_C9` set plus the
  checked real-world OTB corpora
- Aeroflot rounds 4 / 6 / 7 / 8 / 9 remain a consensus-engine-vs-published
  investigation area, but they are not currently treated as active Dutch-core
  bugs

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
- `docs/RULEBOOK_DIFF_2026.md`
  Working note about the pre-2026 to 2026 FIDE transition and how it affects
  repo evidence.
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
  Real-world OTB corpus from Aeroflot Open 2026.
- `benchmarks/fixtures/chess_results/prague_international_chess_festival_2026_d`
  Real-world OTB corpus from Prague International Chess Festival 2026 D.
- `benchmarks/fixtures/chess_results/budapest_spring_festival_2026_group_a_2200`
  Real-world OTB corpus from Budapest Spring Festival 2026 Group A.
- `benchmarks/fixtures/chess_results/international_chessopen_graz_2026_a`
  Real-world OTB corpus from International Chessopen Graz 2026 A.
- `benchmarks/fixtures/lichess`
  Normalized TRF16 fixtures exported from Lichess Swiss events.

## Environment Notes

### Python

Use `uv` for setup, linting, typing, tests, and benchmark runners:

```bash
uv sync --group dev
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

The repo is pinned to Python `3.13` in `.python-version`. Keep it there unless
there is a concrete reason to move it. The current oracle/tooling setup is more
stable on `3.13`, and the `networkx` path used by `TieBreakServer` currently
breaks on the excluded `Python 3.14.1` build.

The `dev` dependency group now includes `py4swiss` and `networkx`, so a normal
`uv sync --group dev` should install the current legacy comparison dependency
set as part of project setup.

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

For Swiss-Manager-lineage comparisons, use the public JaVaFo jar plus a local
Java runtime.

Typical local layout:

- jar: `~/JaVaFo/javafo.jar`

Discovery order:

1. `SWISSPAIRING_JAVAFO_JAR`
2. `JAVAFO_JAR`
3. `~/JaVaFo/javafo.jar`

Sanity check:

```bash
java -jar ~/JaVaFo/javafo.jar -r
```

## Commands That Matter

### Fast sanity checks

```bash
uv run ruff format --check .
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

Current status:

- `dutch_2025_C5` and `dutch_2025_C9` are active BBP-backed regression tests
- `issue_7` is kept only as a legacy divergence fixture

### Single three-way reference compare

```bash
uv run python benchmarks/reference_compare_case_runner.py \
  --trf tests/reference_fixtures/bbp/dutch_2025_C5.trf \
  --warmup 0 \
  --repeats 1 \
  --swisspairing-mode fast \
  --bbp-executable ~/bbpPairings/bbpPairings.exe
```

### Full multi-engine catalog compare

```bash
uv run python benchmarks/benchmark_reference_compare.py \
  --fixtures-dir tests/golden/fixtures \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --bbp-executable ~/bbpPairings/bbpPairings.exe \
  --javafo-jar ~/JaVaFo/javafo.jar
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

Preferred path: fetch and convert directly from a Chess-Results event URL:

```bash
uv run python benchmarks/import_chess_results_event.py \
  --url https://s1.chess-results.com/tnr1307079.aspx \
  --output-dir /tmp/chess_results_trf
```

What the importer does:

- forces the English event page and normalized query shape
- auto-submits the old-event `Show tournament details` postback gate when
  Chess-Results hides the full metadata behind it
- verifies that the event looks like a supported individual Swiss event
- detects the declared round count and available board-pairing rounds
- downloads the complete `zeilen=99999` XLSX exports
- runs the same TRF snapshot reconstruction used by the manual exporter

Manual fallback: reconstruct TRF snapshots from already-downloaded
Chess-Results exports:

```bash
uv run python benchmarks/export_chess_results_trf_snapshots.py \
  --starting-list /path/to/chessResultsList.xlsx \
  --output-dir /tmp/chess_results_trf
```

If the standard `chessResultsList(1).xlsx`, `chessResultsList(2).xlsx`, ...
files live next to the starting list, the exporter auto-discovers them.

Important: Chess-Results XLSX exports are paginated by default. For larger
events, use `Show complete list` or `zeilen=99999`; otherwise the first-page
download may stop around 150 rows and the exporter will reject it as
incomplete.

Normalize lenient TRF16 exports (for example, Lichess Swiss downloads):

```bash
uv run python benchmarks/normalize_trf16.py \
  --input ~/Letöltések/lichess_swiss_*.trf \
  --output-dir /tmp/normalized_trf \
  --xxr-mode bbp-next-round
```

Refresh the checked Lichess fixture corpus (normalize + update + compare):

```bash
benchmarks/import_lichess_fixtures.sh
```

## Fixture Guidance

- Prefer checked-in fixtures before inventing new ad hoc repros.
- If a bug is already visible in Aeroflot or BBP fixtures, work from that
  corpus rather than from synthetic data.
- The checked-in real-world Chess-Results corpora are:
  `benchmarks/fixtures/chess_results/aeroflot_open_2026`,
  `benchmarks/fixtures/chess_results/prague_international_chess_festival_2026_d`,
  `benchmarks/fixtures/chess_results/budapest_spring_festival_2026_group_a_2200`,
  and `benchmarks/fixtures/chess_results/international_chessopen_graz_2026_a`.
- Aeroflot rounds 1-3 published-pairing regressions are already fixed and
  covered in `tests/test_chess_results.py`.
- Aeroflot round 5 is the main real-world BBP-backed Dutch regression and is
  also covered in `tests/test_chess_results.py`.
- On the checked Budapest corpus, round 5 now matches `bbpPairings` once
  float history is derived from the TRF instead of inherited from
  `py4swiss`; the earlier round-7 fast-mode-only `swisspairing` divergence is
  fixed.
- On the checked Graz corpus, `swisspairing` now matches `bbpPairings`,
  `py4swiss`, and `JaVaFo` on all 9 rounds, and the earlier round-1 runtime
  tail is closed out by the direct trivial-first-round bracket path.
- Aeroflot 2026 regulations say the pairings were managed by `Swiss Manager`;
  later published-pairing differences where `swisspairing`, `bbpPairings`,
  and `py4swiss` all agree with each other should therefore not be treated as
  automatic FIDE/BBP evidence against the current solver.
- When the question is specifically about published Swiss-Manager behavior,
  use `JaVaFo` as an extra lineage reference before concluding the published
  result reflects a 2026 Dutch rule difference.
- The checked Aeroflot TRF snapshots show no acceleration markers, so
  `C.04.7` does not currently look like the main explanation for the observed
  Aeroflot gaps.

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
- Aeroflot round 5 is another concrete `bbpPairings`/`swisspairing` vs
  `py4swiss` split, but only on the final 3-player bracket; `swisspairing`
  now matches `bbpPairings` there
- On the checked public JaVaFo release, Aeroflot round 5 aligns with the
  `py4swiss` side rather than the BBP/2026 side. Treat that as Swiss-Manager
  lineage evidence, not as stronger normative evidence than FIDE + BBP.
- International Chessopen Graz 2026 A is now a clean consensus corpus:
  `swisspairing`, `bbpPairings`, `py4swiss`, and the checked JaVaFo release
  all agree there, and the earlier round-1 runtime tail is fixed.
- Budapest Spring Festival 2026 Group A round 5 and all three checked Lichess
  fixtures now align `swisspairing` with `bbpPairings` once float history is
  derived from the TRF instead of inherited from `py4swiss`. In all of those
  cases, `py4swiss` and the checked public JaVaFo release still agree with
  each other on a different pairing.
- The public Lichess Swiss lineage is the `cyanfish/bbpPairings` fork
  (`https://github.com/cyanfish/bbpPairings`); its README says the fork is for
  use by Lichess on large Swiss tournaments. Treat Lichess fixture agreement as
  BBP-lineage evidence, not as proof that live Lichess already matches the
  latest upstream 2026 Dutch implementation.
- On the checked golden catalog, the public JaVaFo release agrees on all
  pairable fixtures but does not reject the two impossible-fixture cases that
  `swisspairing`, `bbpPairings`, and `py4swiss` all reject.
- The 2026 FIDE rules changed materially from the pre-2026 Dutch rules:
  `C.04.2` now allows several limited post-publication pairing changes, and
  `C.04.3` replaced the old PSD / PPB / CLB framing with the newer
  PAB + [C5]-[C21] criterion stack. Do not assume a pre-2026 Dutch oracle is
  still normatively valid for 2026 events.
- The checked summary of those rulebook deltas lives in
  `docs/RULEBOOK_DIFF_2026.md`.
- For Aeroflot rounds 4 / 6 / 7 / 8 / 9, the repo now treats the mismatch as a
  consensus-engine-vs-published case, not as an active Dutch-core bug. On the
  checked corpus, `swisspairing`, `bbpPairings`, `py4swiss`, and the public
  JaVaFo release all agree against the published pairings, and the published
  round exports include multiple non-game seats (`not paired` / bye).
- `issue_7` comes from a BBP bug report opened on 2020-04-13, before the 2026
  ruleset. Keep it as a legacy divergence fixture, not as the main remaining
  2026 blocker. Current public references split on it:
  `bbpPairings` vs `py4swiss` + `JaVaFo`, while `swisspairing` currently
  matches neither side.
- Current `issue_7` debugging result: the earlier top-half heterogeneous
  mismatch is fixed. The remaining divergence is confined to the final
  collapsed 22-player bracket, and the internal fixes that got us there are:
  pairable-MDP subset filtering, restricting the heterogeneous structural
  tie-break to complete multi-MDP candidates, and widening the cheap exact
  odd-heterogeneous refinement window.
- late-entry default-color parity was previously misdiagnosed as a
  `py4swiss`/FIDE conflict; it was actually a local bug and is already fixed

## Agent Workflow

- Start from `docs/PLAN.md` for current roadmap status.
- Keep FIDE-first reasoning explicit whenever external engines disagree.
- After any material pairing-path change, rerun:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

- If a performance-related change touches the fast path, also rerun the
  relevant benchmark or recurring baseline slice instead of assuming the old
  preset still describes current behavior.
- Do not move AGENTS-level workflow detail back into `README.md`.
