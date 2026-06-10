---

title: Dukaan Saathi — Small-Model Inventory Copilot
emoji: 🛒
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
tags:

* inventory
* kirana
* telugu
* gradio
* minicpm-v
* modal
* speech-to-text
* sqlite
* human-in-the-loop
* small-business
* receipt-parsing

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

### Telugu/code-mixed stock commands

Example:

```text
Bingo అయిపోయింది
```

The app detects that Bingo is out of stock and proposes an inventory update. The owner must approve before the stock value changes.

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

## Current stack

* **Gradio / Hugging Face Space** for the demo UI
* **MiniCPM-V 4.6** for receipt image extraction
* **Distil-Whisper small English** for correction-command speech transcription
* **Modal** for hosting model endpoints
* **SQLite** for local inventory state
* **uv** for Python environment and commands
* **Deterministic Python parsers/services** for:

  * stock command parsing
  * receipt text parsing
  * receipt correction commands
  * product matching
  * inventory updates
  * reorder drafts

## Main files

```text
app.py
dukaan_saathi/ui/gradio_app.py
dukaan_saathi/parsers/stock_command.py
dukaan_saathi/parsers/receipt_text.py
dukaan_saathi/parsers/receipt_correction.py
dukaan_saathi/services/inventory.py
dukaan_saathi/services/reorder.py
dukaan_saathi/integrations/modal_receipt.py
dukaan_saathi/integrations/speech.py
dukaan_saathi/integrations/vision.py
modal_apps/receipt_vlm_service.py
modal_apps/speech_asr_service.py
smoke_tests/smoke_test.py
smoke_tests/test_receipt_parser_regression.py
smoke_tests/test_receipt_correction.py
```

## Run locally

Install or sync dependencies:

```bash
uv sync
```

Run the smoke test:

```bash
uv run python smoke_tests/smoke_test.py
```

Run parser regression tests:

```bash
uv run python -m pytest smoke_tests/test_receipt_parser_regression.py -q
uv run python -m pytest smoke_tests/test_receipt_correction.py -q
```

Run the Gradio app:

```bash
scripts/run_app.sh
```

Open the local Gradio URL shown in the terminal, usually:

```text
http://127.0.0.1:7860
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
3. Enter: Bingo అయిపోయింది
4. Click Parse command.
5. Approve the proposed stock update.
6. Show reorder draft suggesting Bingo.
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

You can test the correction flow without Modal by pasting this into the Receipt Import text box:

```text
Mahalakshmi Marketing

| S.No | Particulars | Qty | Rate | Amount |
| 5/ | Port | 1 | X2450 | 2450 |
| 10/ | Rs.g/c | 4 | X8702 | 3480 |
```

Click:

```text
Parse pasted/sample text
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
