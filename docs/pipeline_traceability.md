# Pipeline Traceability

Dukaan Saathi uses static diagrams for explanation and JSON run manifests for
auditability. The diagrams show the intended system shape. The manifests under
`data/runs/` record what actually happened in a local, Modal-backed, or
HF-backed run.

## Fine-tuning DAG

```mermaid
flowchart TD
  A[Seed JSONL<br/>data/finetune/receipt_examples.jsonl] --> B[Modal synthetic generator<br/>modal_apps/receipt_data_generator.py]
  B --> C[Generated JSONL<br/>data/finetune/generated or temp file]
  C --> D[Modal LoRA trainer<br/>modal_apps/receipt_llm_service.py::train]
  D --> E[LoRA adapter<br/>Modal Volume: dukaan-saathi-receipt-lora]
  E --> F[Modal parser endpoint<br/>/parse]
  E --> G[Modal push job<br/>receipt_llm_service.py::push]
  G --> H[Merged model<br/>Hugging Face Hub]

  B -. writes .-> I[Synthetic generation manifest<br/>data/runs/modal-synthetic-*.json]
  D -. writes .-> J[Fine-tune manifest<br/>data/runs/modal-finetune-*.json]
```

The fine-tune manifests include dataset paths, SHA256 hashes, record counts,
model IDs, training parameters, Modal app names, and final status. They do not
store Modal tokens or Hugging Face tokens.

## Inference DAG

```mermaid
flowchart TD
  A[Receipt image] --> B[MiniCPM-V OCR endpoint]
  B --> C[Raw receipt text]
  D[Pasted/sample receipt text] --> C
  C --> E{Receipt backend}
  E -->|hf_inference| F[HF Inference API<br/>HF_RECEIPT_MODEL_REPO]
  E -->|modal_llm| G[Modal LoRA parser endpoint]
  E -->|llamacpp| H[Local llama.cpp parser]
  E -->|deterministic| I[Rule-based parser]
  F --> J[Editable receipt table]
  G --> J
  H --> J
  I --> J
  J --> K[Owner correction]
  K --> L[Owner approval]
  L --> M[Inventory service]
  M --> N[SQLite stock ledger]

  G -. writes .-> O[Inference manifest<br/>data/runs/receipt-inference-*.json]
  M -. writes .-> P[Inventory approval manifest<br/>data/runs/inventory-approval-*.json]
```

Inventory changes remain approval-gated. Model output can only create editable
candidate rows; approved stock changes go through
`dukaan_saathi/services/inventory.py`.

## Runtime Artifacts

`TRACE_DIR` controls where manifests are written. The default is:

```text
data/runs/
```

These files are local runtime evidence and are ignored by git.
