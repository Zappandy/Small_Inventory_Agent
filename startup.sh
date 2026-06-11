#!/bin/bash
# startup.sh — runs before app.py in HF Space or locally.
# Installs llama-cpp-python if needed, downloads GGUF models, starts servers.
#
# Models:
#   Port 8080 — llama-3.2-3b-instruct.Q4_K_M.gguf   (agent orchestrator)
#   Port 8082 — llama-3.2-3b-receipt.Q4_K_M.gguf    (fine-tuned receipt text parser)
#
# Set HF_RECEIPT_MODEL_REPO to your published fine-tuned model repo, e.g.:
#   export HF_RECEIPT_MODEL_REPO="your-org/llama-3.2-3b-receipt-lora"

set -e

MODEL_DIR="${HOME}/models"
mkdir -p "$MODEL_DIR"

# ── Install llama-cpp-python server if not present ───────────────────────────
if ! python -c "import llama_cpp" 2>/dev/null; then
    echo "Installing llama-cpp-python..."
    pip install llama-cpp-python[server] --quiet \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
fi

# ── Download GGUF models from HF Hub ─────────────────────────────────────────

# Orchestrator: base Llama-3.2-3B-Instruct Q4_K_M (~2GB)
if [ ! -f "$MODEL_DIR/llama-3.2-3b-instruct.Q4_K_M.gguf" ]; then
    echo "Downloading Llama-3.2-3B-Instruct..."
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='bartowski/Llama-3.2-3B-Instruct-GGUF',
    filename='Llama-3.2-3B-Instruct-Q4_K_M.gguf',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False,
)
"
    mv "$MODEL_DIR/Llama-3.2-3B-Instruct-Q4_K_M.gguf" \
       "$MODEL_DIR/llama-3.2-3b-instruct.Q4_K_M.gguf"
fi

# Receipt parser: fine-tuned Llama-3.2-3B (download from HF Hub if repo is set)
if [ ! -f "$MODEL_DIR/llama-3.2-3b-receipt.Q4_K_M.gguf" ]; then
    if [ -n "${HF_RECEIPT_MODEL_REPO:-}" ]; then
        echo "Downloading fine-tuned receipt model from $HF_RECEIPT_MODEL_REPO..."
        python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='${HF_RECEIPT_MODEL_REPO}',
    filename='llama-3.2-3b-receipt-unsloth.Q4_K_M.gguf',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False,
)
"
        mv "$MODEL_DIR/llama-3.2-3b-receipt-unsloth.Q4_K_M.gguf" \
           "$MODEL_DIR/llama-3.2-3b-receipt.Q4_K_M.gguf"
    else
        echo "HF_RECEIPT_MODEL_REPO not set — using base model for receipt parser (port 8082)"
        cp "$MODEL_DIR/llama-3.2-3b-instruct.Q4_K_M.gguf" \
           "$MODEL_DIR/llama-3.2-3b-receipt.Q4_K_M.gguf"
    fi
fi

# ── Start llama.cpp HTTP servers ─────────────────────────────────────────────
echo "Starting llama.cpp servers..."

# Port 8080 — Llama-3.2-3B base (agent orchestrator)
python -m llama_cpp.server \
    --model "$MODEL_DIR/llama-3.2-3b-instruct.Q4_K_M.gguf" \
    --host 0.0.0.0 --port 8080 \
    --n_ctx 2048 --n_threads 2 \
    --chat_format llama-3 &

# Port 8082 — Llama-3.2-3B fine-tuned (receipt text parser)
python -m llama_cpp.server \
    --model "$MODEL_DIR/llama-3.2-3b-receipt.Q4_K_M.gguf" \
    --host 0.0.0.0 --port 8082 \
    --n_ctx 2048 --n_threads 2 \
    --chat_format llama-3 &

# Wait for servers to be ready
echo "Waiting for llama.cpp servers to start..."
sleep 15

echo "All servers started. Launching Gradio..."
