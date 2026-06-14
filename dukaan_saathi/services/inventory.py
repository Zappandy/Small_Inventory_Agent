from __future__ import annotations

from typing import Any

import pandas as pd

from dukaan_saathi.storage import apply_stock_delta, find_product, set_product_stock
from dukaan_saathi.traceability import new_run_id, utc_now_iso, write_manifest


def apply_owner_stock_delta(
    *,
    product_id: str,
    delta: float,
    event_type: str,
    source_doc: str,
    note: str = "",
    unit_cost: float | None = None,
) -> dict[str, Any]:
    """Apply an owner-approved stock delta through the canonical service layer."""
    return apply_stock_delta(
        product_id=product_id,
        delta=float(delta),
        event_type=event_type,
        source_doc=source_doc,
        unit_cost=unit_cost,
        note=note,
    )


def set_owner_stock(
    *,
    product_id: str,
    new_stock: float,
    event_type: str,
    source_doc: str,
    note: str = "",
) -> dict[str, Any]:
    """Set owner-approved absolute stock through the canonical service layer."""
    return set_product_stock(
        product_id=product_id,
        new_stock=float(new_stock),
        event_type=event_type,
        source_doc=source_doc,
        note=note,
    )


def approve_command_action(action: dict[str, Any] | None) -> tuple[str, list[str]]:
    trace: list[str] = []
    run_id = new_run_id("inventory-approval")
    started_at = utc_now_iso()

    if not action:
        return "No pending action to approve.", ["No pending action."]

    if action.get("status") != "pending_approval":
        return "This action is not ready for approval.", [f"Action status: {action.get('status')}"]

    action_type = action.get("type")
    product_id = action.get("product_id")

    if not product_id:
        return "Missing product_id.", ["Cannot approve action without product_id."]

    if action_type == "set_stock":
        result = set_owner_stock(
            product_id=product_id,
            new_stock=float(action["new_stock"]),
            event_type="command",
            source_doc="typed_command",
            note=action.get("reason", ""),
        )
        trace.append(
            f"Applied stock update: {result['product_name']} "
            f"{result['previous_stock']} → {result['new_stock']}"
        )
        manifest_path = write_manifest({
            "run_id": run_id,
            "kind": "inventory-approval",
            "status": "succeeded",
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "metadata": {
                "approval_type": "stock_command",
                "action": action,
                "changes": [result],
            },
        })
        trace.append(f"[trace] Wrote inventory approval manifest: {manifest_path}")
        return f"Approved: {result['product_name']} stock is now {result['new_stock']}.", trace

    if action_type == "add_stock":
        result = apply_owner_stock_delta(
            product_id=product_id,
            delta=float(action["delta"]),
            event_type="command",
            source_doc="typed_command",
            note=action.get("reason", ""),
        )
        trace.append(
            f"Applied stock addition: {result['product_name']} "
            f"{result['previous_stock']} → {result['new_stock']}"
        )
        manifest_path = write_manifest({
            "run_id": run_id,
            "kind": "inventory-approval",
            "status": "succeeded",
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "metadata": {
                "approval_type": "stock_command",
                "action": action,
                "changes": [result],
            },
        })
        trace.append(f"[trace] Wrote inventory approval manifest: {manifest_path}")
        return f"Approved: added {result['delta']} to {result['product_name']}.", trace

    return f"Unknown action type: {action_type}", [f"Unknown action type: {action_type}"]


def approve_receipt_rows(receipt_rows: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[str, list[str]]:
    run_id = new_run_id("inventory-approval")
    started_at = utc_now_iso()
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
    changes: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for row in rows:
        should_apply = row.get("apply", True)

        if isinstance(should_apply, str):
            should_apply = should_apply.strip().lower() not in {"false", "no", "0", ""}

        if not should_apply:
            skipped += 1
            skipped_rows.append({
                "product_raw": row.get("product_raw", ""),
                "reason": "owner_skipped",
            })
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
            skipped_rows.append({
                "product_raw": product_name,
                "reason": "unknown_product",
            })
            trace.append(f"Skipped unknown product: {product_name}")
            continue

        try:
            quantity = float(row.get("quantity", 0))
        except (TypeError, ValueError):
            skipped += 1
            skipped_rows.append({
                "product_raw": product_name,
                "reason": "invalid_quantity",
            })
            trace.append(f"Skipped {product_name}: invalid quantity")
            continue

        if quantity <= 0:
            skipped += 1
            skipped_rows.append({
                "product_raw": product_name,
                "reason": "non_positive_quantity",
                "quantity": quantity,
            })
            trace.append(f"Skipped {product_name}: quantity must be positive")
            continue

        unit_cost = 0.0

        try:
            total_price = float(row.get("total_price") or 0)
        except (TypeError, ValueError):
            total_price = 0.0

        try:
            raw_unit_price = float(row.get("unit_price") or 0)
        except (TypeError, ValueError):
            raw_unit_price = 0.0

        if total_price > 0 and quantity > 0:
            unit_cost = total_price / quantity
        else:
            unit_cost = raw_unit_price

        result = apply_owner_stock_delta(
            product_id=product_id,
            delta=quantity,
            event_type="receipt",
            source_doc=str(row.get("supplier") or "receipt"),
            unit_cost=unit_cost,
            note=f"Receipt import: {row.get('product_raw', product_name)}",
        )

        approved += 1
        changes.append(result)
        trace.append(
            f"Updated {result['product_name']}: "
            f"{result['previous_stock']} → {result['new_stock']} "
            f"(effective unit cost: {unit_cost:.2f})"
        )

    manifest_path = write_manifest({
        "run_id": run_id,
        "kind": "inventory-approval",
        "status": "succeeded",
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "metadata": {
            "approval_type": "receipt_rows",
            "input_rows": len(rows),
            "approved": approved,
            "skipped": skipped,
            "changes": changes,
            "skipped_rows": skipped_rows,
        },
    })
    trace.append(f"[trace] Wrote inventory approval manifest: {manifest_path}")

    return f"Approved {approved} rows. Skipped {skipped}.", trace
