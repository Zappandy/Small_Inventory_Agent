from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from dukaan_saathi.parsers.receipt_text import parse_receipt_text


def extract_receipt_with_modal(image_path: Any) -> tuple[list[dict], list[str]]:
    """
    Thin client for a Modal-hosted HF vision model.

    This file should NOT load the model.
    It only sends the receipt image to the model endpoint and adapts the response
    into our existing receipt approval pipeline.
    """
    trace: list[str] = ["Starting receipt image extraction via Modal"]

    endpoint = os.getenv("MODAL_RECEIPT_ENDPOINT", "").strip()
    if not endpoint:
        return [], [
            "MODAL_RECEIPT_ENDPOINT is not set.",
            "Model endpoint is not connected yet.",
            "Use pasted/sample receipt text for the MVP path.",
        ]

    if not image_path:
        return [], ["No receipt image provided."]

    path = Path(str(image_path))
    if not path.exists():
        return [], [f"Receipt image path does not exist: {path}"]

    try:
        with path.open("rb") as f:
            response = requests.post(
                endpoint,
                files={"image": (path.name, f, "image/jpeg")},
                timeout=120,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        return [], [f"Modal request failed: {exc}"]

    try:
        payload = response.json()
    except ValueError:
        return [], ["Modal endpoint did not return valid JSON."]

    if "raw_text" in payload:
        raw_text = payload.get("raw_text") or ""
        trace.append("Modal returned raw OCR/model text")
        rows, parser_trace = parse_receipt_text(raw_text)
        trace.extend(parser_trace)
        return rows, trace

    if "rows" in payload:
        rows = payload.get("rows") or []
        trace.append(f"Modal returned {len(rows)} structured rows")
        trace.append("Rows still require owner review before inventory update")
        return rows, trace

    return [], [
        "Modal endpoint returned JSON, but no usable receipt data.",
        f"Available keys: {list(payload.keys())}",
    ]