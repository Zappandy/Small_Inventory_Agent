#!/bin/bash
# startup.sh — runs before app.py in HF Space
# Downloads GGUF models and starts llama.cpp HTTP servers

set -e

LLAMA_CPP_BIN="${HOME}/.local/bin/llama-server"
MODEL_DIR="${HOME}/models"
mkdir -p "$MODEL_DIR"

# ── Install llama.cpp if not present ────────────────────────────────────────
if [ ! -f "$LLAMA_CPP_BIN" ]; then
    echo "Installing llama.cpp..."
    pip install llama-cpp-python[server] --quiet \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
fi

# ── Download GGUF models from HF Hub ────────────────────────────────────────
# Orchestrator: Llama-3.2-3B-Instruct Q4_K_M (~2GB)
if [ ! -f "$MODEL_DIR/llama-3.2-3b.Q4_K_M.gguf" ]; then
    echo "Downloading Llama-3.2-3B..."
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
       "$MODEL_DIR/llama-3.2-3b.Q4_K_M.gguf"
fi

# Inventory/Reorder/Report: Mistral-7B-Instruct Q4_K_M (~4.1GB)
if [ ! -f "$MODEL_DIR/mistral-7b.Q4_K_M.gguf" ]; then
    echo "Downloading Mistral-7B..."
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='TheBloke/Mistral-7B-Instruct-v0.2-GGUF',
    filename='mistral-7b-instruct-v0.2.Q4_K_M.gguf',
    local_dir='$MODEL_DIR',
    local_dir_use_symlinks=False,
)
"
    mv "$MODEL_DIR/mistral-7b-instruct-v0.2.Q4_K_M.gguf" \
       "$MODEL_DIR/mistral-7b.Q4_K_M.gguf"
fi

# Receipt parser: LoRA-merged Mistral-7B (upload your finetuned GGUF here)
# If not present yet, fall back to base Mistral-7B
if [ ! -f "$MODEL_DIR/mistral-7b-receipt.Q4_K_M.gguf" ]; then
    echo "Finetuned receipt model not found — using base Mistral-7B for port 8082"
    cp "$MODEL_DIR/mistral-7b.Q4_K_M.gguf" \
       "$MODEL_DIR/mistral-7b-receipt.Q4_K_M.gguf"
fi

# ── Start llama.cpp HTTP servers ─────────────────────────────────────────────
echo "Starting llama.cpp servers..."

# Port 8080 — Llama-3.2-3B orchestrator (2 threads, small context)
python -m llama_cpp.server \
    --model "$MODEL_DIR/llama-3.2-3b.Q4_K_M.gguf" \
    --host 0.0.0.0 --port 8080 \
    --n_ctx 2048 --n_threads 2 \
    --chat_format llama-3 &

# Port 8081 — Mistral-7B general (4 threads)
python -m llama_cpp.server \
    --model "$MODEL_DIR/mistral-7b.Q4_K_M.gguf" \
    --host 0.0.0.0 --port 8081 \
    --n_ctx 4096 --n_threads 4 \
    --chat_format mistral &

# Port 8082 — Mistral-7B receipt finetuned
python -m llama_cpp.server \
    --model "$MODEL_DIR/mistral-7b-receipt.Q4_K_M.gguf" \
    --host 0.0.0.0 --port 8082 \
    --n_ctx 4096 --n_threads 4 \
    --chat_format mistral &

# Wait for servers to be ready
echo "Waiting for llama.cpp servers to start..."
sleep 15

echo "All servers started. Launching Gradio..."
