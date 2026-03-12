# 32-Player Tail Regressions

These TRFs were captured from the synthetic benchmark rerun used to investigate
the March 10 midsize tail regressions.

- source dir: `/tmp/swisspairing-p32-refresh/fixtures`
- benchmark input: `/tmp/swisspairing-p32-refresh/benchmark.json`
- command:

```bash
uv run python benchmarks/simulate_swiss_batches.py \
  --output-dir /tmp/swisspairing-p32-refresh/fixtures \
  --seed 20260338 \
  --tournaments 8 \
  --players-min 32 \
  --players-max 32 \
  --rounds-min 5 \
  --rounds-max 11 \
  --max-snapshots-per-tournament 2 \
  --metadata-json /tmp/swisspairing-p32-refresh/simulate.json \
  --fail-on-empty

uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir /tmp/swisspairing-p32-refresh/fixtures \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 120 \
  --json-output /tmp/swisspairing-p32-refresh/benchmark.json
```

They are kept as stable tail cases for midsize exact runtime work around
`[C8]` next-bracket refinement.

Observed timings before the March 11 C8 refinement budget fix:

- `sim0001_r06.trf`: about `992.95ms`
- `sim0005_r04.trf`: about `990.56ms`
- `sim0006_r05.trf`: about `1890.55ms`

Observed timings after the fix on the checked-in bucket:

- `sim0001_r06.trf`: about `205.06ms`
- `sim0005_r04.trf`: about `106.16ms`
- `sim0006_r05.trf`: about `157.06ms`

Quick rerun command:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir benchmarks/fixtures/p32_regressions \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 30
```
