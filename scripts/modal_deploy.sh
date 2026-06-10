#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

SERVICE="${1:-modal_apps/receipt_vlm_service.py}"

case "$SERVICE" in
  modal_apps/receipt_vlm_service.py)
    APP_NAME="${2:-dukaan-saathi-receipt-vlm}"
    FUNCTION_NAME="${3:-api}"
    ROUTE="${4:-/extract}"
    ENV_VAR="${5:-MODAL_RECEIPT_ENDPOINT}"
    ALSO_ARGS=(--also "MINICPM_RECEIPT_ENDPOINT")
    ;;
  modal_apps/speech_asr_service.py)
    APP_NAME="${2:-dukaan-saathi-speech-asr}"
    FUNCTION_NAME="${3:-transcribe}"
    ROUTE="${4:-}"
    ENV_VAR="${5:-MODAL_SPEECH_ENDPOINT}"
    ALSO_ARGS=(--also "SPEECH_ASR_ENDPOINT")
    ;;
  *)
    APP_NAME="${2:?Usage: scripts/modal_deploy.sh <service> <app-name> <function-name> [route] [env-var]}"
    FUNCTION_NAME="${3:?Usage: scripts/modal_deploy.sh <service> <app-name> <function-name> [route] [env-var]}"
    ROUTE="${4:-}"
    ENV_VAR="${5:-MODAL_ENDPOINT}"
    ALSO_ARGS=()
    ;;
esac

echo "Deploying Modal service: $SERVICE"
uv run modal deploy "$SERVICE"

echo "Writing deployed Modal endpoint to .env..."
uv run python scripts/write_modal_endpoint.py \
  --app "$APP_NAME" \
  --function "$FUNCTION_NAME" \
  --route "$ROUTE" \
  --env-var "$ENV_VAR" \
  "${ALSO_ARGS[@]}"

echo "Done. Current endpoint:"
grep "$ENV_VAR" .env || true
