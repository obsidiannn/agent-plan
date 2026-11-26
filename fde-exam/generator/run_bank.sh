#!/usr/bin/env bash
set -uo pipefail

# Generate a real question bank chapter by chapter, with limited parallelism.
# Usage: ./run_bank.sh [prompt_version] [target_per_chapter] [parallel]

PROMPT_VERSION="${1:-v2}"
TARGET_PER_CHAPTER="${2:-16}"
PARALLEL="${3:-4}"
SEED="${SEED:-42}"

cd "$(dirname "$0")"
mkdir -p reports

echo "generation start: prompt=$PROMPT_VERSION target/chapter=$TARGET_PER_CHAPTER parallel=$PARALLEL"

for chapter in 01 02 03 04 05 06 07 08 09 10 11 12; do
  echo "$chapter"
done | xargs -P "$PARALLEL" -I{} bash -c '
  chapter="$1"; prompt_version="$2"; target="$3"; seed="$4"
  echo "[start] chapter $chapter"
  BLIND_SOLVE_SAMPLES_MULTIPLE=1 uv run fde-gen run \
    --chapter "$chapter" \
    --target "$target" \
    --seed "$seed" \
    --prompt-version "$prompt_version" \
    > "reports/bank-${chapter}.log" 2>&1
  code=$?
  echo "[done] chapter $chapter exit=$code"
  tail -5 "reports/bank-${chapter}.log"
  exit $code
' _ {} "$PROMPT_VERSION" "$TARGET_PER_CHAPTER" "$SEED"

echo "generation finished"
uv run fde-gen stats
