#!/usr/bin/env bash
set -euo pipefail

source_dir="${1:-$HOME/Letöltések}"
pattern="${2:-lichess_swiss*.trf}"
normalized_dir="${3:-/tmp/normalized_trf_lichess}"
fixtures_dir="${4:-benchmarks/fixtures/lichess}"
compare_json="${5:-/tmp/lichess_reference_compare_$(date -u +%Y%m%dT%H%M%SZ).json}"
bbp_executable="${SWISSPAIRING_BBP_EXECUTABLE:-$HOME/bbpPairings/bbpPairings.exe}"
javafo_jar="${SWISSPAIRING_JAVAFO_JAR:-$HOME/JaVaFo/javafo.jar}"

shopt -s nullglob
source_files=( "${source_dir}/${pattern}" )
if (( ${#source_files[@]} == 0 )); then
  echo "no Lichess TRF files found: ${source_dir}/${pattern}" >&2
  exit 1
fi

normalize_args=()
for source_file in "${source_files[@]}"; do
  normalize_args+=( "--input" "$source_file" )
done

echo "normalizing ${#source_files[@]} files into ${normalized_dir}" >&2
uv run python benchmarks/normalize_trf16.py \
  "${normalize_args[@]}" \
  --output-dir "${normalized_dir}" \
  --xxr-mode bbp-next-round

mkdir -p "${fixtures_dir}"
rm -f "${fixtures_dir}"/*.trf
cp "${normalized_dir}"/*.trf "${fixtures_dir}/"

echo "running reference comparison on ${fixtures_dir}" >&2
uv run python benchmarks/benchmark_reference_compare.py \
  --fixtures-dir "${fixtures_dir}" \
  --pattern "*.trf" \
  --warmup 0 \
  --repeats 1 \
  --bbp-executable "${bbp_executable}" \
  --javafo-jar "${javafo_jar}" \
  --json-output "${compare_json}"

echo "updated fixtures: ${fixtures_dir}" >&2
echo "comparison summary: ${compare_json}" >&2
