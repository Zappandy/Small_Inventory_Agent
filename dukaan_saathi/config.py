from pathlib import Path
import os


APP_NAME = "Dukaan Saathi"
DB_PATH = os.getenv("DB_PATH", "data/dukaan.db")
DATA_DIR = Path("data")
SAMPLES_DIR = Path("samples")

# Receipt parsing backend: "llamacpp" uses the fine-tuned Llama-3.2-3B via llama.cpp;
# "deterministic" uses the rule-based Python parser (no llama.cpp required).
RECEIPT_BACKEND = os.getenv("RECEIPT_BACKEND", "llamacpp")

# Base URL for the local llama.cpp HTTP servers (OpenAI-compatible).
LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://localhost")

# HF Hub model repo for the fine-tuned receipt model GGUF (used by scripts/download_models.py).
HF_RECEIPT_MODEL_REPO = os.getenv("HF_RECEIPT_MODEL_REPO", "")