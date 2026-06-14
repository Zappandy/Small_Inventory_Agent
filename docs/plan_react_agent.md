# ReAct Agent Status For Hugging Face Spaces

This document describes the current role of the lean ReAct router in the
HF Spaces-oriented runtime.

## Role

ReAct is the app-side orchestrator, not the model.

It records:

```text
Thought -> Action -> Observation
```

and chooses the smallest safe tool chain for a task. The tools may call
deterministic Python, Hugging Face Inference, Modal endpoints, or local
llama.cpp depending on configuration.

ReAct must never write inventory. It returns editable rows, pending actions, and
trace lines. Owner approval remains the write boundary.

## Current Live Paths

### Receipt photo

```text
POST /api/photo
-> ReceiptReActAgent.extract_receipt_image
-> extract_text_from_receipt_image tool
   -> dukaan_saathi/integrations/modal_receipt.py
   -> MODAL_RECEIPT_ENDPOINT
   -> modal_apps/receipt_vlm_service.py
-> parse_receipt_text_tool
   -> hf_inference / modal_llm / llamacpp / deterministic
-> post-match rows to inventory catalog
-> editable receipt rows in UI
-> owner applies row
-> inventory write
```

For HF Spaces, the preferred receipt text parser backend is
`RECEIPT_BACKEND=hf_inference` with `HF_RECEIPT_MODEL_REPO` set.

### Voice command

```text
POST /api/speech
-> Modal ASR endpoint
-> transcript
-> _h_voice_command
-> run_command_parse
-> ReceiptReActAgent.parse_stock_command
-> pending stock action
-> owner clicks Approve stock change
-> _h_voice_apply
-> inventory write
```

The ASR step is separate from ReAct. ReAct starts after text exists.

### Receipt text

The Gradio path already routes text parsing through the ReAct agent with
configured fallback behavior. The custom FastAPI path uses ReAct for photo OCR
flows, then the parser tool for receipt text.

## Tool Responsibilities

- `extract_text_from_receipt_image`: calls the Modal OCR HTTP client.
- `parse_receipt_text_tool`: respects `RECEIPT_BACKEND`.
- `parse_stock_command_tool`: uses the deterministic stock parser today.
- `draft_reorder_tool`: reads inventory and drafts reorder suggestions.
- `propose_inventory_update`: stores a pending proposal only; no DB write.

Modal/HF/llama.cpp inference belongs behind tools or integration clients, not
inside UI handlers.

## Completed

- Custom FastAPI photo path calls `ReceiptReActAgent` first.
- Custom FastAPI voice command path calls `ReceiptReActAgent` first.
- Voice trace is shown in the parsed voice result panel.
- Receipt rows are returned as editable rows and post-matched against inventory.
- Voice actions are pending until owner approval.
- Direct fallback paths remain for robustness if ReAct or a configured backend
  fails.

## Remaining Cleanup

### 1. Heavier ToolCallingAgent

`dukaan_saathi/agent/agent.py` still contains the heavier smolagents
`ToolCallingAgent`. For HF Spaces, do not make this primary unless there is a
clear demo need. If revived, it should use an HF-compatible model client and
must preserve the same owner approval gate.

### 2. Multi-step agent UX

Do not add broad agent chat unless it has a concrete user workflow. The current
demo benefits more from reliable receipt, voice, reorder, and approval flows
than from open-ended agent chat.

## HF Spaces Guidance

- Prefer `hf_inference` for receipt text parsing in the public Space.
- Use Modal for OCR and ASR only when endpoint env vars are configured.
- Keep `/api/warm` best-effort and non-blocking.
- Keep deterministic parser fallbacks for tests and graceful degradation.
- Never require local llama.cpp in the Space runtime.
