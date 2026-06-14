# Dukaan Saathi Agent Handoff

This file is the starting context for future agents working in this repository.
Use it to preserve the safety model, current architecture, and remaining task
priorities.

## Hard Rules

- Use `uv` for all Python commands.
- Run `uv run scripts/smoke_test.sh` before finishing code changes.
- Do not commit secrets or local runtime files:
  - `.env`
  - Modal tokens
  - Hugging Face tokens
  - `data/*.db`
  - `data/runs/`
  - `models/`
  - `__pycache__/`
  - `.venv/`
- Do not remove Modal scripts, benchmark scripts, `AGENTS.md`, or
  `.env.example`.
- Keep changes small and reviewable. Avoid broad rewrites unless the task
  explicitly requires them.

## Current App Shape

Dukaan Saathi is a phone-friendly inventory copilot for a small Indian kirana
store. It turns receipt photos, pasted receipt text, typed commands, and speech
transcripts into reviewable inventory drafts.

The core workflow is:

```text
receipt photo / text command
-> AI draft or deterministic parser draft
-> editable rows or pending action
-> owner correction
-> owner approval
-> inventory update
-> reorder suggestion
```

Important files:

- `app.py` is the FastAPI/static app entry point.
- `dukaan_saathi/ui/gradio_app.py` contains the Gradio UI path.
- `dukaan_saathi/agent/react_agent.py` is the active lean ReAct router.
- `dukaan_saathi/agent/tools.py` wraps parser, integration, and service tools.
- `dukaan_saathi/agent/agent.py` contains the heavier smolagents
  `ToolCallingAgent`; it is not the primary UI path.
- `dukaan_saathi/services/inventory.py` is the required inventory write
  boundary.
- `dukaan_saathi/storage.py` owns SQLite access and demo seed data.
- `dukaan_saathi/parsers/` contains deterministic fallback parsers.
- `dukaan_saathi/integrations/` contains thin HTTP/model integration clients.
- `modal_apps/` contains Modal-hosted model services and training jobs.

## Safety Architecture

- Inventory writes must go through `dukaan_saathi/services/inventory.py`.
- Model output must never update inventory directly.
- Receipt extraction must populate an editable table first.
- Stock command parsing must produce a pending owner action first.
- Owner approval is required before stock changes.
- Receipt row approval and command approval are the only places that should
  write inventory.
- Modal model services live in `modal_apps/`.
- App-side Modal integration must stay as a thin HTTP client in
  `dukaan_saathi/integrations/`.
- Do not add heavy model inference directly to the Gradio or FastAPI runtime.
- ReAct traces should explain `Thought`, `Action`, and `Observation` steps, but
  traces are audit/UI context only; they are not permission to write stock.

When reviewing changes, flag any code path that bypasses owner approval before
stock changes.

## Runtime And Environment

Use these local run paths:

```bash
scripts/run_app.sh --hf-inference
scripts/run_app.sh --deterministic
scripts/run_app.sh --modal-llm
scripts/dev.sh --hf-inference
scripts/dev.sh --deterministic
scripts/dev.sh --modal-llm
```

Supported receipt backends:

- `hf_inference` is the preferred public Hugging Face Space path.
- `modal_llm` calls the Modal-hosted receipt parser endpoint.
- `llamacpp` uses local llama.cpp servers.
- `deterministic` uses rule-based parsers for smoke tests and offline
  debugging.

Important environment variables:

```text
RECEIPT_BACKEND
HF_RECEIPT_MODEL_REPO
HF_TOKEN
MODAL_RECEIPT_ENDPOINT
MODAL_RECEIPT_LLM_ENDPOINT
MODAL_SPEECH_ENDPOINT
SPEECH_ASR_ENDPOINT
DB_PATH
TRACE_DIR
```

Never write real secret values into tracked files. Keep `.env.example` as the
only tracked env template.

SQLite defaults to `data/dukaan.db`. Local tests and demos may mutate this file.
Hosted HF Spaces state is not durable unless persistent storage is configured
and `DB_PATH` points at that persistent location.

Runtime manifests, when enabled, belong under `data/runs/` and are local
evidence only. They must not contain tokens.

## Model And Data Pipeline

Receipt image flow:

```text
uploaded image
-> Modal MiniCPM-V OCR endpoint
-> raw receipt text
-> configured receipt parser backend
-> editable receipt table
-> owner correction/approval
-> inventory service
-> SQLite stock ledger
```

