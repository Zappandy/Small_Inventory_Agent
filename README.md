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

# Dukaan Inventory · దుకాణం ఇన్వెంటరీ

An agentic inventory management system for a small Indian convenience store in Hyderabad —
built for owners who speak Telugu but work with English product names and supplier receipts.

## What it does

- **Telugu voice input** — speak a command ("Bingo అయిపోయింది") and the system understands
- **Receipt photo parsing** — photograph a handwritten or printed supplier bill; the agent extracts all line items
- **Automated reorder suggestions** — when stock falls below threshold, a grouped purchase order is drafted by supplier and shown for approval (human-in-the-loop)
- **Bilingual UI** — alerts and responses in Telugu; product names and data always in English
- **Agent trace panel** — see every step the LangGraph orchestrator takes in real time
- **Weekly reports & shrinkage** — cost vs. estimated revenue, what was ordered vs. what's on the shelf

## Architecture

```
Telugu voice → Whisper small (ASR) → IndicTrans2 (te→en)
Receipt photo → Qwen2.5-VL-7B (OCR)
                          ↓
              LangGraph Orchestrator (Llama-3.2-3B)
         ┌────────────────┼──────────────────┐
  Receipt Parser    Inventory Mgr      Reporting Agent
  (Mistral-7B LoRA) (Mistral-7B)       (Mistral-7B)
         └────────────────┴──► Reorder Agent → HITL PO
                          ↓
              IndicTrans2 (en→te) → Gradio UI
```

All models run locally via **llama.cpp** — no cloud APIs.

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
