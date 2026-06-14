"""
Kirana AI × Dukaan Saathi — gr.Server with hand-rolled HTML frontend.

UI shell ported from kirana-ai; storage and parsers come from dukaan_saathi.
"""

import json
import shutil
import tempfile
import threading
from pathlib import Path

from gradio import Server
from fastapi import File, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import kirana_db as db
import ui as ui_render
from frontend_backend import run_analysis, run_command_parse
from dukaan_saathi import config
from dukaan_saathi.agent.react_agent import get_react_agent
from dukaan_saathi.integrations.modal_receipt import _extract_receipt_result_with_modal
from dukaan_saathi.integrations.speech import transcribe_audio
from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.traceability import new_run_id, utc_now_iso, write_manifest

db.init_db()

STATIC_DIR = Path(__file__).parent / "static"


INITIAL_STATE = {
    "page":           "dashboard",
    "filters":        {"q": "", "category": "All", "status": "All"},
    "analytics_days": 30,
    "orders_filter":  "pending",
    "active_method":  "manual",
    "photo_result":   None,
    "voice_result":   None,
    "insights":       {"inventory": "", "seasonal": "", "expiry": ""},
}


def _new_state() -> dict:
    return json.loads(json.dumps(INITIAL_STATE))


def _parse_receipt_with_configured_backend(raw_text: str):
    """Use the production receipt parser backend for OCR/plain text."""
    if config.RECEIPT_BACKEND == "hf_inference":
        from dukaan_saathi.integrations.hf_inference_receipt import parse_receipt_via_hf_inference
        return parse_receipt_via_hf_inference(raw_text)

    if config.RECEIPT_BACKEND == "modal_llm":
        from dukaan_saathi.integrations.modal_receipt_llm import parse_receipt_with_modal_llm
        return parse_receipt_with_modal_llm(raw_text)

    if config.RECEIPT_BACKEND == "llamacpp":
        from dukaan_saathi.integrations.llamacpp_receipt import parse_receipt_via_llm
        return parse_receipt_via_llm(raw_text)

    return parse_receipt_text(raw_text)


def _match_receipt_rows(rows: list[dict], trace: list[str] | None = None) -> list[dict]:
    matched_rows = []
    trace = trace if trace is not None else []
    for row in rows or []:
        next_row = dict(row)
        if next_row.get("matched_product_id"):
            matched_rows.append(next_row)
            continue

        product_raw = (next_row.get("product_raw") or "").strip()
        if not product_raw:
            matched_rows.append(next_row)
            continue

        matches = db.find_by_name(product_raw)
        if matches:
            match = matches[0]
            next_row["matched_product_id"] = match["id"]
            next_row["matched_product_name"] = match["name"]
            trace.append(f"[receipt_match] Matched '{product_raw}' to {match['name']}")
        else:
            trace.append(f"[receipt_match] No catalog match for '{product_raw}'")
        matched_rows.append(next_row)
    return matched_rows


def _find_order(order_id: str) -> dict | None:
    for order in db.get_all_orders(limit=500):
        if str(order.get("id")) == str(order_id):
            return order
    return None


def _extract_receipt_direct(tmp_path: str) -> tuple[list[dict], list[str], str, str]:
    ocr_result = _extract_receipt_result_with_modal(tmp_path)
    trace = list(getattr(ocr_result, "trace", []) or [])
    raw_text = getattr(ocr_result, "raw_text", "") or ""
    model = getattr(ocr_result, "model", "unknown")
    if not trace:
        trace = [
            f"[receipt_ocr] OCR model: {model}",
            f"[receipt_ocr] Raw text length: {len(raw_text)}",
        ]

    if not raw_text.strip():
        return [], trace, raw_text, model

    rows, parse_trace, raw_text, _ = _parse_receipt_rows_from_text(raw_text)
    trace.extend(parse_trace)
    return rows, trace, raw_text, model


def _parse_receipt_rows_from_text(
    raw_text: str,
    backend_parser=_parse_receipt_with_configured_backend,
) -> tuple[list[dict], list[str], str, str]:
    trace: list[str] = []
    try:
        rows, parser_trace = backend_parser(raw_text)
        trace.extend(parser_trace)
    except Exception as exc:
        trace.append(f"[receipt_parser] Configured backend failed: {exc}")
        trace.append("[receipt_parser] Falling back to deterministic parser.")
        rows, parser_trace = parse_receipt_text(raw_text)
        trace.extend(parser_trace)
    rows = _match_receipt_rows(rows, trace)
    return rows, trace, raw_text, "text"


