#!/usr/bin/env bash
set -euo pipefail

BACKEND="deterministic"
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
    --model-dir)
      MODEL_DIR="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/dev.sh [--backend deterministic|llamacpp] [--model-dir models]

Local staged entrypoint:
  --backend deterministic  Start only Gradio with rule-based parsing
  --backend llamacpp       Download/start local llama.cpp servers, then Gradio

Examples:
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
  deterministic)
    exec scripts/run_app.sh --backend deterministic
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
    echo "Invalid backend: $BACKEND. Expected deterministic or llamacpp." >&2
    exit 2
    ;;
esac
