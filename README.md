---
title: Dukaan Inventory — Telugu Convenience Store Agent
emoji: 🛒
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
tags:
  - inventory
  - telugu
  - llama-cpp
  - langgraph
  - agentic
  - indic-languages
  - rag
  - lora-finetune
---

# Dukaan Saathi · Telugu Inventory Copilot for Kirana Stores

Dukaan Saathi is a small-model inventory assistant for a tiny convenience store in Hyderabad.

The store owner speaks Telugu during the day, sells products with English names, and receives messy supplier receipts on paper. The app helps with the daily inventory loop:

1. Understand Telugu/code-mixed stock commands
2. Extract line items from supplier receipt photos
3. Check inventory thresholds
4. Draft reorder purchase orders by supplier
5. Ask the owner to approve every update before anything changes

This is not a full ERP, POS system, or autonomous purchasing bot. It is a local-first assistant for one real workflow: keeping shelves stocked without forcing the owner to type everything into a spreadsheet.

The LLM does not store inventory or make final business decisions. It only interprets messy inputs and proposes structured actions. Inventory math, thresholds, purchase-order grouping, and database updates are handled by deterministic Python tools. Every stock update and reorder draft requires human approval.


## What it does

- **Telugu/code-mixed stock commands**  
  Example: `Bingo అయిపోయింది` → detects that Bingo is out of stock and proposes an inventory update.

- **Receipt photo parsing**  
  Upload a supplier bill and the app extracts product names, quantities, costs, and supplier names into structured JSON.

- **Inventory ledger**  
  Every approved stock change is written to SQLite with timestamp, source, and reason.

- **Reorder suggestions**  
  When stock falls below threshold, the agent drafts a purchase order grouped by supplier.

- **Human approval**  
  The owner must approve receipt imports, stock updates, and purchase orders before they are applied.

- **Agent trace panel**  
  The UI shows each step: intent detection, product matching, threshold check, supplier grouping, and approval status.

## Architecture

```
Telugu / code-mixed command
        │
Receipt photo
        │
        ▼
Gradio UI
        │
        ▼
Small-model router
(intent, receipt extraction, reorder explanation)
        │
        ▼
Deterministic inventory tools
- match_product()
- update_stock()
- parse_receipt_json()
- check_thresholds()
- draft_purchase_order()
        │
        ▼
Human approval screen
        │
        ▼
SQLite inventory ledger
        │
        ▼
Telugu + English response

```
All models run locally via **llama.cpp** — no cloud APIs.

## TODO: REVIEW IF WHATS UNDER HERE IS STILL RELEVANT
---
## Models used (all < 32B)

| Model | Size | Role |
|---|---|---|
| Llama-3.2-3B-Instruct Q4_K_M | 2GB | Orchestrator / intent classification |
| Mistral-7B-Instruct Q4_K_M | 4.1GB | Inventory, reorder, reporting |
| Mistral-7B LoRA (finetuned) | 4.1GB | Receipt line-item extraction |
| Qwen2.5-VL-7B-Instruct | 7GB | Receipt photo OCR |
| Whisper small | 244MB | Telugu speech recognition |
| IndicTrans2-1B (×2) | 2GB | Telugu↔English translation |

## Finetuning

`mistral-7b-receipt` is a LoRA finetune of Mistral-7B on real receipt photos from
Mahalakshmi Marketing and Sri Venkateshwara Marketing (Malkajgiri, Hyderabad).
Training data: handwritten bills, printed tax invoices, and daily sales notes —
all annotated with structured JSON ground truth.

Trained with [Unsloth](https://github.com/unslothai/unsloth) on a T4 GPU in ~45 minutes.
Exported as Q4_K_M GGUF for llama.cpp inference.

## What we learned

1. **Telugu + English code-switching is the real use case** — the owner says product names
   in English mid-sentence in Telugu. IndicTrans2 handles this well because it was trained
   on Indic code-mixed data.

2. **Finetuning on 3 real receipts beats prompting a general model** — the handwritten
   receipt format (e.g. `4 X 870 = 3480`) is rare in general training data. Even 10 examples
   dramatically improved extraction accuracy.

3. **LangGraph's streaming events are perfect for agent trace UIs** — each node emits
   a step event that maps directly to a trace line in the Gradio UI. Zero extra instrumentation needed.

4. **llama.cpp on HF Spaces T4 is production-viable for this use case** — Mistral-7B Q4_K_M
   runs at ~8 tokens/second on T4, which is fast enough for an inventory tool where the owner
   isn't expecting instant responses.

5. **HITL is not an afterthought — it's the product** — the owner's trust in the system
   comes entirely from the approval step. Never automate the purchase order.
