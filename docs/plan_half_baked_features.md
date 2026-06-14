# Audit: Remaining Feature Gaps For Hugging Face Spaces

Audit date: 2026-06-14. This document is now a status note for the current
FastAPI/static app running toward a Hugging Face Spaces deployment.

## Current HF Spaces Runtime Assumptions

- Public demo runtime is the Docker Space defined by `README.md`.
- The app should default to `RECEIPT_BACKEND=hf_inference` for receipt text
  parsing with `HF_RECEIPT_MODEL_REPO` set in Space secrets/settings.
- Receipt image OCR and speech transcription are optional Modal-hosted services
  called through thin HTTP clients:
  - `MODAL_RECEIPT_ENDPOINT`
  - `MODAL_SPEECH_ENDPOINT` or `SPEECH_ASR_ENDPOINT`
- ReAct is an app-side tool router. It is not a model; it calls tools, and
  model-backed tools may call Modal, HF Inference, or local llama.cpp.
- Inventory writes remain owner-approved. Model output can only create editable
  receipt rows or pending stock actions.
- SQLite state on HF Spaces is ephemeral unless persistent storage is enabled
  and `DB_PATH` points at `/data/...`.

## Completed Since Original Audit

| Feature | Current status |
|---------|----------------|
| ReAct photo path | `POST /api/photo` uses `ReceiptReActAgent` first, with direct fallback. |
| ReAct voice command path | `_h_voice_command` routes through `run_command_parse`, which uses ReAct first. |
| Voice owner approval | Voice parse creates a pending action; `_h_voice_apply` writes only after explicit approval. |
| Dashboard Add to order | `_h_add_to_order` inserts a pending order row. |
| Dashboard Offer to route | `_h_offer_to_route` records a pending liquidation/order intent. |
| Dashboard insights | `run_analysis` now builds deterministic inventory/expiry prose from DB state. |
| Float quantity truncation | Immediate rounding fix added in `kirana_db.py` and `dukaan_saathi/storage.py`. |
| Receipt product matching | Parsed receipt rows are post-matched against existing inventory before display. |
| Orders Mark received | Approved orders can be marked received and stock is updated through the normal owner action. |
| Analytics date range | Analytics supports `7d`, `30d`, and `90d` seller windows. |
| Modal cold-start UX | UI copy explains cold starts; `/api/warm` fire-and-forgets Modal warm pings. |
| Safety tests | `smoke_tests/test_custom_app_safety.py` covers key approval gates and order transitions. |

## Still Worth Doing

### 1. Canonical inventory write boundary

The documented ideal is:

```text
owner approval -> dukaan_saathi/services/inventory.py -> storage ledger
```

The current custom FastAPI path still writes through `kirana_db.py`, which is a
compatibility adapter over the Dukaan storage layer. It preserves the approval
gate, but future code should either migrate these writes into
`dukaan_saathi/services/inventory.py` or keep the adapter boundary explicitly
documented.

### 2. Fractional stock follow-through

`stock_ledger.delta` now migrates to `REAL`, so fractional stock is supported at
the storage layer. Keep checking UI formatting, reorder math, and tests whenever
quantity semantics change.

### 3. HF Spaces persistence decision

For a hackathon demo, ephemeral SQLite may be acceptable. For a realistic public
Space, decide whether to:

- keep session-local state and reset on rebuild, or
- enable HF persistent storage and set `DB_PATH=/data/dukaan.db`.

Document the chosen behavior in the Space README/settings.

### 4. Modal endpoint health and warmup

`/api/warm` currently sends non-blocking `HEAD` requests. If Modal services
expose dedicated health routes, use those instead. Keep page load non-blocking
and avoid surfacing warmup failures as user-facing errors.

### 5. Model endpoint test coverage

Add mocked tests for:

- Modal OCR success and malformed responses.
- Modal speech success and failures.
- HF Inference receipt parser success and malformed JSON fallback.
- Modal receipt LLM success and malformed JSON fallback.

### 6. Voice NLU quality

The current parser is still deterministic/keyword-oriented. For stronger
Telugu/code-mixed commands on Spaces, add an optional HF Inference voice-NLU
path with deterministic fallback and the same owner approval gate.

## Lower Priority Ideas

- LLM-generated dashboard prose after deterministic insights are stable.
- Expanded receipt fine-tuning data and benchmark reports.
- Liquidation-agent routing through WhatsApp/SMS after the order-intent stub is
  enough for the demo.
