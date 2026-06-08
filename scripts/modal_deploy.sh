#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

: "${MODAL_TOKEN_ID:?Missing MODAL_TOKEN_ID. Add it to .env or export it.}"
: "${MODAL_TOKEN_SECRET:?Missing MODAL_TOKEN_SECRET. Add it to .env or export it.}"

echo "Deploying Modal receipt VLM service..."
uv run modal deploy modal_apps/receipt_vlm_service.py
