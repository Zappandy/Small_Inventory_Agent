"""
download_models.py — download GGUF models from HF Hub into the models/ directory.

Called by startup.sh on first boot. Safe to re-run; skips files that already exist.

Required env vars:
    HF_RECEIPT_MODEL_REPO — HF Hub model repo containing the fine-tuned GGUF
                            e.g. "your-org/llama-3.2-3b-receipt-lora"
                            If unset, falls back to copying the base model.
"""

import os
import shutil
from pathlib import Path

MODEL_DIR = Path(os.getenv("MODEL_DIR", str(Path.home() / "models")))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

ORCHESTRATOR_PATH = MODEL_DIR / "llama-3.2-3b-instruct.Q4_K_M.gguf"
RECEIPT_PATH = MODEL_DIR / "llama-3.2-3b-receipt.Q4_K_M.gguf"


def _hf_download(repo_id: str, filename: str, dest: Path) -> None:
    from huggingface_hub import hf_hub_download

    print(f"Downloading {filename} from {repo_id}...")
    tmp = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(MODEL_DIR),
        local_dir_use_symlinks=False,
    )
    downloaded = Path(tmp)
    if downloaded != dest:
        shutil.move(str(downloaded), str(dest))
    print(f"  → {dest}")


def download_orchestrator() -> None:
    if ORCHESTRATOR_PATH.exists():
        print(f"Orchestrator model already present: {ORCHESTRATOR_PATH}")
        return
    _hf_download(
        repo_id="bartowski/Llama-3.2-3B-Instruct-GGUF",
        filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        dest=ORCHESTRATOR_PATH,
    )


def download_receipt_model() -> None:
    if RECEIPT_PATH.exists():
        print(f"Receipt model already present: {RECEIPT_PATH}")
        return

    hf_repo = os.getenv("HF_RECEIPT_MODEL_REPO", "").strip()
    if hf_repo:
        _hf_download(
            repo_id=hf_repo,
            filename="llama-3.2-3b-receipt-unsloth.Q4_K_M.gguf",
            dest=RECEIPT_PATH,
        )
    else:
        if not ORCHESTRATOR_PATH.exists():
            download_orchestrator()
        print("HF_RECEIPT_MODEL_REPO not set — copying base model as receipt model fallback")
        shutil.copy2(str(ORCHESTRATOR_PATH), str(RECEIPT_PATH))


if __name__ == "__main__":
    download_orchestrator()
    download_receipt_model()
    print("All models ready.")
