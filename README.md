---
title: Dukaan Saathi
emoji: 🛒
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
tags:
- inventory
- kirana
- telugu
- fastapi
- minicpm-v
- modal
- speech-to-text
- sqlite
- human-in-the-loop
- small-business
- receipt-parsing
- react-agent
- approval-gated
- llm-finetuning
---

# Dukaan Saathi · Small-Model Inventory Copilot for Kirana Stores

Dukaan Saathi is a phone-friendly inventory copilot for a small Indian convenience store.

The store owner uses Telugu/code-mixed commands during the day, sells products with English names, and receives messy supplier receipts on paper. The app helps turn those messy inputs into safe, reviewable inventory updates.

The goal is **not perfect OCR**. Supplier receipts can be noisy, handwritten, folded, and inconsistent. Dukaan Saathi uses a small vision model to create a draft, then lets the owner quickly correct it before anything touches inventory.

## Core workflow

```text
receipt photo / text command
→ AI draft
→ owner correction
→ owner approval
→ inventory update
→ reorder suggestion
```

Inventory is never updated directly from model output. Every write is approval-gated.

## Using this Space

The app opens on the **Dashboard** tab. Navigate using the top menu:

- **Dashboard** — current stock levels, expiry status, and AI-generated insights
- **Inventory** — full product list; add or edit items
- **Bill Desk** — upload a supplier receipt photo or paste receipt text, correct extracted rows, then approve to update stock
- **Voice** — record or upload a stock command, transcribe it, then approve the proposed change
- **Orders** — pending reorder suggestions; mark as received after stock arrives
- **Analytics** — sales window (7 d / 30 d / 90 d)

**Note on state:** This Space uses SQLite with in-container storage. Inventory changes are visible during your session but may reset when the Space rebuilds. The seeded catalog (Bun, OBM, Happy Happy, Bingo (C), Parle (bulk)) is always restored on restart.

**Note on Modal services:** Receipt image OCR and speech transcription use Modal-hosted endpoints that may have a cold start of 10–30 seconds on first use. A warm-up call runs automatically on page load.

## What it does

### Stock commands

Example:

```text
add Bun 12
```

The app detects that 12 buns arrived and proposes an inventory update. The owner must approve before the stock value changes.

### Receipt photo extraction

The owner uploads a supplier receipt photo. MiniCPM-V extracts likely product rows, quantities, and amounts into a review table.

The extraction can be imperfect. That is expected.

Example noisy draft:

```text
1. Port Ranges (c), qty 1, amount 2450
2. Chocoly, qty 1, amount 8702
```

### Phone-friendly correction commands

Instead of forcing spreadsheet-style editing on a phone, the owner can type a simple correction:

```text
first one Parle bulk, second one Bingo
```

The owner can also record or upload correction audio. The app sends the audio to the Modal speech ASR endpoint, fills the correction command textbox with the transcript, and still waits for the owner to apply the correction and approve rows.

The app remaps the rows to known inventory products:

```text
row 1 → Parle (bulk)
row 2 → Bingo (C)
```

Matched rows become candidates for approval.

Supported correction examples:

```text
first one Parle bulk
second one Bingo
row 1 Parle bulk
row 2 Bingo
skip row 2
quantity row 1 is 4
```

### Approval-gated inventory updates

The owner must explicitly approve stock commands and receipt rows before SQLite inventory is updated.

### Reorder suggestions

When stock falls below threshold, the app drafts reorder suggestions grouped by supplier. Nothing is sent or purchased automatically.

## Quick demo (text-only, no Modal needed)

Paste this into the **Bill Desk** receipt text box:

```text
Mahalakshmi Marketing

| S.No | Particulars | Qty | Rate | Amount |
| 5/   | Port        | 1   | X2450 | 2450  |
| 10/  | Rs.g/c      | 4   | X8702 | 3480  |
```

Click **Parse receipt text**, then type this correction:

```text
first one Parle bulk, second one Bingo
```

Click **Apply correction** → rows map to known products → click **Approve receipt rows** → inventory updates.

