# 128-Player Tail Regressions

These TRFs were captured from the synthetic benchmark rerun used to investigate
the remaining March 11 midsize exact tails after the earlier `[C8]` fix.

- source dir: `/tmp/swisspairing-p128-refresh/fixtures`
- benchmark input: `/tmp/swisspairing-p128-refresh/benchmark.json`
- command:

```bash
uv run python benchmarks/simulate_swiss_batches.py \
  --output-dir /tmp/swisspairing-p128-refresh/fixtures \
  --seed 20260434 \
  --tournaments 8 \
  --players-min 128 \
  --players-max 128 \
  --rounds-min 5 \
  --rounds-max 11 \
  --max-snapshots-per-tournament 2 \
  --metadata-json /tmp/swisspairing-p128-refresh/simulate.json \
  --fail-on-empty

uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir /tmp/swisspairing-p128-refresh/fixtures \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 120 \
  --json-output /tmp/swisspairing-p128-refresh/benchmark.json
```

They are kept as stable tail cases for late-round one-MDP runtime work in
large-ish synthetic tournaments.

Observed timings before the March 11 single-MDP heterogeneous refinement cut:

- `sim0003_r07.trf`: about `1648.46ms`
- `sim0005_r07.trf`: about `1645.54ms`

Observed timings after the later March 11 bounded `[C8]` refinement cuts on
the regenerated `p128` batch:

- `sim0003_r07.trf`: about `361.85ms`
- `sim0005_r07.trf`: about `515.74ms`

Quick rerun command:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir benchmarks/fixtures/p128_regressions \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 120
```
