"""
LangGraph node functions for Kirana AI.

Each node receives KiranaState and returns a partial dict.
completed_nodes / errors use operator.add reducers — each node
just returns ["node_name"], the reducer accumulates them.

SLM_INTEGRATION_POINT markers show exactly where to swap in llama.cpp calls.
"""

from __future__ import annotations
import json
import re
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import kirana_db as db
from seasonal_calendar import (
    build_seasonal_summary,
    get_upcoming_festivals,
    get_seasonal_context,
    get_demand_multiplier,
)
from agent.state import KiranaState


# ── SLM stub ──────────────────────────────────────────────────────────────────
# SLM_INTEGRATION_POINT
# Replace _stub_slm with a real call once the model is ready:
#
#   from llama_cpp import Llama
#   _llm = Llama(
#       model_path="models/qwen2.5-7b-instruct-q4_k_m.gguf",
#       n_ctx=4096, n_threads=8, verbose=False,
#   )
#   def _call_slm(system: str, user: str, max_tokens: int = 512) -> str:
#       resp = _llm.create_chat_completion(
#           messages=[{"role":"system","content":system},
#                     {"role":"user","content":user}],
#           max_tokens=max_tokens, temperature=0.3,
#       )
#       return resp["choices"][0]["message"]["content"].strip()

def _stub_slm(task: str, context_preview: str = "") -> str:
    preview = context_preview[:200] + "…" if len(context_preview) > 200 else context_preview
    return (
        f"**[SLM stub — Qwen2.5-7B not yet loaded]**\n\n"
        f"Task: {task}\n\n"
        f"Context preview:\n{preview}\n\n"
        f"→ See `agent/nodes.py` → `SLM_INTEGRATION_POINT` to wire in the model."
    )


# ── Node: load inventory ──────────────────────────────────────────────────────

def node_load_inventory(state: KiranaState) -> dict:
    return {
        "all_products":    db.get_all_products(),
        "low_stock_items": db.get_low_stock(),
        "expiring_items":  db.get_expiring_soon(7),
        "expired_items":   db.get_expired(),
        "top_sellers":     db.get_top_sellers(10),
        "summary":         db.get_summary(),
        "completed_nodes": ["load_inventory"],
        "errors":          [],
    }


# ── Node: seasonal context ────────────────────────────────────────────────────

def node_seasonal_context(state: KiranaState) -> dict:
    return {
        "seasonal_summary":   build_seasonal_summary(),
        "upcoming_festivals": get_upcoming_festivals(30),
        "completed_nodes":    ["seasonal_context"],
        "errors":             [],
    }


# ── Node: seasonal advice — SLM_INTEGRATION_POINT ────────────────────────────

def node_seasonal_advice(state: KiranaState) -> dict:
    festivals = state.get("upcoming_festivals", [])
    inventory = state.get("all_products", [])
    inv_names = {p["name"] for p in inventory}
    ctx       = get_seasonal_context()

    lines = [f"**Seasonal & Festival Stocking Advice**\n",
             f"🗓️ **Season:** {ctx['season']} — {ctx['note']}\n"]

    if festivals:
        for fest in festivals[:4]:
            relevant = [i for i in fest["demand_items"] if i in inv_names]
            missing  = [i for i in fest["demand_items"] if i not in inv_names]
            lines.append(f"### {fest['name']} ({fest['name_te']})")
            lines.append(f"Expected demand spike: **{fest['demand_multiplier']}×** · "
                         f"Start stocking **{fest['prep_days']} days** before")
            if relevant:
                lines.append(f"✅ Already stocked: {', '.join(relevant[:5])}")
            if missing:
                lines.append(f"❌ Consider adding: {', '.join(missing[:5])}")
            lines.append(f"💡 {fest['tips']}\n")
    else:
        lines.append("No major festivals in the next 30 days. Maintain normal levels.")

    advice = "\n".join(lines)

    # SLM_INTEGRATION_POINT — replace above rule-based logic with:
    # advice = _call_slm(
    #     system="You are a kirana store stocking advisor for South India.",
    #     user=f"Advise the shopkeeper based on this seasonal context:\n"
    #          f"{state.get('seasonal_summary', '')}"
    # )

    return {
        "ai_seasonal_advice": advice,
        "completed_nodes":    ["seasonal_advice"],
        "errors":             [],
    }


