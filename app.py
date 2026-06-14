"""
Kirana AI × Dukaan Saathi — gr.Server with hand-rolled HTML frontend.

UI shell ported from kirana-ai; storage and parsers come from dukaan_saathi.
"""

import json
import shutil
import tempfile
from pathlib import Path

from gradio import Server
from fastapi import File, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import kirana_db as db
import ui as ui_render
from frontend_backend import run_analysis, run_command_parse
from dukaan_saathi import config
from dukaan_saathi.integrations.modal_receipt import _extract_receipt_result_with_modal
from dukaan_saathi.integrations.speech import transcribe_audio
from dukaan_saathi.parsers.receipt_text import parse_receipt_text

db.init_db()

STATIC_DIR = Path(__file__).parent / "static"


INITIAL_STATE = {
    "page":           "dashboard",
    "filters":        {"q": "", "category": "All", "status": "All"},
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
    state["page"] = "dashboard"
    name = p["name"] if p else f"product {pid}"
    unit = p["unit"] if p else ""
    return state, f"success|Queued {qty:g} {unit} of {name} for the next order"


def _h_offer_to_route(state, params):
    pid = params.get("pid")
    p = db.get_product(pid)
    state["page"] = "dashboard"
    name = p["name"] if p else f"product {pid}"
    return state, f"success|Liquidation offer drafted for {name}"


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
        db.adjust_stock(pid, qty_f, mode="add")
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
    applied = None
    action = parsed.get("action", "unknown")
    pid = parsed.get("product_id")
    qty = parsed.get("quantity")

    if action == "add_stock" and pid and qty:
        db.adjust_stock(pid, float(qty), mode="add")
        p = db.get_product(pid)
        name = p["name"] if p else parsed.get("product", "product")
        applied = f"Added {qty} to {name}"
    elif action == "set_stock" and pid and qty is not None:
        db.adjust_stock(pid, float(qty), mode="set")
        p = db.get_product(pid)
        name = p["name"] if p else parsed.get("product", "product")
        applied = f"Set {name} stock to {qty}"

    state["voice_result"] = {
        "action":     action,
        "product":    parsed.get("product", ""),
        "quantity":   qty,
        "unit":       parsed.get("unit", ""),
        "confidence": parsed.get("confidence", "low"),
        "applied":    applied,
    }
    state["page"] = "add"
    state["active_method"] = "voice"
    return state, ("success|" + applied) if applied else "info|Command parsed — review above"


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


def _h_approve_order(state, params):
    oid = params.get("oid")
    if not oid:
        return state, "danger|Invalid order ID"
    db.update_order_status(oid, "approved")
    state["page"] = "orders"
    return state, f"success|Order #{oid} approved"


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
    "generate_orders":  _h_generate_orders,
    "filter_orders":    _h_filter_orders,
    "approve_order":    _h_approve_order,
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

    ocr_result = _extract_receipt_result_with_modal(tmp_path)
    trace = list(getattr(ocr_result, "trace", []) or [])
    if not trace:
        trace = [
            f"[receipt_ocr] OCR model: {getattr(ocr_result, 'model', 'unknown')}",
            f"[receipt_ocr] Raw text length: {len(getattr(ocr_result, 'raw_text', '') or '')}",
        ]

    if (getattr(ocr_result, 'raw_text', '') or '').strip():
        try:
            rows, parser_trace = _parse_receipt_with_configured_backend(getattr(ocr_result, 'raw_text', '') or '')
            trace.extend(parser_trace)
        except Exception as exc:
            trace.append(f"[receipt_parser] Configured backend failed: {exc}")
            trace.append("[receipt_parser] Falling back to deterministic parser.")
            rows, parser_trace = parse_receipt_text(getattr(ocr_result, 'raw_text', '') or '')
            trace.extend(parser_trace)
    else:
        rows = []

    if rows:
        result = {
            "rows": rows,
            "trace": trace,
            "raw_text": getattr(ocr_result, "raw_text", "") or "",
            "ocr_model": getattr(ocr_result, "model", "unknown"),
        }
        toast = f"info|Receipt parsed · {len(rows)} row(s)"
    else:
        result = {
            "error": trace[-1] if trace else "No rows extracted",
            "trace": trace,
            "raw_text": getattr(ocr_result, "raw_text", "") or "",
            "ocr_model": getattr(ocr_result, "model", "unknown"),
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


if __name__ == "__main__":
    server.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
    )
