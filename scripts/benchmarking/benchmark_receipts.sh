#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

if [[ -z "${MINICPM_RECEIPT_ENDPOINT:-}" && -z "${MOLMO_RECEIPT_ENDPOINT:-}" ]]; then
  echo "Set at least one benchmark endpoint in .env.local:"
  echo "  MINICPM_RECEIPT_ENDPOINT=..."
  echo "  MOLMO_RECEIPT_ENDPOINT=..."
  exit 1
fi

uv run python benchmarks/benchmark_receipt_models.py
