"""
hf_inference_receipt.py — Receipt parsing via HF Inference API.

Uses the fine-tuned model pushed to HF Hub after training.
Requires no running Modal service — calls HF Serverless Inference directly.

Push the model to Hub first:
    modal run modal_apps/receipt_llm_service.py::push \\
        --hf-repo-id summerdevlin46/dukaan-saathi-receipt-lora \\
        --hf-token hf_...

Then set HF_RECEIPT_MODEL_REPO (or rely on the default) and optionally HF_TOKEN.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from dukaan_saathi.storage import find_product

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a receipt parser for an Indian convenience store. "
    "Extract all line items from the receipt text. "
    "Return ONLY valid JSON with this structure: "
    '{"supplier": "...", "invoice_no": "...", "date": "YYYY-MM-DD", '
    '"items": [{"product_raw": "...", "qty_cases": 0, "qty_units": 0, '
    '"unit_cost": 0.0, "total": 0.0}], '
    '"subtotal": 0.0, "discount": 0.0, "gst": 0.0, "net_total": 0.0}. '
    "No markdown, no explanation."
)

INSTRUCTION_TEMPLATE = """### Instruction:
{system}

### Input:
{input}

### Response:
"""


def _item_to_row(item: dict[str, Any], supplier: str, document_type: str) -> dict[str, Any]:
    from dukaan_saathi.integrations.llamacpp_receipt import _llm_item_to_row
    return _llm_item_to_row(item, supplier, document_type)


def parse_receipt_via_hf_inference(raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse receipt OCR text using the fine-tuned model on HF Hub via Inference API.
    Falls back to the deterministic parser only if the model repo is not configured.
    Raises on endpoint errors so the caller sees a real failure, not silent determinism.
    """
    from huggingface_hub import InferenceClient
    from dukaan_saathi.parsers.receipt_text import detect_document_type, detect_supplier

    model_repo = os.getenv("HF_RECEIPT_MODEL_REPO", "").strip()
    if not model_repo:
        raise ValueError(
            "HF_RECEIPT_MODEL_REPO is not set. "
            "Push the model first: modal run modal_apps/receipt_llm_service.py::push "
            "--hf-repo-id <repo> --hf-token <token>, "
            "then set HF_RECEIPT_MODEL_REPO=<repo>."
        )

    trace: list[str] = [f"[hf_inference] Calling {model_repo} via HF Inference API"]

    prompt = INSTRUCTION_TEMPLATE.format(system=SYSTEM_PROMPT, input=raw_text)
    client = InferenceClient(token=os.getenv("HF_TOKEN", "") or None)

    response_text = client.text_generation(
        prompt,
        model=model_repo,
        max_new_tokens=768,
        temperature=0.1,
        do_sample=False,
    )

    response_text = response_text.strip()
    parsed = json.loads(response_text)
    items = parsed.get("items", [])
    if not items:
        raise ValueError("HF Inference API returned zero items")

    supplier = parsed.get("supplier") or detect_supplier(raw_text)
    document_type = detect_document_type(raw_text)

    trace.append(f"[hf_inference] Parsed supplier: {supplier}")
    trace.append(f"[hf_inference] Extracted {len(items)} items")

    rows = []
    for item in items:
        row = _item_to_row(item, supplier, document_type)
        rows.append(row)
        if row["matched_product_name"]:
            trace.append(f"[hf_inference] Matched '{row['product_raw']}' → {row['matched_product_name']}")
        else:
            trace.append(f"[hf_inference] Needs owner review: '{row['product_raw']}'")

    trace.append(f"[hf_inference] {len(rows)} candidate line items")
    return rows, trace
