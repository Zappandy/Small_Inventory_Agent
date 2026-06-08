from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from dukaan_saathi.parsers.receipt_text import parse_receipt_text


def extract_receipt_with_modal(image_path: Any) -> tuple[list[dict], list[str]]:
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
                timeout=180,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        return [], [f"Modal request failed: {exc}"]

    try:
        payload = response.json()
    except ValueError:
        return [], ["Modal endpoint did not return valid JSON."]

    raw_text = payload.get("raw_text") or payload.get("text") or ""
    if raw_text.strip():
        trace.append(f"Modal returned raw text using {payload.get('model', 'unknown model')}")
        rows, parser_trace = parse_receipt_text(raw_text)
        trace.extend(parser_trace)
        return rows, trace

    rows = payload.get("rows") or []
    if rows:
        trace.append(f"Modal returned {len(rows)} structured rows")
        return rows, trace

    return [], [
        "Modal endpoint returned no raw_text or rows.",
        f"Available keys: {list(payload.keys())}",
    ]
