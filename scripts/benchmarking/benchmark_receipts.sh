#!/usr/bin/env bash
set -euo pipefail

mkdir -p benchmarks/results

uv run python benchmarks/receipt_eval.py \
  --format markdown \
  --out benchmarks/results/receipt_eval.md \
  --correction "smoke_tests/fixtures/minicpm_receipt_raw_text_actual.txt::first one Parle bulk, second one Bingo"

uv run python benchmarks/receipt_eval.py \
  --format csv \
  --out benchmarks/results/receipt_eval.csv \
  --correction "smoke_tests/fixtures/minicpm_receipt_raw_text_actual.txt::first one Parle bulk, second one Bingo"

echo
echo "Wrote:"
echo "- benchmarks/results/receipt_eval.md"
echo "- benchmarks/results/receipt_eval.csv"
