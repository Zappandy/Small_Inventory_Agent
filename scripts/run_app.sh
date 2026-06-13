#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

BACKEND="${RECEIPT_BACKEND:-hf_inference}"

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
    --hf-inference)
      BACKEND="hf_inference"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/run_app.sh [--backend hf_inference|modal_llm|llamacpp|deterministic]

Runs the Gradio app through uv.
  --backend hf_inference   Use HF Inference API for the fine-tuned model (default, HF Space path)
  --backend modal_llm      Use Modal-hosted fine-tuned receipt parser endpoint
  --backend llamacpp       Use local llama.cpp receipt parser path
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
  hf_inference|llamacpp|modal_llm|deterministic) ;;
  *)
    echo "Invalid backend: $BACKEND. Expected hf_inference, modal_llm, llamacpp, or deterministic." >&2
    exit 2
    ;;
esac

export RECEIPT_BACKEND="$BACKEND"

if [[ "$BACKEND" == "hf_inference" && -z "${HF_RECEIPT_MODEL_REPO:-}" ]]; then
  echo "HF_RECEIPT_MODEL_REPO is not set."
  echo "Receipt text parsing requires the public HF model repo or a configured HF token/private repo."
fi

if [[ "$BACKEND" == "modal_llm" && -z "${MODAL_RECEIPT_LLM_ENDPOINT:-${MODAL_RECEIPT_PARSER_ENDPOINT:-}}" ]]; then
  echo "MODAL_RECEIPT_LLM_ENDPOINT is not set."
  echo "Receipt text parsing will fall back to deterministic parsing until the Modal fine-tuned endpoint is configured."
fi

if [[ -z "${MODAL_RECEIPT_ENDPOINT:-}" ]]; then
  echo "MODAL_RECEIPT_ENDPOINT is not set."
  echo "The app will still run; image extraction will show a clean endpoint-not-set trace."
fi

echo "Starting Gradio with RECEIPT_BACKEND=$RECEIPT_BACKEND"
uv run python app.py
