"""
Inventory manager node.

Handles:
- Updating stock levels from parsed receipts (delta = +qty received)
- Updating stock levels from sales notes (delta = -qty sold)
- Answering stock queries
- Checking thresholds and flagging products needing reorder
"""

from state import AgentState
from db.database import (
    update_stock,
    get_stock_levels,
    get_products_below_threshold,
)

import logging
logger = logging.getLogger(__name__)


def inventory_manager_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    intent = state.get("intent", "stock_query")
    policies = state.get("active_policies", {})

    # ── Receipt parse: add incoming stock ────────────────────────────────────
    if intent == "receipt_parse" and state.get("structured_data"):
        items = state["structured_data"].get("items", [])
        for item in items:
            pid = item.get("product_id")
            if not pid:
                continue
            # Convert cases → units using products table
            qty_units = item.get("qty_units", 0) or (
                item.get("qty_cases", 0) * _units_per_case(pid)
            )
            update_stock(
                product_id=pid,
                delta=+qty_units,
                event_type="receipt",
                source_doc=state["structured_data"].get("invoice_no", "unknown"),
                unit_cost=item.get("unit_cost", 0),
            )
            trace.append(f"inventory_mgr: +{qty_units} units → {pid}")

    # ── Sales log: subtract sold stock ──────────────────────────────────────
    elif intent == "sales_log" and state.get("structured_data"):
        items = state["structured_data"].get("items", [])
        for item in items:
            pid = item.get("product_id")
            qty = item.get("qty_units", 0)
            if pid and qty:
                update_stock(
                    product_id=pid,
                    delta=-qty,
                    event_type="sale",
                    source_doc="sales_note",
                    unit_cost=0,
                )
                trace.append(f"inventory_mgr: -{qty} units → {pid}")

    # ── Stock query: build a natural-language response ───────────────────────
    elif intent == "stock_query":
        rows = get_stock_levels()
        summary_lines = [f"{r[0]}: {r[2]} (threshold {r[3]})" for r in rows[:10]]
        state = {
            **state,
            "response": "Current stock levels:\n" + "\n".join(summary_lines),
        }
        trace.append("inventory_mgr: stock query answered")

    # ── Check thresholds → flag reorder candidates ───────────────────────────
    below = get_products_below_threshold()
    if below:
        names = [p["name"] for p in below]
        trace.append(f"inventory_mgr: {len(below)} products below threshold — {names}")
        # Store for reorder agent to consume
        state = {**state, "structured_data": {
            **(state.get("structured_data") or {}),
            "below_threshold": below,
        }}

    # Policy: flag if any price on this receipt is >10% above history
    price_spike_pct = policies.get("price_spike_alert_pct", 10)
    _check_price_spikes(state, price_spike_pct, trace)

    return {**state, "trace": trace}


def _units_per_case(product_id: str) -> int:
    from db.database import get_product
    p = get_product(product_id)
    return p.get("units_per_case", 1) if p else 1


def _check_price_spikes(state: dict, threshold_pct: float, trace: list):
    from db.database import get_last_unit_cost
    items = (state.get("structured_data") or {}).get("items", [])
    for item in items:
        pid = item.get("product_id")
        new_cost = item.get("unit_cost", 0)
        if not pid or not new_cost:
            continue
        last_cost = get_last_unit_cost(pid)
        if last_cost and last_cost > 0:
            pct_change = ((new_cost - last_cost) / last_cost) * 100
            if pct_change > threshold_pct:
                trace.append(
                    f"inventory_mgr: PRICE SPIKE {pid} "
                    f"₹{last_cost:.0f}→₹{new_cost:.0f} (+{pct_change:.1f}%)"
                )
