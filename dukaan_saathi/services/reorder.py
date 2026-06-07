from __future__ import annotations

from typing import Any

from dukaan_saathi.storage import get_low_stock


def draft_reorder() -> tuple[list[dict[str, Any]], list[str]]:
    low_stock = get_low_stock()
    trace = ["Checking products against reorder thresholds"]
    rows: list[dict[str, Any]] = []

    for product in low_stock:
        current = int(product["current_stock"])
        threshold = int(product["reorder_threshold"])
        target = int(product["target_stock"])
        suggested_qty = max(target - current, 0)

        unit_cost = float(product.get("last_unit_cost") or 0)
        estimated_total = round(suggested_qty * unit_cost, 2)

        rows.append(
            {
                "supplier": product["supplier"],
                "product_name": product["product_name"],
                "current_stock": current,
                "threshold": threshold,
                "target_stock": target,
                "suggested_order_qty": suggested_qty,
                "unit_cost": unit_cost,
                "estimated_total": estimated_total,
                "reason": f"Current stock {current} is at/below threshold {threshold}; refill to target {target}",
            }
        )

        trace.append(
            f"{product['product_name']}: current={current}, "
            f"threshold={threshold}, target={target}, suggest={suggested_qty}"
        )

    if not rows:
        trace.append("No products need reorder.")

    rows.sort(key=lambda row: (row["supplier"], row["product_name"]))
    return rows, trace