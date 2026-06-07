"""
po_check node — surfaces the PO draft and saves it as pending in SQLite.
Actual approval/rejection happens via Gradio UI buttons (approve_po / reject_po).
This node just persists the draft so the UI can display it.
"""

from state import AgentState
from db.database import save_pending_po
from models.translate import en_to_te


def po_check_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    po_draft = state.get("po_draft")

    if not po_draft:
        trace.append("po_check: no PO draft, nothing to do")
        return {**state, "trace": trace}

    # Translate each item's reason into Telugu for the UI
    for po in po_draft.get("purchase_orders", []):
        for item in po.get("items", []):
            reason_en = item.get("reason_en", "")
            item["reason_te"] = en_to_te(reason_en) if reason_en else ""

    # Persist as pending in SQLite (owner approves via UI)
    po_ids = []
    for po in po_draft.get("purchase_orders", []):
        po_id = save_pending_po(po)
        po_ids.append(po_id)
        trace.append(
            f"po_check: saved PO {po_id} for {po['supplier_name']} "
            f"₹{po['po_total']:.0f} — awaiting owner approval"
        )

    response = (
        f"{len(po_ids)} purchase order(s) ready for your approval. "
        f"Check the approval panel to confirm or edit."
    )

    return {**state, "response": response, "trace": trace}