See the full [demo flow](#demo-flow) section below for the complete step-by-step walkthrough including voice and photo paths.

## Why small models fit this problem

Small models are good enough to turn messy receipts and natural commands into useful drafts, but they should not be trusted to update business records directly.

Dukaan Saathi uses the model for interpretation and deterministic Python for safety-critical inventory logic:

```text
MiniCPM-V output
→ parsed candidate rows
→ product matching
→ owner correction
→ owner approval
→ SQLite write
```

This keeps the workflow useful even when the model makes mistakes.

## Model lifecycle

The receipt model is trained on Modal, then pushed to Hugging Face Hub for the
public Space runtime.

```text
Modal synthetic data generation
→ Modal LoRA fine-tuning
→ LoRA adapter stored in a Modal Volume
→ Modal push job merges adapter into the base model
→ merged model pushed to Hugging Face Hub
→ HF Space uses hf_inference to call that Hub model
→ parsed receipt rows populate an editable table
→ owner approval updates inventory
```

Modal is the training and optional serving environment. Hugging Face Hub is the
public model artifact store. Hugging Face Inference is the public Space inference
path.

### Fine-tuned receipt model

A LoRA adapter trained on Llama-3.2-3B-Instruct, stored in a Modal Volume:

```text
Modal app:    dukaan-saathi-receipt-llm
Modal Volume: dukaan-saathi-receipt-lora
Adapter path: /adapters/receipt-lora
Base model:   unsloth/Llama-3.2-3B-Instruct-bnb-4bit
```

After training, push the merged model to Hugging Face Hub:

```bash
uv run modal run modal_apps/receipt_llm_service.py::push
```

That push reads these values from `.env`:

```text
HF_TOKEN=...
HF_RECEIPT_MODEL_REPO=summerdevlin46/dukaan-saathi-receipt-lora
```

The public HF Space uses the pushed model through:

```text
RECEIPT_BACKEND=hf_inference
HF_RECEIPT_MODEL_REPO=summerdevlin46/dukaan-saathi-receipt-lora
```

The same adapter can also be served directly through a Modal receipt parser
endpoint for local or fallback runs. Deploying that endpoint writes this to
`.env`:

```text
MODAL_RECEIPT_LLM_ENDPOINT=https://summerdevlin46--dukaan-saathi-receipt-llm-api.modal.run/parse
```

This is not a local GGUF file. Local llama.cpp use is a separate optional path.

### Training data

| File | Examples | Source |
|------|----------|--------|
| `data/finetune/receipt_examples.jsonl` | 6 | Hand-authored |
| `data/finetune/generated/receipt_examples_modal_synthetic.jsonl` | 22 | Modal LLM-generated |

To regenerate synthetic examples:

```bash
scripts/modal_generate_receipt_examples.sh \
  --count 48 \
  --output data/finetune/generated/receipt_examples_modal_synthetic.jsonl
```

To retrain the LoRA adapter on Modal:

```bash
scripts/modal_finetune_receipt.sh --modal-synthetic-count 48 --max-steps 60 --epochs 8
```

To redeploy the inference endpoint after retraining:

```bash
scripts/modal_deploy.sh modal_apps/receipt_llm_service.py
```

To update the public HF Space model after retraining, push again:

```bash
uv run modal run modal_apps/receipt_llm_service.py::push
```

## Current stack

* **Gradio / Hugging Face Space** for the demo UI
* **Lean ReAct tool router** for selecting the small set of inventory/receipt tools
* **HF Inference API** for the public Hugging Face Space receipt parser path, using the model fine-tuned on Modal and pushed to HF Hub
* **llama.cpp + smolagents tools** for the local model-backed receipt parser path
* **MiniCPM-V 4.6** for receipt image extraction
* **Distil-Whisper small English** for correction-command speech transcription
* **Qwen2.5-1.5B-Instruct** for voice command NLU — semantic slot extraction (intent, product name, quantity, unit) from free-form and Telugu/English mixed commands
* **Modal** for hosting model endpoints
* **SQLite** for local inventory state
* **uv** for Python environment and commands
* **Deterministic Python services and fallback parsers** for:

  * stock command parsing
  * receipt text parsing
  * receipt correction commands
  * product matching
  * inventory updates
  * reorder drafts

Modal integrations are optional remote model services. The app-side Modal code
stays as thin HTTP clients; model serving code lives in `modal_apps/`.

For the public Hugging Face Space, use `RECEIPT_BACKEND=hf_inference` with
`HF_RECEIPT_MODEL_REPO` pointing at the published fine-tuned model. The
deterministic parser path exists for smoke tests, offline debugging, and safety
fallbacks; it is not the primary demo experience.

Modal can also host the receipt parser model. This is useful when local or
Hugging Face environments hit GPU/storage/runtime limits. With the current tiny
fine-tuning set, treat Modal fine-tuning as a demo-oriented adapter that improves
format following on known receipt styles, not as a generally reliable parser.

## Runtime pipeline

The local orchestrator is:

```bash
scripts/dev.sh
```

It selects one of four staged runtime paths:

```text
scripts/dev.sh --hf-inference
→ scripts/run_app.sh --backend hf_inference
  → uv run python app.py
  → receipt text parsing calls the HF Inference API model in HF_RECEIPT_MODEL_REPO
```

```text
scripts/dev.sh --llamacpp
→ scripts/start_llamacpp.sh
  → uv run python scripts/download_models.py
  → uv run python -m llama_cpp.server on port 8080
  → uv run python -m llama_cpp.server on port 8082
→ scripts/run_app.sh --backend llamacpp
  → uv run python app.py
```

```text
scripts/dev.sh --modal-llm
→ scripts/run_app.sh --backend modal_llm
  → uv run python app.py
  → receipt text parsing calls MODAL_RECEIPT_LLM_ENDPOINT
```

```text
scripts/dev.sh --deterministic
→ scripts/run_app.sh --backend deterministic
  → uv run python app.py
  → receipt text parsing uses dukaan_saathi/parsers/receipt_text.py
```

Receipt image and speech are separate optional Modal services:

```text
receipt image
→ ReAct router
→ extract_text_from_receipt_image tool
→ dukaan_saathi/integrations/modal_receipt.py
→ MODAL_RECEIPT_ENDPOINT
→ modal_apps/receipt_vlm_service.py
→ raw receipt text
→ parse_receipt_text_tool
→ configured receipt parser backend
→ editable receipt table
→ owner approval
→ dukaan_saathi/services/inventory.py
```

```text
voice or correction audio
→ dukaan_saathi/integrations/speech.py
→ MODAL_SPEECH_ENDPOINT
→ transcript
→ ReAct router for stock commands, or correction parser for receipt rows
→ pending action / corrected editable rows
→ owner approval
```

Inventory writes only happen after approval:

```text
approve command / approve receipt rows
→ dukaan_saathi/services/inventory.py
→ dukaan_saathi/storage.py
→ SQLite stock ledger
```

## Agent status

The active Gradio path uses a lean ReAct-style router in
`dukaan_saathi/agent/react_agent.py`. It records `Thought`, `Action`, and
`Observation` trace lines, chooses the correct existing tool for the small task
set, and never writes inventory directly.

ReAct is the orchestrator, not the model. It calls tools; some tools call remote
models. For example, receipt-photo ReAct chooses the OCR tool, that tool calls
the Modal MiniCPM-V endpoint, then ReAct chooses the receipt parser tool, which
uses the configured backend:

```text
Receipt photo
→ ReAct
→ Modal OCR tool
→ receipt parser tool
   → HF Inference / Modal LLM / llama.cpp / deterministic parser
→ editable rows
→ owner approval
→ inventory write
```

Voice follows the same approval-gated shape:

```text
Audio
→ Modal ASR
→ transcript
→ ReAct stock-command tool
→ pending stock action
→ owner approval
→ inventory write
```

This separation is intentional: Modal/HF/llama.cpp do expensive inference,
ReAct sequences safe tools and exposes a trace, and deterministic inventory
code performs approved writes.

The heavier `smolagents.ToolCallingAgent` implementation remains in
`dukaan_saathi/agent/agent.py`, but it is no longer the primary Gradio path. The
ReAct router calls the existing tool layer directly, which keeps the app simpler
while preserving the same approval gates.

## Main files

```text
app.py                                      — FastAPI/Server entry point; routes dispatches and approval handlers
frontend_backend.py                         — adapter between custom HTML frontend and dukaan_saathi backend
dukaan_saathi/agent/react_agent.py          — lean ReAct tool router; records Thought/Action/Observation traces
dukaan_saathi/agent/tools.py                — parser, integration, and service tools called by the ReAct router
dukaan_saathi/parsers/stock_command.py      — deterministic stock command parser (keyword + fuzzy catalog match)
dukaan_saathi/parsers/receipt_text.py       — deterministic receipt text parser
dukaan_saathi/parsers/receipt_correction.py — row correction command parser
dukaan_saathi/services/inventory.py         — canonical inventory write boundary (all stock writes go here)
dukaan_saathi/services/reorder.py           — reorder suggestion generator
dukaan_saathi/storage.py                    — SQLite access, seed data, find_product
dukaan_saathi/integrations/command_nlu.py   — Qwen2.5-1.5B NLU HTTP client (MODAL_NLU_ENDPOINT)
dukaan_saathi/integrations/modal_receipt.py — MiniCPM-V OCR HTTP client (MODAL_RECEIPT_ENDPOINT)
dukaan_saathi/integrations/speech.py        — Distil-Whisper ASR HTTP client (MODAL_SPEECH_ENDPOINT)
modal_apps/command_nlu_service.py           — Qwen2.5-1.5B slot extraction endpoint
modal_apps/receipt_vlm_service.py           — MiniCPM-V receipt OCR endpoint
modal_apps/speech_asr_service.py            — Distil-Whisper ASR endpoint
modal_apps/receipt_llm_service.py           — receipt LLM train/serve/push
modal_apps/receipt_data_generator.py        — synthetic receipt example generator
scripts/dev.sh                              — local run entrypoint
scripts/modal_deploy.sh                     — deploy a Modal service and write its URL to .env
smoke_tests/test_custom_app_safety.py       — approval gate, NLU, and Modal integration tests
smoke_tests/test_receipt_parser_regression.py
smoke_tests/test_receipt_correction.py
```

## Run locally

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 1 — Install dependencies

```bash
uv sync
```

### 2 — Configure environment

```bash
cp .env.example .env
```

Then edit `.env`. The minimum required value depends on which backend you run:

| Backend | Required in `.env` |
|---------|-------------------|
| `hf_inference` (recommended) | `HF_RECEIPT_MODEL_REPO=summerdevlin46/dukaan-saathi-receipt-lora` |
| `modal_llm` | `MODAL_RECEIPT_LLM_ENDPOINT=<url from modal_deploy.sh>` |
| `deterministic` | nothing — no model calls |
| `llamacpp` | nothing extra — models downloaded automatically |

Optional Modal services (add when you have them; app runs without them):

```text
MODAL_RECEIPT_ENDPOINT=...   # receipt image OCR (MiniCPM-V)
MODAL_SPEECH_ENDPOINT=...    # speech transcription (Distil-Whisper)
MODAL_NLU_ENDPOINT=...       # voice command slot extraction (Qwen2.5-1.5B)
```

`HF_TOKEN` is only needed if `HF_RECEIPT_MODEL_REPO` is a private repo.

**Running on the public HF Space?** Modal endpoints must be added as Space secrets in the HF UI — see [docs/deployment_setup.md](docs/deployment_setup.md) for the full walkthrough.

### 3 — Run

Pick one backend and start the app. It opens at **http://127.0.0.1:7860**.

**HF Inference (recommended for full demo)**

Calls the fine-tuned receipt model hosted on Hugging Face Hub. Requires
`HF_RECEIPT_MODEL_REPO` in `.env`.

```bash
scripts/dev.sh --hf-inference
```

**Deterministic (fastest, no model needed)**

Uses rule-based parsers only. Stock commands, receipt text, corrections, and
approval all work. Use this to verify UI and approval flows without any model
calls.

```bash
scripts/dev.sh --deterministic
```

**Modal LLM (fine-tuned model served on Modal)**

Calls the LoRA-fine-tuned endpoint you deployed on Modal. Requires
`MODAL_RECEIPT_LLM_ENDPOINT` in `.env`.

```bash
scripts/dev.sh --modal-llm
```

**Local llama.cpp (fully offline fallback)**

Downloads GGUF models and starts two llama.cpp servers on ports 8080 and 8082,
then starts the app. Slow first start; receipt quality depends on whether a
fine-tuned GGUF is available via `HF_RECEIPT_GGUF_REPO`.

```bash
scripts/dev.sh --llamacpp
```

### 4 — Run tests

```bash
uv run scripts/smoke_test.sh
```

Focused test runs:

```bash
uv run python -m pytest smoke_tests/test_custom_app_safety.py -v
uv run python -m pytest smoke_tests/test_receipt_parser_regression.py smoke_tests/test_receipt_correction.py -q
```

## Modal endpoints

Deploy the MiniCPM-V receipt endpoint:

```bash
scripts/modal_deploy.sh modal_apps/receipt_vlm_service.py
```

Deploy the speech ASR endpoint:

```bash
scripts/modal_deploy.sh modal_apps/speech_asr_service.py
```

Deploy the voice command NLU endpoint:

```bash
scripts/modal_deploy.sh modal_apps/command_nlu_service.py
```

All three commands deploy the Modal app and write the generated endpoint URL to `.env`.
`MODAL_RECEIPT_ENDPOINT`, `MODAL_SPEECH_ENDPOINT`, and `MODAL_NLU_ENDPOINT` are written automatically.

Load the endpoint environment:

```bash
source scripts/_env.sh
```

Health check:

```bash
BASE_URL="${MODAL_RECEIPT_ENDPOINT%/extract}"
curl "$BASE_URL/health"
```

Speech health check:

```bash
SPEECH_HEALTH_URL="${MODAL_SPEECH_ENDPOINT/speech-transcribe/speech-health}"
curl "$SPEECH_HEALTH_URL"
```

Test receipt extraction directly (replace with your own receipt image):

```bash
curl -sS -X POST "$MODAL_RECEIPT_ENDPOINT" \
  -F "image=@/path/to/receipt.jpeg"
```

Test speech transcription directly:

```bash
curl -sS -X POST "$MODAL_SPEECH_ENDPOINT" \
  -F "audio=@path/to/audio.wav"
```

NLU health check:

```bash
curl "${MODAL_NLU_ENDPOINT}" \
  -X POST -H "Content-Type: application/json" \
  -d '{"command": "add Bun 12"}'
```

Stop Modal to save cost:

```bash
uv run modal app stop dukaan-saathi-receipt-vlm || true
uv run modal app stop dukaan-saathi-speech-asr || true
uv run modal app stop dukaan-saathi-command-nlu || true
uv run modal app list
```

Look for:

```text
Tasks 0
```

## Demo flow

Full walkthrough covering stock commands, receipt photo, and voice correction:

```text
1. Open Dukaan Saathi.
2. Show current inventory.
3. Enter: add Bun 12
4. Click Parse command.
5. Approve the proposed stock update.
6. Show the updated inventory and reorder draft.
7. Upload a supplier receipt photo.
8. MiniCPM-V extracts imperfect rows.
9. Type or record this correction: first one Parle bulk, second one Bingo
10. If using audio, click Transcribe correction audio.
11. Click Apply correction.
12. Show rows mapped to known inventory products.
13. Click Approve receipt rows.
14. Show inventory updated.
15. Show reorder draft updated.
```

## Safety rule

Model output never writes inventory directly.

The app always follows this flow:

```text
model output
→ parsed draft
→ owner review/correction
→ owner approval
→ inventory write
```

This is the core design principle of Dukaan Saathi.