Receipt text backends:

- HF Inference calls the fine-tuned model in `HF_RECEIPT_MODEL_REPO`.
- Modal LLM calls `MODAL_RECEIPT_LLM_ENDPOINT`.
- llama.cpp uses local model servers.
- deterministic parser uses `dukaan_saathi/parsers/receipt_text.py`.

Speech flow:

```text
audio
-> Modal speech endpoint
-> transcript
-> stock command parser or agent
-> pending owner action
-> owner approval
-> inventory service
```

Fine-tuning and model hosting stay in Modal:

- `modal_apps/receipt_data_generator.py` generates synthetic receipt examples.
- `modal_apps/receipt_llm_service.py` trains, serves, and pushes the receipt
  parser model.
- `modal_apps/receipt_vlm_service.py` serves receipt image OCR.
- `modal_apps/speech_asr_service.py` serves speech transcription.

Use `uv run modal ...` for Modal commands.

## Remaining Task Backlog

Prioritize safety and demo-critical correctness before polish.

### P0 / P1

- Enforce owner confirmation for voice stock commands before inventory writes.
  Current voice flows must not auto-apply parsed actions.
- Verify the active ReAct path is used consistently for photo/text/voice flows
  where intended, with traces exposed to the UI.
- Make dashboard "Add to order" persist a pending order through the database
  instead of only showing a toast.
- Fix float quantity truncation in stock ledger paths. Prefer the smallest safe
  immediate fix unless doing a proper migration.
- Add receipt row product matching so parsed receipt rows suggest existing
  inventory products instead of defaulting to new products.
- Improve Modal cold-start UX for photo and voice actions with clear loading
  feedback.

### P2

- Replace static dashboard insight text with deterministic prose derived from
  current inventory/reorder/expiry state.
- Make dashboard "Offer to route" record a pending liquidation/order intent or
  route to a future liquidation flow.
- Add an Orders "Mark Received" flow for approved orders that applies received
  quantity through the normal inventory approval/write boundary.
- Add a lightweight `/api/warm` endpoint or equivalent keep-warm hook for Modal
  endpoints if it does not complicate deployment.

### P3

- Add analytics date range filtering for top sellers and related metrics.
- Consider LLM-backed voice NLU for Telugu/code-mixed commands, with deterministic
  parser fallback and owner confirmation.
- Consider LLM-generated dashboard prose only after deterministic insights are
  stable.
- Expand receipt fine-tuning data and benchmark coverage.
- Add mocked tests for successful and malformed Modal/llama.cpp model responses.

## UI And Demo Constraints

- Keep the app phone-friendly.
- Avoid raw JSON or developer-looking output in user-facing UI unless it is
  explicitly a trace/debug panel.
- Examples should map to seeded catalog items such as `Bun`, `OBM`,
  `Happy Happy`, `Bingo (C)`, and `Parle (bulk)`.
- Do not reintroduce confusing/non-rendering Telugu examples.
- Do not use low-contrast dark text on green backgrounds.
- Keep the approval step visible. Do not bypass it to make the demo look more
  automatic.

## Review Guidelines

Flag these issues during review:

- Any inventory write that does not go through owner approval.
- Any direct database stock write outside `dukaan_saathi/services/inventory.py`.
- Receipt model output updating inventory directly.
- Voice command output updating inventory before confirmation.
- Secrets, tokens, local DB files, runtime manifests, or generated model files
  being committed.
- Model inference added directly to Gradio/FastAPI runtime instead of an
  integration client or Modal service.
- App-side Modal code becoming more than a thin HTTP client.
- Changes that delete Modal scripts, benchmark scripts, `AGENTS.md`, or
  `.env.example`.
- Broad rewrites where a small targeted change would satisfy the task.

## Commands And Checks

Install or sync dependencies:

```bash
uv sync
```

Run the required smoke test:

```bash
uv run scripts/smoke_test.sh
```

Useful focused checks:

```bash
uv run python -m unittest smoke_tests.test_agent_ui_integration
uv run python -m pytest smoke_tests/test_receipt_parser_regression.py -q
uv run python -m pytest smoke_tests/test_receipt_correction.py -q
```

Before finishing, inspect the diff:

```bash
git status --short
git diff --stat
git diff -- AGENTS.md
```

If there are unrelated user changes in the working tree, do not revert them.
Work around them or ask only when they block the task.
