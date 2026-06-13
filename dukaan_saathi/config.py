from pathlib import Path
import os


APP_NAME = "Dukaan Saathi"
DB_PATH = os.getenv("DB_PATH", "data/dukaan.db")
DATA_DIR = Path("data")
SAMPLES_DIR = Path("samples")

# Receipt parsing backend:
# - "hf_inference" uses the fine-tuned model on Hugging Face Inference API.
# - "llamacpp" uses local llama.cpp servers.
# - "modal_llm" uses a Modal-hosted receipt parser endpoint.
# - "deterministic" uses the rule-based Python parser.
RECEIPT_BACKEND = os.getenv("RECEIPT_BACKEND", "hf_inference")

# Base URL for the local llama.cpp HTTP servers (OpenAI-compatible).
LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://localhost")

# HF Hub model repo for the fine-tuned receipt model GGUF (used by scripts/download_models.py).
HF_RECEIPT_MODEL_REPO = os.getenv("HF_RECEIPT_MODEL_REPO", "")

# Modal endpoint for receipt text parsing with a hosted LoRA/base model.
MODAL_RECEIPT_LLM_ENDPOINT = os.getenv("MODAL_RECEIPT_LLM_ENDPOINT", "")
