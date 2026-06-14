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
app.py
dukaan_saathi/ui/gradio_app.py
dukaan_saathi/parsers/stock_command.py
dukaan_saathi/parsers/receipt_text.py
dukaan_saathi/parsers/receipt_correction.py
dukaan_saathi/services/inventory.py
dukaan_saathi/services/reorder.py
dukaan_saathi/agent/agent.py
dukaan_saathi/agent/tools.py
dukaan_saathi/integrations/modal_receipt.py
dukaan_saathi/integrations/llamacpp_llm.py
dukaan_saathi/integrations/llamacpp_receipt.py
dukaan_saathi/integrations/speech.py
dukaan_saathi/integrations/vision.py
modal_apps/receipt_vlm_service.py
modal_apps/speech_asr_service.py
modal_apps/receipt_llm_service.py
modal_apps/receipt_data_generator.py
scripts/dev.sh
scripts/start_llamacpp.sh
scripts/run_app.sh
scripts/modal_finetune_receipt.sh
scripts/modal_generate_receipt_examples.sh
docs/pipeline_traceability.md
smoke_tests/smoke_test.py
smoke_tests/test_receipt_parser_regression.py
smoke_tests/test_receipt_correction.py
```

## Run locally

Install or sync dependencies:

```bash
uv sync
```

Install receipt fine-tuning dependencies only when training:

```bash
uv pip install -r requirements-train.txt
```

Run the required smoke test:

```bash
uv run scripts/smoke_test.sh
```

Run focused parser tests:

```bash
uv run python -m pytest smoke_tests/test_receipt_parser_regression.py -q
uv run python -m pytest smoke_tests/test_receipt_correction.py -q
```

### Recommended public HF Space path

The public Space is:

```text
https://huggingface.co/spaces/Zappandy/Kirana_AI
```

The root `Dockerfile` is the deployment artifact for that Space. It runs
`uvicorn app:server` and should not require local llama.cpp model servers.

This path uses the fine-tuned model on Hugging Face via the HF Inference API.

```bash
scripts/dev.sh --hf-inference
```

Or directly:

```bash
scripts/run_app.sh --backend hf_inference
```

Set:

```text
HF_RECEIPT_MODEL_REPO=summerdevlin46/dukaan-saathi-receipt-lora
RECEIPT_BACKEND=hf_inference
```

`HF_TOKEN` is only needed if the model repo is private.

Optional Modal services for the public Space:

```text
MODAL_RECEIPT_ENDPOINT=...       # receipt image OCR
MODAL_SPEECH_ENDPOINT=...        # speech transcription
MODAL_RECEIPT_LLM_ENDPOINT=...   # optional receipt parser fallback
```

The default backend is:

```text
RECEIPT_BACKEND=hf_inference
```

SQLite persistence is a product choice:

- Without HF persistent storage, omit `DB_PATH`; the Space uses
  `data/dukaan.db` inside the runtime and state may reset on rebuild/restart.
- With HF persistent storage enabled, set:

```text
DB_PATH=/data/dukaan.db
```

The Docker image creates `/data`, but durable data still requires persistent
storage to be enabled in the Space settings.

### Modal-hosted receipt parser path

This is the probabilistic path. It uses the fine-tuned LoRA adapter deployed on
Modal (see [Prepared demo artifacts](#prepared-demo-artifacts)). Requires the
`.env` file with `MODAL_RECEIPT_LLM_ENDPOINT` set.

```bash
scripts/dev.sh --modal-llm
```

Or directly:

```bash
scripts/run_app.sh --backend modal_llm
```

Open the local Gradio URL shown in the terminal, usually:

```text
http://127.0.0.1:7860
```

### Local llama.cpp path (fallback)

Use this if the Modal endpoint is unavailable or you want a fully local run.
Requires a GGUF-compatible model artifact and starts two llama.cpp servers. The
HF Space model pushed by `receipt_llm_service.py::push` is a merged HF Hub model
for HF Inference API, not automatically a GGUF.

```bash
scripts/dev.sh --llamacpp
```

Or in separate terminals:

```bash
scripts/start_llamacpp.sh        # starts ports 8080 and 8082
scripts/run_app.sh --backend llamacpp
```

Expected local model servers:

```text
http://127.0.0.1:8080/v1  # agent orchestrator
http://127.0.0.1:8082/v1  # receipt parser (fine-tuned)
```

If `HF_RECEIPT_GGUF_REPO` points to a repo with the expected GGUF file,
`scripts/download_models.py` can use it for local llama.cpp. If it is unset or
does not contain a GGUF, the local path falls back to the base model and receipt
parsing quality will be lower than the fine-tuned HF Inference path.

Limitations:

* The training set is small (28 examples total), so the adapter improves format
  following on known receipt styles rather than generalizing broadly.
* Modal cold starts can add a few seconds to the first receipt parse.
* Keep owner approval enabled; model output still only populates editable rows.

### Deterministic fallback path

Use this only for fast UI/core workflow testing without model servers.
Deterministic means the app uses the rule-based Python parsers in
`dukaan_saathi/parsers/` instead of calling llama.cpp for receipt text parsing.
Stock commands, pasted/sample receipt text, correction commands, approval, and
reorder drafts all work. This is not the preferred hackathon demo path.

```bash
scripts/dev.sh --deterministic
```

Or:

```bash
scripts/run_app.sh --backend deterministic
```

Open the local Gradio URL shown in the terminal, usually:

```text
http://127.0.0.1:7860
```

The startup hook used by hosted environments is:

```bash
./startup.sh
```

It also uses `uv run` and repo-local `models/`.

## Modal endpoints

Deploy the MiniCPM-V receipt endpoint:

```bash
scripts/modal_deploy.sh modal_apps/receipt_vlm_service.py
```

Deploy the speech ASR endpoint:

```bash
scripts/modal_deploy.sh modal_apps/speech_asr_service.py
```

Both commands deploy the Modal app and write the generated endpoint URL to `.env`.
The receipt deployment writes `MODAL_RECEIPT_ENDPOINT`; the speech deployment writes `MODAL_SPEECH_ENDPOINT`.

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

Test receipt extraction directly:

```bash
curl -sS -X POST "$MODAL_RECEIPT_ENDPOINT" \
  -F "image=@samples/receipts/receipt.jpeg"
```

Test speech transcription directly:

```bash
curl -sS -X POST "$MODAL_SPEECH_ENDPOINT" \
  -F "audio=@path/to/audio.wav"
```

Stop Modal to save cost:

```bash
uv run modal app stop dukaan-saathi-receipt-vlm || true
uv run modal app stop dukaan-saathi-speech-asr || true
uv run modal app list
```

Look for:

```text
Tasks 0
```

## Demo flow

Use this flow for the hackathon demo video:

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

## Local text-only receipt test

You can test the correction flow without Modal by pasting this into the Bill Desk text box:

```text
Mahalakshmi Marketing

| S.No | Particulars | Qty | Rate | Amount |
| 5/ | Port | 1 | X2450 | 2450 |
| 10/ | Rs.g/c | 4 | X8702 | 3480 |
```

Click:

```text
Parse receipt text
```

Then enter this correction command:

```text
first one Parle bulk, second one Bingo
```

Click:

```text
Apply correction
```

Expected result:

```text
row 1 → Parle (bulk), apply=True
row 2 → Bingo (C), apply=True
```

Then click:

```text
Approve receipt rows
```

Inventory should update only after approval.

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