def _service_status() -> dict:
    import os

    return {
        "receipt_backend": config.RECEIPT_BACKEND,
        "hf_receipt_model": bool(os.getenv("HF_RECEIPT_MODEL_REPO", "").strip()),
        "modal_ocr": bool(
            (os.getenv("MODAL_RECEIPT_ENDPOINT") or os.getenv("MINICPM_RECEIPT_ENDPOINT") or "").strip()
        ),
        "modal_speech": bool(
            (os.getenv("MODAL_SPEECH_ENDPOINT") or os.getenv("SPEECH_ASR_ENDPOINT") or "").strip()
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Traceability helper
# ──────────────────────────────────────────────────────────────────────────────

def _record_approval_manifest(source_doc: str, result: dict) -> None:
    """Write a lightweight approval manifest for FastAPI-path stock writes."""
    ts = utc_now_iso()
    try:
        write_manifest({
            "run_id": new_run_id("inventory-approval"),
            "kind": "inventory-approval",
            "status": "succeeded",
            "started_at": ts,
            "ended_at": ts,
            "metadata": {
                "approval_type": source_doc,
                "product_id": result.get("product_id", ""),
                "product_name": result.get("product_name", ""),
                "previous_stock": result.get("previous_stock"),
                "new_stock": result.get("new_stock"),
                "delta": result.get("delta"),
            },
        })
    except Exception:
        pass  # manifest writes must never break the approval flow


# ──────────────────────────────────────────────────────────────────────────────
# Action handlers — each returns (state, toast)
# ──────────────────────────────────────────────────────────────────────────────

def _h_navigate(state, params):
    state["page"] = params.get("to", "dashboard")
    return state, ""


def _h_refresh(state, _params):
    return state, "success|Refreshed"


def _h_run_analysis(state, _params):
    result = run_analysis()
    state["insights"] = {
        "inventory": result.get("ai_inventory_analysis", ""),
        "seasonal":  result.get("ai_seasonal_advice", ""),
        "expiry":    result.get("ai_expiry_advice", ""),
    }
    ui_render.invalidate_insights()
    n = len(result.get("suggested_orders", []))
    state["page"] = "dashboard"
    msg = f"AI analysis complete · {n} restock order(s) generated" if n else "AI analysis complete"
    return state, f"success|{msg}"


def _h_refresh_insights(state, _params):
    ui_render.invalidate_insights()
    state["page"] = "dashboard"
    return state, "success|Refreshing AI insights…"


def _h_add_to_order(state, params):
    pid = params.get("pid")
    try:
        qty = float(params.get("qty"))
    except (TypeError, ValueError):
        return state, "danger|Could not queue this reorder"
    p = db.get_product(pid)
    if not p:
        state["page"] = "dashboard"
        return state, "danger|Product not found"
    db.insert_orders([{
        "product_id": pid,
        "product_name": p["name"],
        "qty_needed": qty,
        "unit": p["unit"],
        "reason": "Manual reorder from dashboard",
        "ai_confidence": 0.95,
    }])
    state["page"] = "orders"
    state["orders_filter"] = "pending"
    return state, f"success|Reorder queued for {p['name']}"


def _h_offer_to_route(state, params):
    pid = params.get("pid")
    p = db.get_product(pid)
    if not p:
        state["page"] = "dashboard"
        return state, "danger|Product not found"
    db.insert_orders([{
        "product_id": pid,
        "product_name": p["name"],
        "qty_needed": p["quantity"],
        "unit": p["unit"],
        "reason": "Liquidation route offer for near-expiry or overstock item",
        "ai_confidence": 0.7,
    }])
    state["page"] = "orders"
    state["orders_filter"] = "pending"
    return state, f"success|Liquidation offer logged for {p['name']}"


def _h_plan_festival_stock(state, params):
    key = (params.get("key") or "").strip()
    state["page"] = "seasonal"
    return state, f"info|Festival plan opened · {key or 'upcoming'}"


def _h_filter_inventory(state, params):
    state["filters"]["q"]        = params.get("q", "")
    state["filters"]["category"] = params.get("category", "All")
    state["filters"]["status"]   = params.get("status", "All")
    state["page"] = "inventory"
    return state, ""


def _h_update_stock(state, params):
    pid = params.get("pid")
    try:
        qty = float(params["qty"])
    except (KeyError, ValueError, TypeError):
        return state, "danger|Invalid product ID or quantity"
    mode = params.get("mode", "add")
    db.adjust_stock(pid, qty, mode=mode)
    p = db.get_product(pid)
    state["page"] = "inventory"
    return state, ("success|" + (f"{p['name']} → {p['quantity']} {p['unit']}" if p else "Updated"))


def _h_record_sale(state, params):
    pid = params.get("pid")
    try:
        qty = float(params["qty"]); price = float(params["price"])
    except (KeyError, ValueError, TypeError):
        return state, "danger|Invalid sale input"
    db.record_sale(pid, qty, price)
    p = db.get_product(pid)
    state["page"] = "inventory"
    return state, "success|" + (f"Sale recorded · {p['name']} remaining {p['quantity']}" if p else "Sale recorded")


def _h_delete_product(state, params):
    pid = params.get("pid")
    if not pid:
        return state, "danger|Invalid ID"
    p = db.get_product(pid)
    if not p:
        return state, "warn|Product not found"
    db.delete_product(pid)
    state["page"] = "inventory"
    return state, f"success|'{p['name']}' deleted"


def _h_add_product(state, params):
    name = (params.get("name") or "").strip()
    if not name:
        return state, "danger|Product name is required"
    try:
        qty = float(params.get("qty") or 0)
        min_stock = float(params.get("min_stock") or 0)
        buy = float(params.get("buy_price") or 0)
        sell = float(params.get("sell_price") or 0)
    except (ValueError, TypeError):
        return state, "danger|Quantity and prices must be numbers"
    expiry = (params.get("expiry_date") or "").strip() or None
    db.add_product(
        name, params.get("category", "Other"), qty, params.get("unit", "kg"),
        min_stock, buy, sell,
        name_local=(params.get("name_local") or "").strip(),
        expiry_date=expiry,
        supplier=(params.get("supplier") or "").strip(),
    )
    state["page"] = "inventory"
    state["filters"] = {"q": "", "category": "All", "status": "All"}
    return state, f"success|'{name}' added to inventory"


def _h_apply_receipt_row(state, params):
    qty = params.get("quantity") or 0
    try:
        qty_f = float(qty)
    except (ValueError, TypeError):
        qty_f = 0.0
    if qty_f <= 0:
        state["page"] = "add"; state["active_method"] = "photo"
        return state, "danger|Row has no usable quantity"

    pid = params.get("matched_product_id")
    if pid:
        result = db.adjust_stock(pid, qty_f, mode="add")
        _record_approval_manifest("receipt_row", result)
        p = db.get_product(pid)
        name = p["name"] if p else pid
        msg = f"Added {qty_f:g} to {name}"
    else:
        name = (params.get("product_raw") or "").strip() or "Unknown item"
        unit_price = float(params.get("unit_price") or 0)
        db.add_product(
            name, "Other", qty_f, "unit",
            min_stock=0, buy_price=unit_price, sell_price=0,
            supplier=(params.get("supplier") or "").strip(),
        )
        msg = f"Created '{name}' with {qty_f:g} units"

    state["page"] = "add"; state["active_method"] = "photo"
    return state, f"success|{msg}"


def _h_voice_command(state, params):
    text = (params.get("text") or "").strip()
    if not text:
        return state, "warn|Please type a command"
    parsed = run_command_parse(text)
    action = parsed.get("action", "unknown")
    pid = parsed.get("product_id")
    qty = parsed.get("quantity")
    needs_approval = action in {"add_stock", "set_stock"} and bool(pid) and qty is not None

    state["voice_result"] = {
        "action":         action,
        "product":        parsed.get("product", ""),
        "product_id":     pid,
        "quantity":       qty,
        "unit":           parsed.get("unit", ""),
        "confidence":     parsed.get("confidence", "low"),
        "trace":          parsed.get("trace", []),
        "applied":        None,
        "needs_approval": needs_approval,
        "suggested_name": parsed.get("suggested_name"),
        "suggested_qty":  parsed.get("suggested_qty"),
        "raw_command":    text,
    }
    state["page"] = "add"
    state["active_method"] = "voice"
    if needs_approval:
        return state, "info|Command parsed — approve before stock changes"
    return state, "warn|Could not parse a stock update"


def _h_voice_apply(state, params):
    action = params.get("action")
    pid = params.get("product_id")
    qty = params.get("quantity")
    if action not in {"add_stock", "set_stock"} or not pid or qty is None:
        state["page"] = "add"
        state["active_method"] = "voice"
        return state, "danger|No valid parsed command to apply"

    try:
        qty_f = float(qty)
    except (TypeError, ValueError):
        state["page"] = "add"
        state["active_method"] = "voice"
        return state, "danger|Invalid quantity"

    mode = "add" if action == "add_stock" else "set"
    result = db.adjust_stock(pid, qty_f, mode=mode)
    _record_approval_manifest("voice_command", result)
    p = db.get_product(pid)
    name = p["name"] if p else params.get("product", "product")
    applied = f"Added {qty_f:g} to {name}" if mode == "add" else f"Set {name} stock to {qty_f:g}"

    state["voice_result"] = {
        "action": action,
        "product": name,
        "product_id": pid,
        "quantity": qty_f,
        "unit": params.get("unit", ""),
        "confidence": params.get("confidence", "high"),
        "trace": params.get("trace", []),
        "applied": applied,
        "needs_approval": False,
    }
    state["page"] = "inventory"
    state["filters"] = {"q": "", "category": "All", "status": "All"}
    return state, f"success|{applied}"


def _h_generate_orders(state, _params):
    result = run_analysis()
    n = len(result.get("suggested_orders", []))
    state["page"] = "orders"
    state["orders_filter"] = "pending"
    return state, ("success|" + (f"{n} order(s) generated" if n else "No restock needed"))


def _h_filter_orders(state, params):
    state["orders_filter"] = params.get("status", "pending")
    state["page"] = "orders"
    return state, ""


def _h_filter_analytics(state, params):
    try:
        days = int(params.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    state["analytics_days"] = days if days in {7, 30, 90} else 30
    state["page"] = "analytics"
    return state, ""


def _h_approve_order(state, params):
    oid = params.get("oid")
    if not oid:
        return state, "danger|Invalid order ID"
    db.update_order_status(oid, "approved")
    state["page"] = "orders"
    return state, f"success|Order #{oid} approved"


def _h_mark_order_received(state, params):
    oid = params.get("oid")
    if not oid:
        return state, "danger|Invalid order ID"
    order = _find_order(str(oid))
    if not order:
        state["page"] = "orders"
        return state, "danger|Order not found"
    if order.get("status") != "approved":
        state["page"] = "orders"
        return state, "warn|Approve the order before marking it received"
    if not order.get("product_id"):
        state["page"] = "orders"
        return state, "danger|Order has no product match"

    db.adjust_stock(order["product_id"], float(order.get("qty_needed") or 0), mode="add")
    db.update_order_status(oid, "received")
    state["page"] = "orders"
    state["orders_filter"] = "received"
    return state, f"success|Order #{oid} received and stock updated"


def _h_reject_order(state, params):
    oid = params.get("oid")
    if not oid:
        return state, "danger|Invalid order ID"
    db.update_order_status(oid, "rejected")
    state["page"] = "orders"
    return state, f"warn|Order #{oid} rejected"


def _h_save_settings(state, params):
    for key in ("shop_name", "owner_name", "region", "low_stock_days_ahead", "expiry_warn_days"):
        if key in params:
            db.set_setting(key, str(params[key]))
    state["page"] = "settings"
    return state, "success|Settings saved"


HANDLERS = {
    "navigate":            _h_navigate,
    "refresh":             _h_refresh,
    "run_analysis":        _h_run_analysis,
    "refresh_insights":    _h_refresh_insights,
    "add_to_order":        _h_add_to_order,
    "offer_to_route":      _h_offer_to_route,
    "plan_festival_stock": _h_plan_festival_stock,
    "filter_inventory": _h_filter_inventory,
    "update_stock":     _h_update_stock,
    "record_sale":      _h_record_sale,
    "delete_product":   _h_delete_product,
    "add_product":      _h_add_product,
    "apply_receipt_row": _h_apply_receipt_row,
    "voice_command":    _h_voice_command,
    "voice_apply":      _h_voice_apply,
    "generate_orders":  _h_generate_orders,
    "filter_orders":    _h_filter_orders,
    "filter_analytics": _h_filter_analytics,
    "approve_order":    _h_approve_order,
    "mark_order_received": _h_mark_order_received,
    "reject_order":     _h_reject_order,
    "save_settings":    _h_save_settings,
}


# ──────────────────────────────────────────────────────────────────────────────
# gr.Server engine
# ──────────────────────────────────────────────────────────────────────────────
server = Server(title="Kirana AI", docs_url=None, redoc_url=None)
server.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


INDEX_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kirana AI</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
  <div class="page-host">{initial_html}</div>
  <input type="file" id="kirana-photo-input" accept="image/*" style="position:absolute;left:-9999px;top:-9999px;">
  <script>window.__KIRANA_STATE__ = {initial_state_json};</script>
  <script src="/static/app.js" defer></script>
</body>
</html>"""


@server.get("/", response_class=HTMLResponse)
def index() -> str:
    state = _new_state()
    html = ui_render.render("dashboard", state)
    return INDEX_HTML.format(
        initial_html=html,
        initial_state_json=json.dumps(state),
    )


@server.post("/api/dispatch")
def api_dispatch(payload: dict) -> dict:
    state = payload.get("state") or _new_state()
    action = payload.get("action", "")
    params = payload.get("params") or {}

    handler = HANDLERS.get(action)
    if not handler:
        html = ui_render.render(state.get("page", "dashboard"), state,
                                toast=f"warn|Unknown action: {action}")
        return {"html": html, "state": state}

    state, toast = handler(state, params)
    html = ui_render.render(state["page"], state, toast=toast)
    return {"html": html, "state": state}


@server.post("/api/photo")
async def api_photo(state: str = Form(...), image: UploadFile = File(...)) -> dict:
    state_dict = json.loads(state) if state else _new_state()
    suffix = Path(image.filename or "").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(image.file, tmp)
        tmp_path = tmp.name

    try:
        react_result = get_react_agent().extract_receipt_image(tmp_path)
        trace = list(react_result.trace)
        rows = _match_receipt_rows(react_result.receipt_rows or [], trace)
        raw_text = react_result.raw_text or ""
        ocr_model = "react_agent"
    except Exception as exc:
        rows, trace, raw_text, ocr_model = _extract_receipt_direct(tmp_path)
        trace.insert(0, f"[react_agent] Unavailable; used direct receipt path: {exc}")

    if rows:
        result = {
            "rows": rows,
            "trace": trace,
            "raw_text": raw_text,
            "ocr_model": ocr_model,
        }
        toast = f"info|Receipt parsed · {len(rows)} row(s)"
    else:
        result = {
            "error": trace[-1] if trace else "No rows extracted",
            "trace": trace,
            "raw_text": raw_text,
            "ocr_model": ocr_model,
        }
        toast = f"warn|{result['error']}"

    state_dict["photo_result"] = result
    state_dict["page"] = "add"
    state_dict["active_method"] = "photo"
    html = ui_render.render(state_dict["page"], state_dict, toast=toast)
    return {"html": html, "state": state_dict}


@server.post("/api/speech")
async def api_speech(state: str = Form(...), audio: UploadFile = File(...)) -> dict:
    state_dict = json.loads(state) if state else _new_state()
    suffix = Path(audio.filename or "").suffix or ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name

    transcript, trace = transcribe_audio(tmp_path)

    state_dict["voice_result"] = {
        "transcript": transcript,
        "trace": trace,
    }
    state_dict["page"] = "add"
    state_dict["active_method"] = "voice"

    toast = "success|Speech transcribed" if transcript else f"warn|{trace[-1] if trace else 'Speech transcription failed'}"
    html = ui_render.render(state_dict["page"], state_dict, toast=toast)
    return {"html": html, "state": state_dict}


@server.get("/api/status")
def api_status() -> dict:
    return _service_status()


@server.get("/api/warm")
def api_warm() -> dict:
    import os
    import requests

    endpoints = [
        os.getenv("MODAL_RECEIPT_ENDPOINT", "").strip(),
        os.getenv("MINICPM_RECEIPT_ENDPOINT", "").strip(),
        os.getenv("MODAL_RECEIPT_LLM_ENDPOINT", "").strip(),
        os.getenv("MODAL_SPEECH_ENDPOINT", "").strip(),
        os.getenv("SPEECH_ASR_ENDPOINT", "").strip(),
    ]
    warmed = 0

    def _ping(url: str) -> None:
        try:
            requests.head(url, timeout=5)
        except Exception:
            pass

    for endpoint in sorted({e for e in endpoints if e}):
        warmed += 1
        threading.Thread(target=_ping, args=(endpoint,), daemon=True).start()

    return {"ok": True, "warmed": warmed}


if __name__ == "__main__":
    server.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
    )
