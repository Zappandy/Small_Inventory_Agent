"""
frontend_backend.py

Adapter between the custom HTML frontend and the real Dukaan Saathi backend.

Purpose:
- Keep the stakeholder-friendly custom frontend.
- Do not use the imported root LangGraph stack.
- Route command parsing, reorder drafting, OCR, HF receipt parsing, and speech
  through the canonical dukaan_saathi backend.
"""

from __future__ import annotations

from typing import Any

import kirana_db as db
from dukaan_saathi.parsers.stock_command import parse_stock_command
from dukaan_saathi.services.reorder import draft_reorder


def run_command_parse(text: str) -> dict[str, Any]:
    """
    Parse a typed/voice command using the real Dukaan Saathi backend parser.

    This function does not write inventory.
    Inventory writes must happen only after explicit UI approval.
    """
    action, trace = parse_stock_command(text)

    if not action:
        return {
            "action": "unknown",
            "product": "",
            "quantity": None,
            "unit": "",
            "confidence": "low",
            "trace": trace,
        }

    return {
        **action,
        "confidence": action.get("confidence", "medium"),
        "trace": trace,
    }


def run_analysis() -> dict[str, Any]:
    """
    Produce dashboard/reorder suggestions using deterministic Dukaan Saathi services.

    This replaces the Rahul LangGraph analysis path.
    """
    reorder_rows, trace = draft_reorder()

    # Store pending orders for the pretty Orders page, if possible.
    inserted = 0
    try:
        orders = []
        for row in reorder_rows:
            orders.append(
                {
                    "product_id": row.get("product_id") or row.get("matched_product_id") or "",
                    "product_name": row.get("product_name") or row.get("product_raw") or "Unknown item",
                    "qty_needed": row.get("suggested_order_qty") or row.get("quantity") or 0,
                    "unit": row.get("unit") or row.get("unit_type") or "unit",
                    "reason": row.get("reason") or "Below reorder threshold",
                    "ai_confidence": row.get("confidence") or 0.8,
                }
            )
        inserted = db.insert_orders(orders)
    except Exception as exc:
        trace.append(f"[frontend_backend] Could not insert pending orders: {exc}")

    if reorder_rows:
        inventory_msg = f"{len(reorder_rows)} item(s) need reorder review."
    else:
        inventory_msg = "Inventory looks okay against current reorder thresholds."

    return {
        "ai_inventory_analysis": inventory_msg,
        "ai_seasonal_advice": "Seasonal recommendations are available in the Seasonal page.",
        "ai_expiry_advice": "Review expiring-stock cards for near-expiry items.",
        "suggested_orders": reorder_rows,
        "needs_human_approval": bool(reorder_rows),
        "orders_inserted": inserted,
        "trace": trace,
    }
