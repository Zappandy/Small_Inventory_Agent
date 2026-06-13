#!/usr/bin/env bash
# HF Space startup hook: prepare local llama.cpp model servers before app.py.
#
# Local development should usually use:
#   scripts/dev.sh --deterministic
#   scripts/dev.sh --llamacpp

set -euo pipefail

source scripts/_env.sh

export MODEL_DIR="${MODEL_DIR:-models}"

echo "Preparing llama.cpp models in $MODEL_DIR"
uv run python scripts/download_models.py

ORCHESTRATOR_MODEL="$MODEL_DIR/llama-3.2-3b-instruct.Q4_K_M.gguf"
RECEIPT_MODEL="$MODEL_DIR/llama-3.2-3b-receipt.Q4_K_M.gguf"

echo "Starting llama.cpp orchestrator on 0.0.0.0:8080"
uv run python -m llama_cpp.server \
  --model "$ORCHESTRATOR_MODEL" \
  --host 0.0.0.0 --port 8080 \
  --n_ctx 2048 --n_threads 2 \
  --chat_format llama-3 &

echo "Starting llama.cpp receipt parser on 0.0.0.0:8082"
uv run python -m llama_cpp.server \
  --model "$RECEIPT_MODEL" \
  --host 0.0.0.0 --port 8082 \
  --n_ctx 2048 --n_threads 2 \
  --chat_format llama-3 &

echo "Waiting for llama.cpp servers to start..."
sleep 15

echo "llama.cpp startup complete."
