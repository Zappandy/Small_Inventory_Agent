#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

SERVICE="${1:-modal_apps/receipt_vlm_service.py}"
APP_NAME="${2:-dukaan-saathi-receipt-vlm}"
FUNCTION_NAME="${3:-api}"

echo "Deploying Modal service: $SERVICE"
uv run modal deploy "$SERVICE"

echo "Writing deployed Modal endpoint to .env..."
uv run python scripts/write_modal_endpoint.py \
  --app "$APP_NAME" \
  --function "$FUNCTION_NAME" \
  --route "/extract" \
  --env-var "MODAL_RECEIPT_ENDPOINT" \
  --also "MINICPM_RECEIPT_ENDPOINT"

echo "Done. Current endpoint:"
grep "MODAL_RECEIPT_ENDPOINT" .env || true
