# Benchmarks

This folder contains a reproducible benchmark harness for comparing:

- `py4swiss` Dutch engine
- optional `JaVaFo` public release for Swiss-Manager-lineage comparisons
- `swisspairing` Dutch round pairing in both:
  - strict mode (`sequential_search_max_players=None`)
  - fast bounded mode (`sequential_search_max_players=6` by default)

on the same TRF inputs.

For local 2026 Dutch comparisons, build `bbpPairings` first:

```bash
git clone https://github.com/BieremaBoyzProgramming/bbpPairings ~/bbpPairings
cd ~/bbpPairings
make
```

The benchmark helpers auto-discover the executable from:

1. `SWISSPAIRING_BBP_EXECUTABLE`
2. `BBP_PAIRINGS_EXE`
3. `~/bbpPairings/bbpPairings.exe`
4. `PATH`

For optional JaVaFo comparisons, install a local Java runtime plus the public
[`JaVaFo`](https://www.rrweb.org/javafo/) jar. The helpers auto-discover the
jar from:

1. `SWISSPAIRING_JAVAFO_JAR`
2. `JAVAFO_JAR`
3. `~/JaVaFo/javafo.jar`

## Scripts

- `benchmark_py4swiss_compare.py`: multi-case driver with timeout isolation.
- `benchmark_reference_compare.py`: multi-case driver for `py4swiss`,
  `bbpPairings`, optional `JaVaFo`, and both `swisspairing` modes.
- `reference_compare_case_runner.py`: single-case timed runner for the same
  engine set.
- `py4swiss_bench_case_runner.py`: single-case timed runner (JSON output).
- `export_pychess_trf_batches.py`: export pychess dump snapshots to TRF
  benchmark cases.
- `export_chess_results_trf_snapshots.py`: reconstruct TRF snapshots from
  Chess-Results starting-list plus pairings/results XLSX exports.
- `simulate_swiss_batches.py`: generate synthetic Swiss TRF snapshot batches
  with seeded random outcomes.
- `run_recurring_baselines.py`: run fixed-size synthetic baseline profiles and
  append trend rows to CSV.

## Usage

Run against the current golden fixture catalog:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py
```

Run against custom TRF exports (for example, pychess Swiss state exports):

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir /path/to/trf_exports \
  --pattern '*.trf' \
  --fast-sequential-search-max-players 6 \
  --repeats 7 \
  --timeout-seconds 60
```

Run a single case:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --case /path/to/state_001.trf
```

Optional JSON report output:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --json-output /tmp/bench_report.json
```

Run against the checked-in 64-player tail-regression fixtures:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir benchmarks/fixtures/p64_regressions \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 30 \
  --fast-sequential-search-max-players 6
```

Run with SLA checks (non-zero exit when violated):

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir /tmp/sim_swiss_trf \
  --pattern '*.trf' \
  --sla-min-fast-success-rate 0.99 \
  --sla-min-fast-equality-rate-when-both-ok 0.95 \
  --sla-max-runner-error-rate 0.01 \
  --sla-max-fast-p95-ms 2000 \
  --sla-max-fast-p50-ratio 10.0
```

Export TRF benchmark batches directly from pychess dump files
(`tournament.json`, `tournament_player.json`, `tournament_pairing.json`):

```bash
uv run python benchmarks/export_pychess_trf_batches.py \
  --source-root /path/to/pychess-variants \
  --output-dir /tmp/pychess_trf_batches \
  --system 2 \
  --max-snapshots-per-tournament 3
```

Run benchmark on exported batches:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir /tmp/pychess_trf_batches \
  --pattern '*.trf'
```

Reconstruct real-world TRF snapshots from Chess-Results XLSX exports:

```bash
uv run python benchmarks/export_chess_results_trf_snapshots.py \
  --starting-list /path/to/chessResultsList.xlsx \
  --output-dir /tmp/chess_results_trf
```

If the round exports live next to the starting list with the standard
`chessResultsList(1).xlsx`, `chessResultsList(2).xlsx`, ... naming pattern,
the exporter auto-discovers them. The output directory contains one TRF per
published round plus a `published_pairings.json` manifest.

Chess-Results exports are paginated by default. For larger events, use the
site's `Show complete list` view or export with `zeilen=99999`; otherwise the
XLSX files may stop after the first 150 rows and the exporter will reject the
incomplete input.

The repo now includes checked-in real-world OTB corpora reconstructed from
Chess-Results:

```bash
uv run python benchmarks/reference_compare_case_runner.py \
  --trf benchmarks/fixtures/chess_results/aeroflot_open_2026/aeroflot_open_2026_r02.trf \
  --warmup 0 \
  --repeats 1 \
  --swisspairing-mode fast \
  --bbp-executable ~/bbpPairings/bbpPairings.exe
```

Normalize lenient TRF16 exports (for example, some Lichess downloads) into
strict fixed-column TRF16 before running py4swiss/BBP comparisons:

```bash
uv run python benchmarks/normalize_trf16.py \
  --input ~/Letöltések/lichess_swiss_2026.03.03_7TYuxURK_bullet-increment.trf \
  --output-dir /tmp/normalized_trf \
  --xxr-mode bbp-next-round
```

For multiple files, pass `--input` more than once. Use `--in-place` to rewrite
files directly. `--xxr-mode bbp-next-round` shifts `XXR` by +1, which is useful
for BBP compatibility on Lichess exports where `XXR` matches completed rounds.

Refresh the checked Lichess corpus from local downloads in one command
(normalize + fixture update + 4-engine compare summary):

```bash
benchmarks/import_lichess_fixtures.sh
```

Optional parameters:

1. source dir (default: `~/Letöltések`)
2. filename pattern (default: `lichess_swiss*.trf`)
3. normalized output dir (default: `/tmp/normalized_trf_lichess`)
4. checked fixture dir (default: `benchmarks/fixtures/lichess`)
5. reference compare JSON output path

Generate synthetic Swiss TRF batches when no production Swiss history exists:

```bash
uv run python benchmarks/simulate_swiss_batches.py \
  --output-dir /tmp/sim_swiss_trf \
  --seed 20260306 \
  --tournaments 30 \
  --players-min 32 \
  --players-max 256 \
  --rounds-min 5 \
  --rounds-max 11
```

Benchmark generated synthetic batches:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir /tmp/sim_swiss_trf \
  --pattern '*.trf'
```

Build `bbpPairings` once and run three-way comparisons against the same TRF
catalog:

```bash
cd ~/bbpPairings
make

cd ~/swisspairing
uv run python benchmarks/benchmark_reference_compare.py \
  --fixtures-dir tests/golden/fixtures \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --bbp-executable ~/bbpPairings/bbpPairings.exe
```

Run the same comparison with optional JaVaFo enabled:

```bash
uv run python benchmarks/benchmark_reference_compare.py \
  --fixtures-dir tests/golden/fixtures \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --bbp-executable ~/bbpPairings/bbpPairings.exe \
  --javafo-jar ~/JaVaFo/javafo.jar
```

Run recurring baseline profiles (default: 16, 32, 64, 128, 256, 512):

```bash
uv run python benchmarks/run_recurring_baselines.py \
  --output-root benchmarks/results/recurring \
  --tournaments-per-profile 8 \
  --fast-sequential-search-max-players 6 \
  --repeats 3 \
  --warmup 1 \
  --timeout-seconds 120
```

Apply the calibrated recurring synthetic SLA preset from the current checked-in
`post-fast-cap-6-plus-512-20260306` baseline:

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

Output artifacts:

- `benchmarks/results/recurring/<run_id>/run_summary.json`
- `benchmarks/results/recurring/<run_id>/p<size>/simulate.json`
- `benchmarks/results/recurring/<run_id>/p<size>/benchmark.json`
- `benchmarks/results/recurring/trend.csv` (appended on each run)

## Notes

- The benchmark and reference drivers reuse the active interpreter, so run
  them through `uv` after `uv sync --group dev`.
- The driver now probes `py4swiss` before case execution and exits immediately
  with a clear interpreter/import error when the comparison runtime is missing.
- `py4swiss` is used here as a compatibility reference, not as the rules
  authority; if a parity mismatch is traced to FIDE non-compliance, prefer the
  FIDE rule and treat the difference as an upstream-report candidate.
- `bbpPairings` is the stronger external oracle for the remaining 2026 Dutch
  work, but the FIDE handbook is still the final authority if implementations
  disagree.
- `JaVaFo` is useful here as a Swiss-Manager-lineage oracle, especially for
  Aeroflot-style real-world investigations, but the public release should not
  be treated as stronger 2026 rules authority than `bbpPairings`.
- On the checked golden catalog, the public JaVaFo release currently agrees on
  all pairable fixtures but does not reject the two impossible-fixture cases
  that the other three engines reject.
- Child runners prepend the repository `src/` directory to `PYTHONPATH`, so
  local source edits are used during benchmark subprocess runs.
- `benchmarks/fixtures/chess_results/aeroflot_open_2026` is the first
  checked-in real-world OTB corpus reconstructed from external exports. The
  first checked Aeroflot round-2 and round-3 published-pairing regressions are
  now covered in normal tests and currently match in `swisspairing` fast mode,
  `py4swiss`, and BBP.
- `benchmarks/fixtures/lichess` contains normalized TRF16 fixtures exported
  from Lichess Swiss events, plus source/provenance notes.
- `benchmarks/fixtures/p64_regressions` contains checked-in synthetic tail
  cases for 64-player fast-mode runtime work.
- Synthetic batch generation uses the greedy round pipeline with a lower
  sequential-search cap to avoid pathological exact-search runtimes.
- The default recurring sweep now includes `p512`. That profile is still
  practical to benchmark, but its synthetic fixture export is materially
  slower than `p256`; use `--profiles 16,32,64,128,256` if you want the
  lighter historical sweep.
- Synthetic recurring baselines are endogenous to the current fast pairing
  pipeline. After a material pairing-path change, add a new checked-in
  baseline run plus a new preset name rather than silently retuning an older
  preset.
- Recurring baseline trend rows include run id, profile size, exported fixture
  counts, runner error rate, both-ok case counts, fast+strict success/equality
  rates, p50/p95 timings, ratios, calibrated SLA pass/fail status, and git
  metadata.
- Summary includes:
  - success rates for both engines,
  - pairing equality rates for `swisspairing_fast` and `swisspairing_strict`
    using both-ok denominators plus over-all-case rates,
  - global p50/p95 latencies (milliseconds) for both modes,
  - p50 ratios against any enabled external engine (`py4swiss`,
    `bbpPairings`, `JaVaFo`).
