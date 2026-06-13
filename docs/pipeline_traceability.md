# Pipeline Traceability

Dukaan Saathi uses static diagrams for explanation and JSON run manifests for
auditability. The diagrams show the intended system shape. The manifests under
`data/runs/` record what actually happened in a local or Modal-backed run.

## Fine-tuning DAG

```mermaid
flowchart TD
  A[Seed JSONL<br/>data/finetune/receipt_examples.jsonl] --> B[Modal synthetic generator<br/>modal_apps/receipt_data_generator.py]
  B --> C[Generated JSONL<br/>data/finetune/generated or temp file]
  C --> D[Modal LoRA trainer<br/>modal_apps/receipt_llm_service.py::train]
  D --> E[LoRA adapter<br/>Modal Volume: dukaan-saathi-receipt-lora]
  E --> F[Modal parser endpoint<br/>/parse]

  B -. writes .-> G[Synthetic generation manifest<br/>data/runs/modal-synthetic-*.json]
  D -. writes .-> H[Fine-tune manifest<br/>data/runs/modal-finetune-*.json]
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
  E -->|modal_llm| F[Modal LoRA parser endpoint]
  E -->|llamacpp| G[Local llama.cpp parser]
  E -->|deterministic| H[Rule-based parser]
  F --> I[Editable receipt table]
  G --> I
  H --> I
  I --> J[Owner correction]
  J --> K[Owner approval]
  K --> L[Inventory service]
  L --> M[SQLite stock ledger]

  F -. writes .-> N[Inference manifest<br/>data/runs/receipt-inference-*.json]
  L -. writes .-> O[Inventory approval manifest<br/>data/runs/inventory-approval-*.json]
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

