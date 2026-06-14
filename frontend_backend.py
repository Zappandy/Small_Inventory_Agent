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
from dukaan_saathi.integrations.command_nlu import extract_command_slots
from dukaan_saathi.parsers.stock_command import parse_stock_command
from dukaan_saathi.services.reorder import draft_reorder
from dukaan_saathi.storage import find_product


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
            "suggested_name": (result or {}).get("suggested_name"),
            "suggested_qty": (result or {}).get("suggested_qty"),
            "raw_command": (result or {}).get("raw_command", ""),
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


def _action_from_nlu(slots: dict, trace: list[str]) -> dict[str, Any] | None:
    """
    Build a normalised action dict from NLU slots + catalog lookup.

    Returns None if the NLU intent is unknown or unusable, so the caller can
    fall through to the deterministic parser.
    """
    intent = slots.get("intent", "unknown")
    product_name = slots.get("product_name") or ""
    quantity = slots.get("quantity")

    trace.append(
        f"Observation: intent={intent!r}, product={product_name!r}, "
        f"qty={quantity}, unit={slots.get('unit')!r}, "
        f"confidence={slots.get('confidence')!r}, model={slots.get('model')!r}"
    )

    if intent == "unknown" or not product_name:
        trace.append("Thought: NLU intent or product unclear; handing off to deterministic parser.")
        return None

    # mark_out/mark_low with a non-trivial quantity is contradictory
    # (model probably misread "add 10 X" as mark_out). Fall through so the
    # deterministic keyword parser can handle it correctly.
    if intent in {"mark_out", "mark_low"} and quantity is not None and float(quantity) > 1:
        trace.append(
            f"Thought: NLU returned {intent!r} with qty={quantity} — "
            "contradictory signal; handing off to deterministic parser."
        )
        return None

    trace.append(f"Thought: Look up '{product_name}' in the catalog (strict fuzzy threshold).")
    catalog_hit = find_product(product_name, fuzzy_cutoff=0.75)

    if catalog_hit is None:
        trace.append(f"Observation: '{product_name}' not in catalog — will surface create-new prompt.")
        return {
            "status": "needs_review",
            "message": "Could not match a known product.",
            "raw_command": product_name,
            "suggested_name": product_name,
            "suggested_qty": int(quantity) if quantity is not None else None,
        }

    pid = catalog_hit["id"]
    name = catalog_hit["name"]
    trace.append(f"Observation: Matched to catalog product '{name}' (id={pid!r}).")
    trace.append("Thought: Return the proposed action for owner approval; do not write inventory.")

    if intent == "add_stock":
        qty = quantity if quantity is not None else 1
        return {
            "status": "pending_approval",
            "type": "add_stock",
            "product_id": pid,
            "product_name": name,
            "delta": qty,
            "reason": f"NLU: owner said stock arrived.",
        }
    if intent in {"set_stock", "mark_low", "mark_out"}:
        if intent == "mark_out":
            qty = 0
        elif intent == "mark_low":
            qty = 1
        else:
            qty = quantity if quantity is not None else 0
        return {
            "status": "pending_approval",
            "type": "set_stock",
            "product_id": pid,
            "product_name": name,
            "new_stock": qty,
            "reason": f"NLU: intent={intent}.",
        }

    return None


def run_command_parse(text: str) -> dict[str, Any]:
    """
    Parse a typed/voice command and normalise to the shape _h_voice_command expects:
      action, product, product_id, quantity, unit, confidence, trace

    Priority:
    1. Modal NLU model (semantic slot extraction, handles new products + Telugu)
    2. ReAct agent wrapping deterministic parser (catalog-only, keyword-based)
    3. Bare deterministic parser (if ReAct fails)
    """
    # 1. Try NLU-assisted path
    slots = extract_command_slots(text)
    if slots is not None:
        trace = [
            "Thought: Identify the user workflow and select the smallest safe tool chain.",
            f"Thought: Send command to NLU model for semantic slot extraction.",
            "Action: command_nlu_extract",
        ]
        action = _action_from_nlu(slots, trace)
        if action is not None:
            return _normalise_stock_action(action, trace)
        # NLU returned unknown intent — fall through with its trace prefix
        result, det_trace = parse_stock_command(text)
        trace.append("Action: parse_stock_command_tool (deterministic fallback)")
        trace.extend(det_trace)
        return _normalise_stock_action(result, trace)

    # 2. ReAct agent + deterministic parser
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
