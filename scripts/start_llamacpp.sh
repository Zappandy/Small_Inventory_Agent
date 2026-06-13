#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

MODEL_DIR="${MODEL_DIR:-models}"
DOWNLOAD_MODE="download"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-dir)
      MODEL_DIR="$2"
      shift 2
      ;;
    --no-download)
      DOWNLOAD_MODE="skip"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/start_llamacpp.sh [--model-dir models] [--no-download]

Starts local llama.cpp OpenAI-compatible servers:
  8080: agent orchestrator
  8082: receipt parser

Models are stored in the repo-local models/ directory by default.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

export MODEL_DIR

if [[ "$DOWNLOAD_MODE" == "download" ]]; then
  uv run python scripts/download_models.py
fi

ORCHESTRATOR_MODEL="$MODEL_DIR/llama-3.2-3b-instruct.Q4_K_M.gguf"
RECEIPT_MODEL="$MODEL_DIR/llama-3.2-3b-receipt.Q4_K_M.gguf"

if [[ ! -f "$ORCHESTRATOR_MODEL" || ! -f "$RECEIPT_MODEL" ]]; then
  echo "Missing llama.cpp model files in $MODEL_DIR." >&2
  echo "Run scripts/start_llamacpp.sh without --no-download first." >&2
  exit 1
fi

cleanup() {
  jobs -p | xargs -r kill
}
trap cleanup EXIT INT TERM

echo "Starting llama.cpp orchestrator on http://127.0.0.1:8080/v1"
uv run python -m llama_cpp.server \
  --model "$ORCHESTRATOR_MODEL" \
  --host 127.0.0.1 --port 8080 \
  --n_ctx 2048 --n_threads 2 \
  --chat_format llama-3 &

echo "Starting llama.cpp receipt parser on http://127.0.0.1:8082/v1"
uv run python -m llama_cpp.server \
  --model "$RECEIPT_MODEL" \
  --host 127.0.0.1 --port 8082 \
  --n_ctx 2048 --n_threads 2 \
  --chat_format llama-3 &

echo "llama.cpp servers are starting. Press Ctrl-C to stop them."
wait
