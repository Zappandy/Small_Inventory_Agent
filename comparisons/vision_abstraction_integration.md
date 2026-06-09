# Vision Abstraction Integration

## Integrated

- Added `dukaan_saathi.integrations.vision` as the app-side typed boundary for receipt vision extraction.
- Defined typed names for the Modal backend, model name, raw text, parsed rows, latency, and trace messages.
- Refactored `dukaan_saathi.integrations.modal_receipt` so the existing HTTP client returns a typed `VisionExtractionResult` internally.
- Preserved the public UI-facing API:
  `extract_receipt_with_modal(image_path) -> tuple[list[dict], list[str]]`.
- Preserved the Modal-hosted model split: model inference remains in `modal_apps/receipt_vlm_service.py`; the Gradio app still calls HTTP only.
- Added a MiniCPM raw-text fixture for `samples/receipts/receipt.jpeg` and a regression test for current `parse_receipt_text()` behavior.

## Intentionally Not Merged

- Did not merge `feature/vision` wholesale because it removes protected Modal scripts, benchmark scripts, `AGENTS.md`, and `.env.example`.
- Did not move feature-branch `scripts/vision/*` inference code into the Gradio app runtime.
- Did not adopt the broad `scripts/abcs.py` scaffolding; the app only needs a small receipt-vision result contract right now.
- Did not change the receipt image input away from `type="filepath"`.
- Did not remove the Gradio image extraction button.
- Did not bypass the editable receipt table or owner approval step before inventory writes.
- Did not change inventory write paths; receipt import still goes through `dukaan_saathi.services.inventory`.
