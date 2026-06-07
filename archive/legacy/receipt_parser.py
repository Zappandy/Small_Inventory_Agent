"""
Receipt parser node.

Input:  state["input"] contains raw OCR text OR structured dict from vision model.
Output: state["structured_data"] = validated receipt dict ready for DB write.

Uses the LoRA-finetuned Mistral-7B (trained on Mahalakshmi / Sri Venkateshwara
receipt formats) for line-item extraction and schema validation.

Expected output schema:
{
  "supplier": str,
  "invoice_no": str,
  "date": "YYYY-MM-DD",
  "items": [
    {
      "product_raw": str,   # as written on receipt
      "product_id": str,    # resolved canonical ID
      "qty_cases": int,
      "qty_units": int,
      "unit_cost": float,
      "total": float
    }
  ],
  "subtotal": float,
  "discount": float,
  "gst": float,
  "net_total": float
}
"""

import json
import logging
from state import AgentState
from db.vector_store import resolve_aliases
from db.database import log_receipt
from models.llm import call_llm

logger = logging.getLogger(__name__)

PARSER_SYSTEM = """You are a receipt parser for an Indian convenience store.
Extract all line items from the receipt text below. Product names will be in
English. Quantities may be written as "4×870" or "4 cases" or "30X28=840".
Prices are in Indian Rupees (₹). Dates are in DD/MM/YY format — convert to YYYY-MM-DD.

Return ONLY valid JSON matching this exact schema:
{
  "supplier": "string",
  "invoice_no": "string or null",
  "date": "YYYY-MM-DD",
  "items": [
    {
      "product_raw": "string",
      "qty_cases": integer,
      "qty_units": integer,
      "unit_cost": number,
      "total": number
    }
  ],
  "subtotal": number,
  "discount": number,
  "gst": number,
  "net_total": number
}

If a field is missing, use null for strings and 0 for numbers. Do not add markdown."""


def receipt_parser_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    input_text = state.get("input", "")

    # If vision model already returned structured dict, use it directly
    if isinstance(state.get("structured_data"), dict):
        raw_receipt = state["structured_data"]
        trace.append("receipt_parser: using pre-parsed vision output")
    else:
        # Call finetuned Mistral-7B for text-based extraction
        raw = call_llm(
            model="mistral-7b-receipt",   # points to LoRA-merged GGUF
            system=PARSER_SYSTEM,
            user=input_text,
            max_tokens=1024,
            json_mode=True,
        )
        try:
            raw_receipt = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Receipt parser JSON decode failed")
            raw_receipt = {"items": [], "net_total": 0}

    trace.append(f"receipt_parser: found {len(raw_receipt.get('items', []))} line items")

    # Resolve product aliases for each raw product name
    raw_names = [i.get("product_raw", "") for i in raw_receipt.get("items", [])]
    alias_map = resolve_aliases(raw_names) if raw_names else {}

    for item in raw_receipt.get("items", []):
        item["product_id"] = alias_map.get(item.get("product_raw", ""), None)

    unresolved = [i["product_raw"] for i in raw_receipt["items"] if not i.get("product_id")]
    if unresolved:
        trace.append(f"receipt_parser: unresolved aliases — {unresolved} (needs owner mapping)")

    # Persist to DB
    doc_id = log_receipt(raw_receipt)
    trace.append(f"receipt_parser: logged as receipt doc_id={doc_id}")

    return {
        **state,
        "structured_data": raw_receipt,
        "trace": trace,
    }
