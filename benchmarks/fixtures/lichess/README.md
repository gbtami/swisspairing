# Lichess TRF Fixtures

This directory stores normalized TRF16 fixtures exported from Lichess Swiss
events.

## Normalization

- Source directory: `~/Letöltések`
- Normalizer: `benchmarks/normalize_trf16.py`
- Mode: `--xxr-mode bbp-next-round`
  - Lichess exports here report `XXR` as completed rounds.
  - BBP expects the next-round-style value (`completed_rounds + 1`).

## Included Cases

- `lichess_swiss_2026.02.14_cY3wR140_weekly-agca-prize-50-dollars.trf`
  - Source URL: `https://lichess.org/swiss/cY3wR140`
  - 2026-03-07 local comparison: `py4swiss` and `JaVaFo` agree; `swisspairing`
    differs; `bbpPairings` differs.
- `lichess_swiss_2026.02.28_KQYWuizM_weekly-agca-prize-50-dollars.trf`
  - Source URL: `https://lichess.org/swiss/KQYWuizM`
  - 2026-03-10 local comparison: `swisspairing`, `py4swiss`, and `JaVaFo`
    agree; `bbpPairings` differs.
- `lichess_swiss_2026.03.03_7TYuxURK_bullet-increment.trf`
  - Source URL: `https://lichess.org/swiss/7TYuxURK`
  - 2026-03-07 local comparison: `swisspairing`, `py4swiss`, and `JaVaFo`
    agree; `bbpPairings` differs.

## Reproduce Comparison Snapshot

```bash
uv run python benchmarks/benchmark_reference_compare.py \
  --fixtures-dir benchmarks/fixtures/lichess \
  --pattern '*.trf' \
  --warmup 0 \
  --repeats 1 \
  --bbp-executable ~/bbpPairings/bbpPairings.exe \
  --javafo-jar ~/JaVaFo/javafo.jar
```
