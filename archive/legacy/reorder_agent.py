"""
Reorder agent node.

Takes the list of products below threshold, groups them by supplier,
applies historical order quantity patterns from ChromaDB,
and builds a draft PO for each supplier.

Does NOT place orders — only produces po_draft for HITL approval.
"""

import json
from state import AgentState
from db.database import get_product, get_supplier, get_pending_pos
from db.vector_store import get_order_pattern
from models.llm import call_llm

REORDER_SYSTEM = """You are a purchase order assistant for a small convenience store
in Hyderabad, India. Given a list of low-stock products with their supplier and
historical order quantities, generate a grouped purchase order suggestion.

Apply these rules:
1. Group all items from the same supplier into one PO
2. Suggest quantity = max(reorder_threshold × 2, last_order_qty)
3. Explain the suggestion reason in simple English (will be translated to Telugu)
4. Check minimum order value policy per supplier

Return ONLY valid JSON:
{
  "purchase_orders": [
    {
      "supplier_id": "str",
      "supplier_name": "str",
      "items": [
        {
          "product_id": "str",
          "product_name": "str",
          "suggested_qty_cases": int,
          "unit_cost": float,
          "total": float,
          "reason_en": "str"
        }
      ],
      "po_total": float,
      "meets_min_order": bool
    }
  ]
}"""


def reorder_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    policies = state.get("active_policies", {})

    below = (state.get("structured_data") or {}).get("below_threshold", [])
    if not below:
        trace.append("reorder_agent: no products below threshold, skipping")
        return {**state, "trace": trace}

    # Enrich each product with supplier info and order history
    enriched = []
    for product in below:
        pid = product.get("product_id") or product.get("id")
        p = get_product(pid) or product
        supplier = get_supplier(p.get("supplier_id", ""))
        pattern = get_order_pattern(pid)   # from ChromaDB historical patterns

        enriched.append({
            "product_id": pid,
            "product_name": p.get("name", pid),
            "supplier_id": p.get("supplier_id", "unknown"),
            "supplier_name": supplier.get("name", "Unknown") if supplier else "Unknown",
            "current_stock": product.get("current_stock", 0),
            "reorder_threshold": p.get("reorder_threshold", 2),
            "last_order_qty_cases": pattern.get("avg_qty_cases", 2),
            "unit_cost": p.get("last_unit_cost", 0),
            "min_order_value": policies.get(
                "min_order_per_supplier", {}
            ).get(supplier.get("name", ""), 0) if supplier else 0,
        })

    trace.append(f"reorder_agent: enriched {len(enriched)} products for PO generation")

    # Call LLM to generate grouped PO suggestions
    raw = call_llm(
        model="mistral-7b",
        system=REORDER_SYSTEM,
        user=json.dumps(enriched, ensure_ascii=False),
        max_tokens=1024,
        json_mode=True,
    )

    try:
        result = json.loads(raw)
        pos = result.get("purchase_orders", [])
    except json.JSONDecodeError:
        trace.append("reorder_agent: LLM JSON parse failed, building simple PO")
        pos = _fallback_po(enriched)

    # Flag POs that don't meet minimum order value
    for po in pos:
        if not po.get("meets_min_order", True):
            trace.append(
                f"reorder_agent: WARNING {po['supplier_name']} PO ₹{po['po_total']:.0f} "
                f"below min order — flagged"
            )

    trace.append(f"reorder_agent: drafted {len(pos)} purchase orders for approval")

    # Flatten into single po_draft structure
    po_draft = {
        "purchase_orders": pos,
        "status": "pending_approval",
    }

    return {**state, "po_draft": po_draft, "trace": trace}


def _fallback_po(enriched: list) -> list:
    """Simple supplier-grouped PO without LLM, used as fallback."""
    by_supplier: dict = {}
    for item in enriched:
        sid = item["supplier_id"]
        if sid not in by_supplier:
            by_supplier[sid] = {
                "supplier_id": sid,
                "supplier_name": item["supplier_name"],
                "items": [],
                "po_total": 0.0,
                "meets_min_order": True,
            }
        qty = max(item["reorder_threshold"] * 2, item["last_order_qty_cases"])
        total = qty * item["unit_cost"]
        by_supplier[sid]["items"].append({
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "suggested_qty_cases": qty,
            "unit_cost": item["unit_cost"],
            "total": total,
            "reason_en": f"Stock at {item['current_stock']}, threshold {item['reorder_threshold']}",
        })
        by_supplier[sid]["po_total"] += total

    return list(by_supplier.values())
