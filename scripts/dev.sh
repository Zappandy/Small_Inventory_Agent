#!/usr/bin/env bash
set -euo pipefail

BACKEND="${RECEIPT_BACKEND:-hf_inference}"
MODEL_DIR="${MODEL_DIR:-models}"

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
    --model-dir)
      MODEL_DIR="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/dev.sh [--backend hf_inference|modal_llm|deterministic|llamacpp] [--model-dir models]

Local staged entrypoint:
  --backend hf_inference   Start Gradio against HF Inference API
  --backend modal_llm      Start Gradio against Modal receipt parser endpoint
  --backend deterministic  Start only Gradio with rule-based parsing
  --backend llamacpp       Download/start local llama.cpp servers, then Gradio

Examples:
  scripts/dev.sh --hf-inference
  scripts/dev.sh --modal-llm
  scripts/dev.sh --deterministic
  scripts/dev.sh --llamacpp
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
  hf_inference)
    exec scripts/run_app.sh --backend hf_inference
    ;;
  deterministic)
    exec scripts/run_app.sh --backend deterministic
    ;;
  modal_llm)
    exec scripts/run_app.sh --backend modal_llm
    ;;
  llamacpp)
    export MODEL_DIR
    scripts/start_llamacpp.sh --model-dir "$MODEL_DIR" &
    SERVER_PID=$!

    cleanup() {
      kill "$SERVER_PID" 2>/dev/null || true
      wait "$SERVER_PID" 2>/dev/null || true
    }
    trap cleanup EXIT INT TERM

    echo "Waiting for llama.cpp servers to bind..."
    sleep 15
    scripts/run_app.sh --backend llamacpp
    ;;
  *)
    echo "Invalid backend: $BACKEND. Expected hf_inference, deterministic, llamacpp, or modal_llm." >&2
    exit 2
    ;;
esac
