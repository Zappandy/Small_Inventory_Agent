# Dukaan Saathi Current Agent Handoff

Date: 2026-06-14

This is the current state after the ReAct integration, Modal/HF inference work, and the latest Gradio UI cleanup. Use this as the next-agent starting point.

## Hard Rules

- Use `uv` for all Python commands.
- Run `uv run scripts/smoke_test.sh` before finishing code changes.
- Do not commit `.env`, tokens, local DBs, `__pycache__/`, or `.venv/`.
- Gradio UI lives in `dukaan_saathi/ui/`.
- Inventory writes must go through `dukaan_saathi/services/inventory.py`.
- Model output must never update inventory directly.
- Receipt extraction must populate editable rows first.
- Owner approval is required before stock changes.
- Modal services live in `modal_apps/`.
- App-side Modal integration should stay a thin HTTP client.

## Current App Shape

Entry point:

```bash
uv run python app.py
```

Preferred script:

```bash
scripts/run_app.sh --hf-inference
```

Local deterministic fallback:

```bash
scripts/run_app.sh --deterministic
```

The Gradio app is in `dukaan_saathi/ui/gradio_app.py`.

Sidebar routes now are:

- `Overview`
- `How to?`
- `Inventory`
- `Stock Command`
- `Bill Desk`
- `Reorder`

`Receipt AI` was renamed to `Bill Desk`.

## Demo Flow

For HF Spaces or local demo:

1. Open `Bill Desk`.
2. Use `Load and parse sample`, or paste receipt text and click `Parse receipt text`, or upload a receipt image and click `Read uploaded photo`.
3. Confirm rows appear in `Editable extracted receipt rows`.
4. Optionally correct rows using typed correction or speech transcript.
5. Click `Approve rows and update inventory`.
6. Confirm changed stock in `Inventory after approval`.
7. Open `Reorder` and click `Generate reorder draft`.

Important: this is intentionally approval-gated. Model output fills the editable table; approval writes inventory.

## Inventory Data

Inventory comes from local SQLite:

```text
data/dukaan.db
```

The DB path is controlled by:

```text
DB_PATH
```

Default:

```text
data/dukaan.db
```

Seed data is hardcoded in `dukaan_saathi/storage.py`:

- suppliers: `DEMO_SUPPLIERS`
- products: `DEMO_PRODUCTS`
- aliases: `DEMO_ALIASES`

Original seed products:

- `Bingo (C)`, initial stock 1
- `Parle (bulk)`, initial stock 1
- `PARLE-G 60GM RS.72P`, initial stock 2
- `Happy Happy 27.5G (24P)`, initial stock 4
- `Bun`, initial stock 8
- `OBM`, initial stock 5

The displayed inventory is read through `get_inventory()`, which queries the `current_stock` SQL view. The view sums `stock_ledger` deltas.

Local tests and demos may mutate `data/dukaan.db`. If numbers look unexpected, it is probably because a prior approved command or smoke test wrote ledger rows.

HF Spaces caveat: unless persistent storage is configured, SQLite state is session/runtime-local and can reset on rebuild/restart.

## Receipt / Model Pipeline

Receipt text parser backend is controlled by:

```text
RECEIPT_BACKEND
```

Supported values:

- `hf_inference` default for HF Spaces/public demo
- `modal_llm`
- `llamacpp`
- `deterministic`

Fine-tuned component:

- The fine-tuned model is for receipt text parsing.
- Modal is used for fine-tuning and can serve model endpoints.
- HF Inference can call the pushed HF model for public Spaces use.

Vision OCR and speech are separate optional services:

- `MODAL_RECEIPT_ENDPOINT` for receipt photo OCR.
- `MODAL_SPEECH_ENDPOINT` or `SPEECH_ASR_ENDPOINT` for speech transcription.

The image/OCR path should produce receipt text or rows, but it must still populate editable rows before approval.

## ReAct Agent

Primary ReAct path is:

```text
dukaan_saathi/agent/react_agent.py
```

Tools are in:

```text
dukaan_saathi/agent/tools.py
```

The UI handlers attempt the ReAct agent first, then fall back to deterministic/configured parser paths when needed.

Do not add heavy model inference directly to Gradio runtime. Keep Modal/HF integrations in `dukaan_saathi/integrations/`.

## Recent UI Fixes

Recent user complaints addressed:

- Removed confusing/non-rendering Telugu examples from visible UI.
- Removed the bad `Thums Up 12` example.
- Command examples now use seeded catalog items:
  - `add Bun 12`
  - `set OBM stock 5`
  - `Happy Happy low`
- Removed raw `Proposed action` JSON box from command UI.
- Added a `How to?` route.
- Renamed `Receipt AI` to `Bill Desk`.
- `Load and parse sample` now loads sample text and immediately populates editable rows.
- `Read uploaded photo` falls back to parsing existing receipt text if no image is uploaded.
- Added `Inventory after approval` inside Bill Desk so demo users can see model-derived approved changes without switching tabs.
- Added scoped CSS for dataframe text visibility in Inventory, Bill Desk, and Reorder.
- Added scoped CSS for speech/audio control to avoid white-box rendering.

User is very sensitive to:

- low-contrast dark blue text on green backgrounds
- code/monospace-looking UI examples
- nonfunctional or cluttered dashboard controls
- raw JSON/developer-looking UI components
- examples that do not map to seeded inventory

Do not reintroduce those.

## Current Tests

Run:

```bash
uv run python -m unittest smoke_tests.test_agent_ui_integration
uv run scripts/smoke_test.sh
```

Latest passing state:

- `smoke_tests.test_agent_ui_integration`: 8 tests
- `scripts/smoke_test.sh`: 26 tests

The new integration coverage includes:

- command handler uses ReAct/fallback
- receipt parser fallback produces editable rows
- approved receipt rows update inventory snapshots

## Files Changed Recently

Most recent work touched:

- `dukaan_saathi/ui/gradio_app.py`
- `smoke_tests/test_agent_ui_integration.py`
- `smoke_tests/smoke_test.py`
- `dukaan_saathi/agent/tools.py`
- `README.md`

At handoff time, `git status --short` showed at least:

```text
M  dukaan_saathi/ui/gradio_app.py
M  smoke_tests/test_agent_ui_integration.py
```

There may be other modifications from earlier turns in docs/scripts/config. Inspect with:

```bash
git status --short
git diff --stat
```

## Commands To Run The App

Local HF inference path:

```bash
uv sync
scripts/run_app.sh --hf-inference
```

Local no-model path:

```bash
uv sync
scripts/run_app.sh --deterministic
```

Modal receipt parser path:

```bash
uv sync
scripts/run_app.sh --modal-llm
```

If Gradio port `7860` is occupied, it may launch on `7861`.

## Known Caveats / Next Work

- HF Spaces needs correct secrets/env:
  - `HF_RECEIPT_MODEL_REPO`
  - optional `HF_TOKEN` if model/private access requires it
  - optional Modal endpoint vars for OCR/speech
- SQLite state in HF Spaces is not durable without persistent storage.
- Dashboard header stats may not auto-refresh after approvals because it is static HTML rendered at app load. Tables do update. If this matters, refactor stats into updateable Gradio components.
- The CSS now targets Gradio dataframe internals. If upgrading Gradio, re-check table text visibility.
- Receipt sample rows depend on parser/model output. Deterministic fallback works for smoke tests.
- Do not bypass owner approval to make the demo look more magical. Show the approval step clearly instead.
