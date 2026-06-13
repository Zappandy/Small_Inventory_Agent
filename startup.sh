#!/usr/bin/env bash
# HF Space startup hook — runs before app.py.
#
# The default backend is modal_llm (fine-tuned LoRA via Modal endpoint).
# No local model servers are needed on HF Spaces.
#
# Local dev with llama.cpp:
#   scripts/dev.sh --llamacpp
# Local dev with Modal:
#   scripts/dev.sh --modal-llm

set -euo pipefail

source scripts/_env.sh

echo "Startup complete. Using RECEIPT_BACKEND=${RECEIPT_BACKEND:-modal_llm}"
