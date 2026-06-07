from __future__ import annotations

from typing import Any

import pandas as pd

from dukaan_saathi.storage import apply_stock_delta, find_product, set_product_stock


def approve_command_action(action: dict[str, Any] | None) -> tuple[str, list[str]]:
    trace: list[str] = []

    if not action:
        return "No pending action to approve.", ["No pending action."]

    if action.get("status") != "pending_approval":
        return "This action is not ready for approval.", [f"Action status: {action.get('status')}"]

    action_type = action.get("type")
    product_id = action.get("product_id")

    if not product_id:
        return "Missing product_id.", ["Cannot approve action without product_id."]

    if action_type == "set_stock":
        result = set_product_stock(
            product_id=product_id,
            new_stock=int(action["new_stock"]),
            event_type="command",
            source_doc="typed_command",
            note=action.get("reason", ""),
        )
        trace.append(
            f"Applied stock update: {result['product_name']} "
            f"{result['previous_stock']} → {result['new_stock']}"
        )
        return f"Approved: {result['product_name']} stock is now {result['new_stock']}.", trace

    if action_type == "add_stock":
        result = apply_stock_delta(
            product_id=product_id,
            delta=int(action["delta"]),
            event_type="command",
            source_doc="typed_command",
            note=action.get("reason", ""),
        )
        trace.append(
            f"Applied stock addition: {result['product_name']} "
            f"{result['previous_stock']} → {result['new_stock']}"
        )
        return f"Approved: added {result['delta']} to {result['product_name']}.", trace

    return f"Unknown action type: {action_type}", [f"Unknown action type: {action_type}"]


def approve_receipt_rows(receipt_rows: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[str, list[str]]:
    if receipt_rows is None:
        return "No receipt rows to approve.", ["No rows provided."]

    if isinstance(receipt_rows, pd.DataFrame):
        rows = receipt_rows.to_dict(orient="records")
    else:
        rows = receipt_rows

    if not rows:
        return "No receipt rows to approve.", ["No rows found."]

    approved = 0
    skipped = 0
    trace: list[str] = []

    for row in rows:
        should_apply = row.get("apply", True)

        if isinstance(should_apply, str):
            should_apply = should_apply.strip().lower() not in {"false", "no", "0", ""}

        if not should_apply:
            skipped += 1
            trace.append(f"Skipped by owner: {row.get('product_raw', '')}")
            continue

        product_id = str(row.get("matched_product_id") or "").strip()
        product_name = str(
            row.get("matched_product_name")
            or row.get("product_raw")
            or ""
        ).strip()

        if not product_id:
            matched = find_product(product_name)
            if matched:
                product_id = matched["id"]
                product_name = matched["name"]

        if not product_id:
            skipped += 1
            trace.append(f"Skipped unknown product: {product_name}")
            continue

        try:
            quantity = int(float(row.get("quantity", 0)))
        except (TypeError, ValueError):
            skipped += 1
            trace.append(f"Skipped {product_name}: invalid quantity")
            continue

        if quantity <= 0:
            skipped += 1
            trace.append(f"Skipped {product_name}: quantity must be positive")
            continue

        try:
            unit_cost = float(row.get("unit_price") or 0)
        except (TypeError, ValueError):
            unit_cost = 0.0

        result = apply_stock_delta(
            product_id=product_id,
            delta=quantity,
            event_type="receipt",
            source_doc=str(row.get("supplier") or "receipt"),
            unit_cost=unit_cost,
            note=f"Receipt import: {row.get('product_raw', product_name)}",
        )

        approved += 1
        trace.append(
            f"Updated {result['product_name']}: "
            f"{result['previous_stock']} → {result['new_stock']}"
        )

    return f"Approved {approved} rows. Skipped {skipped}.", trace
