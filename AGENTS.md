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
- `kirana_db.py` is the custom FastAPI UI adapter over the Dukaan storage
  layer. It must preserve the same owner-approval safety rules while this path
  is migrated toward the canonical inventory service boundary.

## Safety Architecture

- Inventory writes must go through `dukaan_saathi/services/inventory.py`.
  The current custom FastAPI path still writes through `kirana_db.py`, which
  delegates to the Dukaan storage ledger; do not add new direct stock writes
  elsewhere.
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
- ReAct is the orchestrator, not the model. It calls tools; model-backed tools
  may call Modal, Hugging Face Inference, or local llama.cpp. The public Space
  should rely on HF Inference plus optional Modal endpoints, not local model
  servers.

When reviewing changes, flag any code path that bypasses owner approval before
stock changes.

## Runtime And Environment

The public Hugging Face Space is:

```text
https://huggingface.co/spaces/Zappandy/Kirana_AI
```

The root `Dockerfile` deploys the Space frontend/backend by running
`uvicorn app:server`. Do not add a local model-server requirement to that path.

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
- `llamacpp` uses local llama.cpp servers only; do not require it for HF Spaces.
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
MODAL_NLU_ENDPOINT        # Qwen2.5-1.5B command slot extractor; optional, falls back to deterministic
DB_PATH
TRACE_DIR
```

Never write real secret values into tracked files. Keep `.env.example` as the
only tracked env template.

SQLite defaults to `data/dukaan.db`. Local tests and demos may mutate this file.
Hosted HF Spaces state is not durable unless persistent storage is configured
and `DB_PATH` points at that persistent location.

For the public Space, use `DB_PATH=/data/dukaan.db` only when HF persistent
storage is enabled. Otherwise leave `DB_PATH` unset and treat the DB as
runtime-local demo state.

Runtime manifests, when enabled, belong under `data/runs/` and are local
evidence only. They must not contain tokens.

## Model And Data Pipeline

Receipt image flow:

```text
uploaded image
-> ReAct router
-> Modal MiniCPM-V OCR tool
-> raw receipt text
-> configured receipt parser tool/backend
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
-> ReAct stock command tool
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

### Completed

- Voice stock commands parse to a pending action and require explicit owner
  approval before stock writes.
- The custom FastAPI photo and voice paths use the lean ReAct router first, with
  deterministic/configured fallback paths.
- Dashboard "Add to order" and "Offer to route" create pending order rows.
- Receipt rows are post-matched against inventory before display.
- Stock ledger deltas migrate to `REAL` for fractional quantities.
- Dashboard insights use deterministic inventory/expiry state.
- Orders support "Mark received" after approval.
- Analytics has a `7d` / `30d` / `90d` sales window.
- Modal photo/speech flows expose cold-start loading hints and `/api/warm`.
- ReAct agent trace surfaced in the UI as a collapsible "Agent reasoning" panel
  on both the photo and voice result cards.
- Unknown-product commands extract a suggested name and quantity and offer an
  inline "Add new product" form instead of showing a blank result.
- NLU slot extraction service (`modal_apps/command_nlu_service.py`) using
  `Qwen/Qwen2.5-1.5B-Instruct`. Deployed; `MODAL_NLU_ENDPOINT` wired into
  `.env` and HF Space secrets. `run_command_parse` tries NLU first, falls back
  to ReAct/deterministic on failure or unknown intent.
- Mocked NLU tests cover the happy path, unknown-product path, and
  missing-endpoint fallback (`smoke_tests/test_custom_app_safety.py`).
- `/api/warm` pings the NLU health endpoint (`nlu-health`) alongside the
  receipt and speech endpoints.

### Remaining

- Add and maintain tests for every approval gate and order/receipt transition.
- Migrate the custom FastAPI inventory writes from `kirana_db.py` toward
  `dukaan_saathi/services/inventory.py`, or document the adapter boundary
  explicitly until migration is done.
- Keep fractional quantity behavior covered in tests when changing receipt,
  stock, reorder, or sales flows.

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