# ── Node: inventory analysis — SLM_INTEGRATION_POINT ─────────────────────────

def node_analyse_inventory(state: KiranaState) -> dict:
    low   = state.get("low_stock_items", [])
    expir = state.get("expiring_items",  [])
    summ  = state.get("summary", {})

    lines = []
    if summ:
        lines.append(
            f"**Stock overview:** {summ.get('total',0)} products · "
            f"₹{summ.get('total_value',0):,.0f} inventory value"
        )

    if low:
        lines.append(f"\n**⚠️ Low stock — {len(low)} item(s):**")
        for p in low[:8]:
            pct = (p["quantity"] / max(p["min_stock"], 0.01)) * 100
            lines.append(
                f"- **{p['name']}** ({p['name_local']}) — "
                f"{p['quantity']} {p['unit']} left ({pct:.0f}% of minimum)"
            )

    if expir:
        lines.append(f"\n**🕐 Expiring within 7 days — {len(expir)} item(s):**")
        for p in expir[:6]:
            lines.append(
                f"- **{p['name']}** — {p['quantity']} {p['unit']} "
                f"(expires {p['expiry_date']})"
            )

    if not low and not expir:
        lines.append("✅ Stock levels look healthy. No urgent restock needed.")

    analysis = "\n".join(lines)

    # SLM_INTEGRATION_POINT — replace above with:
    # context = json.dumps({"low": low[:10], "expiring": expir[:6], "summary": summ},
    #                      ensure_ascii=False)
    # analysis = _call_slm(
    #     system="You are an AI inventory assistant for an Indian kirana store. "
    #            "Be concise and actionable.",
    #     user=f"Analyse this inventory and give clear advice:\n{context}"
    # )

    return {
        "ai_inventory_analysis": analysis,
        "completed_nodes":       ["analyse_inventory"],
        "errors":                [],
    }


# ── Node: expiry liquidation advice — SLM_INTEGRATION_POINT ──────────────────

def node_expiry_advice(state: KiranaState) -> dict:
    expir   = state.get("expiring_items", [])
    expired = state.get("expired_items",  [])

    lines = ["**Expiry Management**\n"]

    if expired:
        lines.append(f"🚨 **{len(expired)} product(s) already expired — remove immediately:**")
        for p in expired:
            lines.append(f"  - {p['name']} (expired {p['expiry_date']})")
        lines.append("")

    if expir:
        lines.append(f"⚡ **{len(expir)} product(s) expiring within 7 days:**")
        for p in expir:
            days_left = (
                datetime.date.fromisoformat(p["expiry_date"]) - datetime.date.today()
            ).days
            lines.append(f"\n**{p['name']}** ({p['name_local']}) — {p['quantity']} {p['unit']}, "
                         f"expires in {days_left} day(s)")
            lines.append("  - 💰 Run 10–15% discount to move stock fast")
            lines.append("  - 📍 Move to eye-level shelf near entrance")
            lines.append("  - 🎁 Bundle with a fast-moving complementary item")
    else:
        lines.append("✅ No products expiring in the next 7 days.")

    advice = "\n".join(lines)

    # SLM_INTEGRATION_POINT — replace above with:
    # context = json.dumps({"expiring": expir, "expired": expired}, ensure_ascii=False)
    # advice = _call_slm(
    #     system="You are a retail advisor for an Indian kirana store.",
    #     user=f"Suggest liquidation strategies for these expiring items:\n{context}"
    # )

    return {
        "ai_expiry_advice": advice,
        "completed_nodes":  ["expiry_advice"],
        "errors":           [],
    }


# ── Node: generate restock orders — SLM_INTEGRATION_POINT ────────────────────

