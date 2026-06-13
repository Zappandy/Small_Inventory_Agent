#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

BACKEND="${RECEIPT_BACKEND:-llamacpp}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --deterministic)
      BACKEND="deterministic"
      shift
      ;;
    --llamacpp)
      BACKEND="llamacpp"
      shift
      ;;
    --modal-llm)
      BACKEND="modal_llm"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/run_app.sh [--backend llamacpp|modal_llm|deterministic]

Runs the Gradio app through uv.
  --backend llamacpp       Use local llama.cpp receipt parser path (default)
  --backend modal_llm      Use Modal-hosted receipt parser endpoint
  --backend deterministic  Use rule-based parser for local no-model testing
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

case "$BACKEND" in
  llamacpp|modal_llm|deterministic) ;;
  *)
    echo "Invalid backend: $BACKEND. Expected llamacpp or deterministic." >&2
    exit 2
    ;;
esac

export RECEIPT_BACKEND="$BACKEND"

if [[ -z "${MODAL_RECEIPT_ENDPOINT:-}" ]]; then
  echo "MODAL_RECEIPT_ENDPOINT is not set."
  echo "The app will still run; image extraction will show a clean endpoint-not-set trace."
fi

echo "Starting Gradio with RECEIPT_BACKEND=$RECEIPT_BACKEND"
uv run python app.py
