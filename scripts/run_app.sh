#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

if [[ -z "${MODAL_RECEIPT_ENDPOINT:-}" ]]; then
  echo "MODAL_RECEIPT_ENDPOINT is not set."
  echo "The app will still run; image extraction will show a clean endpoint-not-set trace."
fi

uv run python app.py
