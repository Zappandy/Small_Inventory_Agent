# Dukaan Saathi — AI Handoff Document

**Date:** 2026-06-13  
**Repo:** https://github.com/Zappandy/Small_Inventory_Agent  
**Branch:** `main` (canonical — `react-refactor` was merged here today)  
**HF Model:** https://huggingface.co/summerdevlin46/dukaan-saathi-receipt-lora  
**HF Space:** not yet deployed (next step)

---

## What this project is

Dukaan Saathi is a phone-friendly inventory copilot for a small Indian kirana (convenience) store. The owner uses Telugu/code-mixed commands and supplier receipts to update stock. Every model output is gated behind owner approval before touching the database — model never writes directly.

Core flow:
```
receipt photo / text command
→ ReAct agent (dukaan_saathi/agent/react_agent.py)
→ structured draft
→ owner review/correction
→ owner approval
→ SQLite inventory update
→ reorder suggestion
```

---

## Stack

- **UI:** Gradio 6.16.0 (`app.py` → `dukaan_saathi/ui/gradio_app.py`)
- **Agent:** Lean ReAct router in `dukaan_saathi/agent/react_agent.py` (smolagents-style, not the heavier `agent/agent.py`)
- **Receipt backend (default):** `hf_inference` — calls fine-tuned model on HF Hub via `InferenceClient`
- **Receipt backend (fallback):** `modal_llm` — calls Modal-hosted endpoint; `llamacpp` — local servers
- **Database:** SQLite at `data/dukaan.db` (path via `DB_PATH` env var); re-seeds demo data on cold start
- **Package manager:** `uv` — always use `uv run python` / `uv run modal`, never bare `python`
- **Dependencies:** `pyproject.toml` + `uv.lock` for local dev; `requirements.txt` for HF Spaces pip install — keep both in sync

---

## Fine-tuned model

- **Base:** `unsloth/Llama-3.2-3B-Instruct-bnb-4bit`
- **Training:** LoRA fine-tune on Modal (`scripts/modal_finetune_receipt.sh`)
- **Adapter stored in:** Modal Volume `dukaan-saathi-receipt-lora`
- **Merged model on HF Hub:** `summerdevlin46/dukaan-saathi-receipt-lora` (2 safetensors shards, fp16)
- **Training data:**
  - `data/finetune/receipt_examples.jsonl` — 6 hand-authored examples
  - `data/finetune/generated/receipt_examples_modal_synthetic.jsonl` — 22 Modal LLM-generated examples

---

## Environment variables (`.env`, gitignored)

```
HF_TOKEN=                        # write token for model push; optional at inference if model is public
HF_RECEIPT_MODEL_REPO=summerdevlin46/dukaan-saathi-receipt-lora

MODAL_RECEIPT_LLM_ENDPOINT=https://summerdevlin46--dukaan-saathi-receipt-llm-api.modal.run/parse
MODAL_RECEIPT_PARSER_ENDPOINT=   # same as above
MODAL_RECEIPT_ENDPOINT=          # MiniCPM-V image extraction endpoint
MODAL_SPEECH_ENDPOINT=           # Distil-Whisper ASR endpoint
```

See `.env.example` for the full template.

---

## Running locally

```bash
uv sync
scripts/dev.sh --modal-llm       # Modal endpoint (requires MODAL_RECEIPT_LLM_ENDPOINT in .env)
scripts/dev.sh --deterministic   # no model, rule-based parser only (smoke testing)
scripts/dev.sh --llamacpp        # local llama.cpp servers (requires model download)
```

Default backend order of preference: `hf_inference` → `modal_llm` → `llamacpp` → `deterministic`

---

## Deploying to HF Spaces

### Prerequisites (must be done before deploying)
1. Model is already on HF Hub at `summerdevlin46/dukaan-saathi-receipt-lora` ✅
2. Make the model repo **public** on HF Hub (Settings → Make public)
3. The GitHub repo `main` branch is ready to link to the Space

### Space secrets to set
```
HF_RECEIPT_MODEL_REPO=summerdevlin46/dukaan-saathi-receipt-lora
# HF_TOKEN not needed if model is public
```

### What the Space does on startup
- `startup.sh` runs (lightweight — just loads `.env`, no llama.cpp)
- `python app.py` launches Gradio with `RECEIPT_BACKEND=hf_inference`
- `init_db()` seeds demo inventory from hardcoded data (SQLite re-seeds on every cold start)

### Database persistence warning
`data/dukaan.db` is gitignored. The Space re-seeds demo data on every cold start — inventory changes during a session are lost on restart. For persistence: set `DB_PATH=/data/dukaan.db` in Space settings and enable HF persistent storage (Pro tier). **Do not touch storage logic without understanding this.**

---

## Key files

```
app.py                                         # entrypoint — demo.launch(css, theme)
dukaan_saathi/
  config.py                                    # RECEIPT_BACKEND default + all env vars
  ui/gradio_app.py                             # Gradio UI, build_demo(), init_db()
  agent/react_agent.py                         # primary agent (lean ReAct router)
  agent/agent.py                               # heavier smolagents impl (not primary path)
  integrations/
    hf_inference_receipt.py                    # DEFAULT: InferenceClient → HF Hub model
    modal_receipt_llm.py                       # FALLBACK: Modal endpoint
    llamacpp_receipt.py                        # FALLBACK: local llama.cpp
  parsers/
    receipt_text.py                            # deterministic fallback parser
    stock_command.py                           # Telugu/code-mixed command parser
    receipt_correction.py                      # correction command parser
  services/inventory.py                        # all inventory writes (approval-gated)
  storage.py                                   # SQLite layer + demo seed data
modal_apps/
  receipt_llm_service.py                       # Modal fine-tune + serve + push-to-hub
  receipt_data_generator.py                    # synthetic training data generation
scripts/
  dev.sh                                       # local dev entrypoint
  modal_finetune_receipt.sh                    # re-train the LoRA
  run_app.sh                                   # runs app.py via uv
startup.sh                                     # HF Space pre-launch hook (lightweight)
requirements.txt                               # HF Spaces pip install (NOT local dev)
pyproject.toml                                 # local dev deps (uv)
```

---

## Things to be careful about

1. **Database persistence** — re-seeds on cold start; do not assume inventory state survives Space restarts without persistent storage
2. **`requirements.txt` vs `pyproject.toml`** — both must be kept in sync; `llama-cpp-python` is intentionally excluded from `requirements.txt` (HF Spaces path only)
3. **`uv run`** — always prefix Modal and Python commands with `uv run` in this project
4. **Modal costs** — stop apps after use: `uv run modal app stop dukaan-saathi-receipt-llm --yes`
5. **Fallback chain** — if `HF_RECEIPT_MODEL_REPO` is not set, `hf_inference` raises explicitly (does NOT silently use deterministic parser); this is intentional
6. **Model push** — to re-push after retraining: `uv run modal run modal_apps/receipt_llm_service.py::push` (reads `HF_TOKEN` and `HF_RECEIPT_MODEL_REPO` from `.env` via `modal.Secret.from_dotenv()`)
