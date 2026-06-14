"""
LangChain-compatible tool wrappers around database.py.
These are the tools the SLM agent will call when wired up via LangGraph.

SLM_INTEGRATION_POINT: bind these tools to the language model using
    llm.bind_tools([get_inventory, flag_low_stock, ...])
"""

from __future__ import annotations
import json
import kirana_db as db


# ── Read tools ────────────────────────────────────────────────────────────────

def get_inventory() -> str:
    """Return full inventory as a JSON string."""
    products = db.get_all_products()
    slim = [
        {
            "id": p["id"],
            "name": p["name"],
            "name_te": p["name_local"],
            "category": p["category"],
            "quantity": p["quantity"],
            "unit": p["unit"],
            "min_stock": p["min_stock"],
            "sell_price": p["sell_price"],
            "expiry_date": p["expiry_date"],
        }
        for p in products
    ]
    return json.dumps(slim, ensure_ascii=False)


def get_low_stock_items() -> str:
    """Return products at or below minimum stock level."""
    items = db.get_low_stock()
    return json.dumps(
        [{"id": i["id"], "name": i["name"], "qty": i["quantity"],
          "min": i["min_stock"], "unit": i["unit"]} for i in items],
        ensure_ascii=False,
    )


def get_expiring_items(days: int = 7) -> str:
    """Return products expiring within N days."""
    items = db.get_expiring_soon(days)
    return json.dumps(
        [{"id": i["id"], "name": i["name"], "qty": i["quantity"],
          "unit": i["unit"], "expiry": i["expiry_date"]} for i in items],
        ensure_ascii=False,
    )


def get_top_selling_items(n: int = 10) -> str:
    """Return top-N sellers by volume over last 30 days."""
    items = db.get_top_sellers(n)
    return json.dumps(
        [{"name": i["name"], "sold": i["total_sold"], "unit": i["unit"]} for i in items],
        ensure_ascii=False,
    )


def get_velocity(product_id: int) -> float:
    """Return average daily sales (units/day) for a product over last 30 days."""
    return db.get_daily_velocity(product_id)


# ── Write tools ───────────────────────────────────────────────────────────────

def add_stock(product_id: int, quantity: float) -> str:
    """Increment stock for a product."""
    db.adjust_stock(product_id, quantity, mode="add")
    p = db.get_product(product_id)
    return json.dumps({"status": "ok", "new_quantity": p["quantity"] if p else None})


def set_stock(product_id: int, quantity: float) -> str:
    """Set absolute stock level for a product."""
    db.adjust_stock(product_id, quantity, mode="set")
    return json.dumps({"status": "ok"})


def create_restock_order(
    product_name: str,
    qty_needed: float,
    unit: str,
    reason: str,
    product_id: int | None = None,
    ai_confidence: float = 0.8,
) -> str:
    """Create a pending restock order (requires human approval before acting)."""
    oid = db.create_order(
        product_name=product_name,
        qty_needed=qty_needed,
        unit=unit,
        reason=reason,
        product_id=product_id,
        ai_confidence=ai_confidence,
    )
    return json.dumps({"status": "pending_approval", "order_id": oid})


def approve_order(order_id: int) -> str:
    db.update_order_status(order_id, "approved")
    return json.dumps({"status": "approved"})


def reject_order(order_id: int) -> str:
    db.update_order_status(order_id, "rejected")
    return json.dumps({"status": "rejected"})


def record_sale_tool(product_id: int, qty: float, price: float) -> str:
    sid = db.record_sale(product_id, qty, price)
    return json.dumps({"status": "ok", "sale_id": sid})


def find_product(name: str) -> str:
    results = db.find_by_name(name)
    return json.dumps(
        [{"id": r["id"], "name": r["name"], "qty": r["quantity"], "unit": r["unit"]}
         for r in results],
        ensure_ascii=False,
    )


# ── Tool registry (for LangGraph tool-calling node) ──────────────────────────

TOOL_REGISTRY = {
    "get_inventory":          get_inventory,
    "get_low_stock_items":    get_low_stock_items,
    "get_expiring_items":     get_expiring_items,
    "get_top_selling_items":  get_top_selling_items,
    "get_velocity":           get_velocity,
    "add_stock":              add_stock,
    "set_stock":              set_stock,
    "create_restock_order":   create_restock_order,
    "approve_order":          approve_order,
    "reject_order":           reject_order,
    "record_sale_tool":       record_sale_tool,
    "find_product":           find_product,
}


def dispatch_tool(tool_name: str, **kwargs):
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        return fn(**kwargs)
    except Exception as e:
        return json.dumps({"error": str(e)})
