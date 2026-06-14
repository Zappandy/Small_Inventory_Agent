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
from dukaan_saathi.agent.react_agent import get_react_agent
from dukaan_saathi.parsers.stock_command import parse_stock_command
from dukaan_saathi.services.reorder import draft_reorder


def _normalise_stock_action(result: dict[str, Any] | None, trace: list[str]) -> dict[str, Any]:
    action_type = (result or {}).get("type")
    status = (result or {}).get("status", "error")

    if not result or status in ("error", "needs_review") or not action_type:
        return {
            "action": "unknown",
            "product": (result or {}).get("product_name", ""),
            "product_id": (result or {}).get("product_id"),
            "quantity": None,
            "unit": "",
            "confidence": "low",
            "trace": trace,
        }

    qty = result.get("delta") if action_type == "add_stock" else result.get("new_stock")
    return {
        "action": action_type,
        "product": result.get("product_name", ""),
        "product_id": result.get("product_id"),
        "quantity": qty,
        "unit": "",
        "confidence": "high",
        "trace": trace,
    }


def run_command_parse(text: str) -> dict[str, Any]:
    """
    Parse a typed/voice command and normalise to the shape _h_voice_command expects:
      action, product, product_id, quantity, unit, confidence, trace
    """
    try:
        react_result = get_react_agent().parse_stock_command(text)
        trace = list(react_result.trace)
        return _normalise_stock_action(react_result.action, trace)
    except Exception as exc:
        result, trace = parse_stock_command(text)
        trace = [f"ReAct agent unavailable; using deterministic parser: {exc}", *trace]
        return _normalise_stock_action(result, trace)


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

    low = db.get_low_stock()
    expiring = db.get_expiring_soon(7)
    expired = db.get_expired()

    if low:
        names = ", ".join(row["name"] for row in low[:3])
        more = f" and {len(low) - 3} more" if len(low) > 3 else ""
        inventory_msg = f"{len(low)} item(s) are low: {names}{more}."
    else:
        inventory_msg = "All active items are above reorder thresholds."

    if expired:
        expiry_msg = f"{len(expired)} expired item(s) need immediate review."
    elif expiring:
        names = ", ".join(row["name"] for row in expiring[:3])
        more = f" and {len(expiring) - 3} more" if len(expiring) > 3 else ""
        expiry_msg = f"{len(expiring)} item(s) expire within 7 days: {names}{more}."
    else:
        expiry_msg = "No items expire in the next 7 days."

    return {
        "ai_inventory_analysis": inventory_msg,
        "ai_seasonal_advice": "Use the Seasonal page for upcoming festival stock planning.",
        "ai_expiry_advice": expiry_msg,
        "suggested_orders": reorder_rows,
        "needs_human_approval": bool(reorder_rows),
        "orders_inserted": inserted,
        "trace": trace,
    }
