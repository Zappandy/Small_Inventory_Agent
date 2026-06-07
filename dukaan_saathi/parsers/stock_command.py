from __future__ import annotations

import re
from typing import Any

from dukaan_saathi.storage import find_product


OUT_OF_STOCK_MARKERS = [
    "out",
    "finished",
    "empty",
    "khatam",
    "ayipoyindi",
    "అయిపోయింది",
]

LOW_STOCK_MARKERS = [
    "low",
    "less",
    "తక్కువ",
]

ADD_STOCK_MARKERS = [
    "add",
    "received",
    "arrived",
    "stock add",
    "add cheyyi",
]


def parse_stock_command(command: str) -> tuple[dict[str, Any], list[str]]:
    command = (command or "").strip()
    trace = [f"Received command: {command}"]

    if not command:
        return {"status": "error", "message": "No command provided."}, trace

    product = find_product(command)
    if product is None:
        trace.append("No product matched.")
        return {
            "status": "needs_review",
            "message": "Could not match a known product.",
            "raw_command": command,
        }, trace

    trace.append(f"Matched product: {product['name']}")

    lower = command.lower()
    numbers = [int(n) for n in re.findall(r"\d+", command)]

    if any(marker in lower for marker in OUT_OF_STOCK_MARKERS) or "అయిపోయింది" in command:
        trace.append("Detected intent: stockout")
        trace.append("Proposed action: set stock to 0")
        return {
            "status": "pending_approval",
            "type": "set_stock",
            "product_id": product["id"],
            "product_name": product["name"],
            "new_stock": 0,
            "reason": f"Owner said product is out of stock: {command}",
        }, trace

    if any(marker in lower for marker in ADD_STOCK_MARKERS):
        qty = numbers[-1] if numbers else 1
        trace.append("Detected intent: add stock")
        trace.append(f"Proposed action: add {qty}")
        return {
            "status": "pending_approval",
            "type": "add_stock",
            "product_id": product["id"],
            "product_name": product["name"],
            "delta": qty,
            "reason": f"Owner said stock arrived: {command}",
        }, trace

    if any(marker in lower for marker in LOW_STOCK_MARKERS):
        trace.append("Detected intent: mark low stock")
        trace.append("Proposed action: set stock to 1")
        return {
            "status": "pending_approval",
            "type": "set_stock",
            "product_id": product["id"],
            "product_name": product["name"],
            "new_stock": 1,
            "reason": f"Owner said stock is low: {command}",
        }, trace

    if numbers:
        qty = numbers[-1]
        trace.append("Detected intent: set stock count")
        trace.append(f"Proposed action: set stock to {qty}")
        return {
            "status": "pending_approval",
            "type": "set_stock",
            "product_id": product["id"],
            "product_name": product["name"],
            "new_stock": qty,
            "reason": f"Owner provided stock count: {command}",
        }, trace

    trace.append("Product matched, but intent was unclear.")
    return {
        "status": "needs_review",
        "message": "Product matched, but command intent was unclear.",
        "product_id": product["id"],
        "product_name": product["name"],
        "raw_command": command,
    }, trace
