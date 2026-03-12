# 64-Player Tail Regressions

These TRFs were captured from the synthetic benchmark run:

- run id: `p64-focus-20260306`
- source dir: `/tmp/swisspairing_recurring_sla_p64/p64-focus-20260306/p64/fixtures`
- command:

```bash
uv run python benchmarks/run_recurring_baselines.py \
  --profiles 64 \
  --tournaments-per-profile 4 \
  --rounds-min 5 \
  --rounds-max 7 \
  --max-snapshots-per-tournament 2 \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 30
```

They are kept as stable tail cases for exact runtime work on 64-player
tournaments.

Observed `swisspairing` timings before the `PlayerState` color-state cache:

- `sim0001_r06.trf`: `2748.97ms`
- `sim0002_r05.trf`: `478.15ms`
- `sim0003_r04.trf`: `1378.58ms`

Observed `swisspairing` timings after the cache:

- `sim0001_r06.trf`: `1826.04ms`
- `sim0002_r05.trf`: `308.55ms`
- `sim0003_r04.trf`: `867.99ms`

Quick rerun command:

```bash
uv run python benchmarks/benchmark_py4swiss_compare.py \
  --fixtures-dir benchmarks/fixtures/p64_regressions \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --timeout-seconds 30
```
