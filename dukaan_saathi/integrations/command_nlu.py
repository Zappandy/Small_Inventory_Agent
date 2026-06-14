from __future__ import annotations

import os

import requests


def extract_command_slots(command: str) -> dict | None:
    """
    Call the Modal NLU endpoint to extract structured slots from a raw command.

    Returns a dict with keys: intent, product_name, quantity, unit, confidence, model.
    Returns None if the endpoint is not configured, the request fails, or the
    response cannot be parsed — callers must fall back to the deterministic parser.

    Safety boundary:
    - This only returns structured slots.
    - It does not look up products.
    - It does not apply inventory changes.
    - It does not approve anything.
    """
    endpoint = os.getenv("MODAL_NLU_ENDPOINT", "").strip()
    if not endpoint:
        return None

    try:
        response = requests.post(
            endpoint,
            json={"command": command},
            timeout=60,
        )
        response.raise_for_status()
        slots = response.json()
    except (requests.RequestException, ValueError):
        return None

    intent = slots.get("intent", "unknown")
    if intent not in {"add_stock", "set_stock", "mark_low", "mark_out", "unknown"}:
        return None

    return {
        "intent": intent,
        "product_name": slots.get("product_name"),
        "quantity": slots.get("quantity"),
        "unit": slots.get("unit"),
        "confidence": slots.get("confidence", "medium"),
        "model": slots.get("model", "unknown"),
    }
