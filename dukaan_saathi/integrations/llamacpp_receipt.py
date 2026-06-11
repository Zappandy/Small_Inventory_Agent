"""
llamacpp_receipt.py — Receipt text → structured rows via fine-tuned Llama-3.2-3B on llama.cpp.

Calls the fine-tuned model on port 8082 to parse OCR receipt text into structured line items.
Returns the same (rows, trace) signature as parsers.receipt_text.parse_receipt_text so it
can be dropped in as an alternative backend.

Falls back to the deterministic parser if the LLM server is unavailable or returns bad JSON.
"""

from __future__ import annotations

import json
import logging
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


def _llm_item_to_row(item: dict[str, Any], supplier: str, document_type: str) -> dict[str, Any]:
    product_raw = str(item.get("product_raw", "")).strip()
    qty_units = int(item.get("qty_units") or item.get("qty_cases") or 0)
    unit_price = float(item.get("unit_cost") or 0) or None
    total_price = float(item.get("total") or 0) or None

    matched = find_product(product_raw)
    matched_product_id = matched["id"] if matched else ""
    matched_product_name = matched["name"] if matched else ""

    warning_parts = []
    if not matched:
        warning_parts.append("No catalog match; owner must map or skip.")
    if item.get("needs_review"):
        warning_parts.append("Flagged for review by parser.")

    return {
        "apply": bool(matched),
        "document_type": document_type,
        "supplier": supplier,
        "product_raw": product_raw,
        "matched_product_id": matched_product_id,
        "matched_product_name": matched_product_name,
        "quantity_raw": str(qty_units),
        "quantity": qty_units,
        "unit_price": unit_price,
        "total_price": total_price,
        "confidence": 0.85 if matched else 0.5,
        "warning": " | ".join(warning_parts),
    }


def parse_receipt_via_llm(raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse receipt OCR text using the fine-tuned Llama-3.2-3B model via llama.cpp.
    Falls back to the deterministic parser on any failure.
    """
    from dukaan_saathi.integrations.llamacpp_llm import call_llm
    from dukaan_saathi.parsers.receipt_text import parse_receipt_text, detect_supplier, detect_document_type

    trace: list[str] = ["[llamacpp] Calling fine-tuned Llama-3.2-3B for receipt parsing"]

    try:
        response_text = call_llm(
            model="llama-3.2-3b-receipt",
            system=SYSTEM_PROMPT,
            user=raw_text,
            max_tokens=768,
            json_mode=True,
            temperature=0.1,
        )

        if '"error"' in response_text:
            raise ValueError(f"LLM returned error: {response_text}")

        parsed = json.loads(response_text)
        items = parsed.get("items", [])

        if not items:
            raise ValueError("LLM returned zero items")

        supplier = parsed.get("supplier", detect_supplier(raw_text))
        document_type = detect_document_type(raw_text)

        trace.append(f"[llamacpp] Parsed supplier: {supplier}")
        trace.append(f"[llamacpp] Extracted {len(items)} items from LLM response")

        rows = []
        for item in items:
            row = _llm_item_to_row(item, supplier, document_type)
            rows.append(row)
            if row["matched_product_name"]:
                trace.append(f"[llamacpp] Matched '{row['product_raw']}' → {row['matched_product_name']}")
            else:
                trace.append(f"[llamacpp] Needs owner review: '{row['product_raw']}'")

        trace.append(f"[llamacpp] Extracted {len(rows)} candidate line items")
        return rows, trace

    except Exception as exc:
        logger.warning(f"llamacpp_receipt falling back to deterministic parser: {exc}")
        trace.append(f"[llamacpp] Fallback to deterministic parser: {exc}")
        fallback_rows, fallback_trace = parse_receipt_text(raw_text)
        return fallback_rows, trace + fallback_trace