def node_generate_orders(state: KiranaState) -> dict:
    low       = state.get("low_stock_items", [])
    festivals = state.get("upcoming_festivals", [])
    suggested: list[dict] = []

    for p in low:
        velocity  = db.get_daily_velocity(p["id"], days=14)
        fest_mult = get_demand_multiplier(p["name"])
        days_cover = 14 * fest_mult
        qty_needed = round(max(p["min_stock"] * 2, velocity * days_cover), 1)

        reason = (f"Stock at {p['quantity']}{p['unit']} (min {p['min_stock']}). "
                  f"Velocity {velocity:.2f}/day.")
        if fest_mult > 1.0:
            reason += f" Festival demand ×{fest_mult} expected."

        suggested.append({
            "product_id":    p["id"],
            "product_name":  p["name"],
            "qty_needed":    qty_needed,
            "unit":          p["unit"],
            "reason":        reason,
            "ai_confidence": min(0.95, 0.7 + velocity * 0.05),
        })

    # SLM_INTEGRATION_POINT — replace heuristic with:
    # context = json.dumps({"low_stock": low, "festivals": festivals}, ensure_ascii=False)
    # raw = _call_slm(
    #     system="You are a procurement AI for an Indian kirana store. "
    #            "Return ONLY a JSON array.",
    #     user=f"Generate restock orders for low-stock items:\n{context}\n"
    #          "Format: [{product_id,product_name,qty_needed,unit,reason,ai_confidence}]"
    # )
    # suggested = json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group())

    return {
        "suggested_orders":     suggested,
        "needs_human_approval": len(suggested) > 0,
        "completed_nodes":      ["generate_orders"],
        "errors":               [],
    }


# ── Node: parse voice / text command — SLM_INTEGRATION_POINT ─────────────────

def node_parse_command(state: KiranaState) -> dict:
    text = state.get("user_input", "")
    if not text.strip():
        return {"ai_parsed_command": {}, "completed_nodes": ["parse_command"], "errors": []}

    text_lower = text.lower()

    add_kws  = ["add", "stock", "arrived", "received", "got", "brought",
                "purchase", "వచ్చింది", "స్టాక్", "కొన్నాం"]
    sell_kws = ["sold", "sale", "customer", "అమ్మాం", "అమ్మడం"]
    qry_kws  = ["how much", "check", "quantity", "left", "remaining",
                "ఎంత", "చూడు", "ఉంది"]

    action = "unknown"
    if any(k in text_lower for k in add_kws):
        action = "add_stock"
    elif any(k in text_lower for k in sell_kws):
        action = "record_sale"
    elif any(k in text_lower for k in qry_kws):
        action = "query_stock"

    qty_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|g|litre|ltr|l|piece|packet|dozen|box|bottle)?",
        text_lower,
    )
    qty, unit = None, "kg"
    if qty_match:
        qty = float(qty_match.group(1))
        raw_unit = qty_match.group(2) or "kg"
        unit = {"ltr": "litre", "l": "litre"}.get(raw_unit, raw_unit)

    product = ""
    for p in db.get_all_products():
        if p["name"].lower() in text_lower or (p["name_local"] and p["name_local"] in text):
            product = p["name"]
            break

    parsed = {
        "action":     action,
        "product":    product,
        "quantity":   qty,
        "unit":       unit,
        "raw_text":   text,
        "confidence": "medium" if (product and qty) else "low",
    }

    # SLM_INTEGRATION_POINT — replace regex heuristics with:
    # raw = _call_slm(
    #     system="You are a voice command parser for a kirana store assistant. "
    #            "Parse the instruction and return ONLY JSON.",
    #     user=f'Instruction: "{text}"\n'
    #          'Return: {{"action":"add_stock"|"record_sale"|"query_stock"|"unknown",'
    #          '"product":"name or empty","quantity":number_or_null,'
    #          '"unit":"kg|litre|piece|packet","confidence":"high"|"medium"|"low"}}'
    # )
    # parsed = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
    # parsed["raw_text"] = text

    return {
        "ai_parsed_command": parsed,
        "completed_nodes":   ["parse_command"],
        "errors":            [],
    }


# ── Node: human approval — persists orders to DB ─────────────────────────────

def node_human_approval(state: KiranaState) -> dict:
    for o in state.get("suggested_orders", []):
        db.create_order(
            product_name=o["product_name"],
            qty_needed=o["qty_needed"],
            unit=o["unit"],
            reason=o["reason"],
            product_id=o.get("product_id"),
            ai_confidence=o.get("ai_confidence", 0.0),
        )
    return {
        "completed_nodes": ["human_approval"],
        "errors":          [],
    }
