from __future__ import annotations

import json
import os
from typing import Any

import requests

from dukaan_saathi.integrations.llamacpp_receipt import _llm_item_to_row
from dukaan_saathi.parsers.receipt_text import (
    detect_document_type,
    detect_supplier,
    parse_receipt_text,
)


def _extract_json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("parsed") or payload.get("raw_json") or payload.get("text") or ""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError("Modal parser response did not include JSON text")
    return json.loads(value)


def parse_receipt_with_modal_llm(raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    trace: list[str] = ["[modal_llm] Calling Modal receipt parser endpoint"]
    endpoint = (
        os.getenv("MODAL_RECEIPT_LLM_ENDPOINT")
        or os.getenv("MODAL_RECEIPT_PARSER_ENDPOINT")
        or ""
    ).strip()

    if not endpoint:
        rows, fallback_trace = parse_receipt_text(raw_text)
        return rows, trace + [
            "[modal_llm] MODAL_RECEIPT_LLM_ENDPOINT is not set; using deterministic parser",
            *fallback_trace,
        ]

    try:
        response = requests.post(
            endpoint,
            json={"raw_text": raw_text},
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Modal parser response JSON was not an object")

        parsed = _extract_json_payload(payload)
        items = parsed.get("items") or []
        if not items:
            raise ValueError("Modal parser returned zero items")

        supplier = parsed.get("supplier") or detect_supplier(raw_text)
        document_type = detect_document_type(raw_text)
        rows = [
            _llm_item_to_row(item, supplier=supplier, document_type=document_type)
            for item in items
            if isinstance(item, dict)
        ]
        if not rows:
            raise ValueError("Modal parser returned no valid item objects")

        model = str(payload.get("model") or "unknown")
        latency = payload.get("latency_seconds")
        latency_note = f" in {latency:.2f}s" if isinstance(latency, int | float) else ""
        trace.append(f"[modal_llm] Parsed {len(rows)} rows with {model}{latency_note}")
        return rows, trace

    except Exception as exc:
        rows, fallback_trace = parse_receipt_text(raw_text)
        return rows, trace + [
            f"[modal_llm] Fallback to deterministic parser: {exc}",
            *fallback_trace,
        ]
