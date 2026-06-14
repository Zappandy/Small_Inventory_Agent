from __future__ import annotations
import os
from pathlib import Path

import pandas as pd
import gradio as gr

from dukaan_saathi.integrations.modal_receipt import extract_receipt_with_modal
from dukaan_saathi.integrations.speech import transcribe_audio
from dukaan_saathi import config
from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.parsers.receipt_correction import apply_receipt_correction_command
from dukaan_saathi.parsers.stock_command import parse_stock_command
from dukaan_saathi.services.inventory import approve_command_action, approve_receipt_rows
from dukaan_saathi.services.reorder import draft_reorder
from dukaan_saathi.storage import get_inventory, init_db


INVENTORY_COLUMNS = [
    "product_id",
    "product_name",
    "supplier",
    "current_stock",
    "reorder_threshold",
    "target_stock",
    "unit_type",
    "units_per_case",
    "last_unit_cost",
    "status",
]

RECEIPT_COLUMNS = [
    "apply",
    "document_type",
    "supplier",
    "product_raw",
    "matched_product_id",
    "matched_product_name",
    "quantity_raw",
    "quantity",
    "unit_price",
    "total_price",
    "confidence",
    "warning",
]

REORDER_COLUMNS = [
    "supplier",
    "product_name",
    "current_stock",
    "threshold",
    "target_stock",
    "suggested_order_qty",
    "unit_cost",
    "estimated_total",
    "reason",
]

SAMPLE_RECEIPT_DIR = Path("samples/receipt_text")


SAMPLE_RECEIPT = """Mahalakshmi Marketing
Bingo 4 X 870 = 3480
Lays Classic 2 X 480 = 960
Parle-G 10 X 50 = 500
"""


CUSTOM_CSS = """
:root {
    --kirana-bg: #06251d;
    --kirana-rail: #031912;
    --kirana-panel: #0d3b2f;
    --kirana-panel-2: #123f34;
    --kirana-line: rgba(220, 246, 229, 0.12);
    --kirana-muted: #c4d8cf;
    --kirana-text: #f4fbf6;
    --kirana-gold: #f4a62a;
    --kirana-green: #65c98f;
    --kirana-red: #ff4f61;
}

body,
.gradio-container {
    background: var(--kirana-bg) !important;
    color: var(--kirana-text) !important;
}

.gradio-container {
    max-width: none !important;
    min-height: 100vh !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}

footer { display: none !important; }

.app-shell {
    gap: 0 !important;
    min-height: 100vh;
}

.sidebar {
    min-width: 260px !important;
    max-width: 260px !important;
    background: var(--kirana-rail);
    border-right: 1px solid var(--kirana-line);
    padding: 20px 16px;
}

.main-surface {
    padding: 28px 38px 48px !important;
}

.brand-lockup {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 34px;
}

.brand-icon {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background: var(--kirana-gold);
    color: #04140f;
    font-weight: 900;
}

.brand-title {
    font-size: 18px;
    line-height: 1.1;
    font-weight: 800;
    color: var(--kirana-text);
}

.sidebar-label,
.metric-subtitle,
.panel-subtitle {
    color: var(--kirana-muted);
}

.brand-subtitle {
    color: #f7c66f;
}

.sidebar-status {
    color: var(--kirana-text);
    font-weight: 750;
}

.sidebar-footer div {
    color: var(--kirana-text);
}

.brand-subtitle,
.sidebar-label {
    font-size: 11px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}

.sidebar-label {
    margin: 22px 0 12px;
}

.nav-item,
.sidebar-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border-radius: 9px;
    padding: 12px 12px;
    color: var(--kirana-text);
}

.nav-button button {
    width: 100% !important;
    justify-content: flex-start !important;
    border: 0 !important;
    border-radius: 9px !important;
    background: transparent !important;
    color: var(--kirana-text) !important;
    box-shadow: none !important;
    padding: 12px 12px !important;
    font-weight: 750 !important;
    text-align: left !important;
}

.nav-button button:hover {
    background: rgba(244, 166, 42, 0.12) !important;
}

.nav-button-primary button {
    background: rgba(244, 166, 42, 0.14) !important;
}

.nav-item.active {
    background: rgba(244, 166, 42, 0.14);
}

.nav-count {
    min-width: 28px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--kirana-gold);
    color: #111;
    font-size: 12px;
    font-weight: 800;
    text-align: center;
}

.sidebar-footer {
    margin-top: 220px;
    display: block;
    border-top: 1px solid var(--kirana-line);
    border-radius: 0;
}

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--kirana-gold);
    margin-right: 8px;
}

.hero-bar {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 22px;
}

.hero-title {
    margin: 0;
    font-size: 34px;
    line-height: 1.05;
    font-weight: 850;
    color: var(--kirana-text);
}

.hero-copy {
    margin: 8px 0 0;
    max-width: 760px;
    color: var(--kirana-muted);
    font-size: 15px;
}

.backend-pill {
    white-space: nowrap;
    border: 1px solid var(--kirana-line);
    border-radius: 999px;
    padding: 8px 12px;
    color: var(--kirana-gold);
    background: rgba(244, 166, 42, 0.08);
    font-size: 13px;
    font-weight: 700;
}

.metric-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin: 14px 0 24px;
}

.metric-card {
    border: 1px solid var(--kirana-line);
    background: linear-gradient(180deg, rgba(22, 76, 63, 0.9), rgba(13, 59, 47, 0.85));
    border-radius: 8px;
    padding: 18px 20px;
}

.metric-value {
    font-size: 34px;
    line-height: 1;
    font-weight: 850;
}

.metric-value.warn { color: var(--kirana-gold); }
.metric-value.danger { color: var(--kirana-red); }
.metric-subtitle { margin-top: 8px; font-size: 13px; }

.gradio-tabs {
    border: 1px solid var(--kirana-line) !important;
    background: rgba(6, 37, 29, 0.35) !important;
    border-radius: 8px !important;
    padding: 14px !important;
}

.tab-nav,
.tabs {
    background: transparent !important;
}

.tab-nav button {
    border-radius: 8px !important;
    color: var(--kirana-muted) !important;
    font-weight: 750 !important;
}

.tab-nav button.selected {
    background: rgba(244, 166, 42, 0.16) !important;
    color: var(--kirana-text) !important;
}

.block,
.form,
.panel,
.gr-box,
.gr-panel {
    border-color: var(--kirana-line) !important;
    background: var(--kirana-panel) !important;
    border-radius: 8px !important;
}

.panel-heading h2,
.panel-heading h3 {
    margin: 0 !important;
    font-size: 22px !important;
    line-height: 1.2 !important;
    color: var(--kirana-text) !important;
}

.prose h1,
.prose h2,
.prose h3,
.markdown h1,
.markdown h2,
.markdown h3 {
    color: var(--kirana-text) !important;
}

.panel-heading {
    margin: 0 0 14px !important;
}

label,
.prose,
.markdown,
.wrap,
.output-class,
.input-class {
    color: var(--kirana-text) !important;
}

textarea,
input,
.dataframe,
.table-wrap {
    background: #0a2f25 !important;
    color: var(--kirana-text) !important;
    border-color: var(--kirana-line) !important;
}

.inventory-table,
.receipt-table,
.reorder-table,
.inventory-table *,
.receipt-table *,
.reorder-table * {
    border-color: rgba(220, 246, 229, 0.18) !important;
}

.inventory-table *,
.receipt-table *,
.reorder-table * {
    color: var(--kirana-text) !important;
    -webkit-text-fill-color: var(--kirana-text) !important;
}

.inventory-table .table-wrap,
.receipt-table .table-wrap,
.reorder-table .table-wrap,
.inventory-table .dataframe,
.receipt-table .dataframe,
.reorder-table .dataframe,
.inventory-table table,
.receipt-table table,
.reorder-table table,
.inventory-table thead,
.receipt-table thead,
.reorder-table thead,
.inventory-table tbody,
.receipt-table tbody,
.reorder-table tbody {
    background: #08291f !important;
    color: var(--kirana-text) !important;
}

.inventory-table th,
.receipt-table th,
.reorder-table th,
.inventory-table [role="columnheader"],
.receipt-table [role="columnheader"],
.reorder-table [role="columnheader"] {
    background: #123f34 !important;
    color: var(--kirana-text) !important;
    -webkit-text-fill-color: var(--kirana-text) !important;
    font-weight: 800 !important;
}

.inventory-table td,
.receipt-table td,
.reorder-table td,
.inventory-table [role="gridcell"],
.receipt-table [role="gridcell"],
.reorder-table [role="gridcell"],
.inventory-table .cell-wrap,
.receipt-table .cell-wrap,
.reorder-table .cell-wrap,
.inventory-table .cell,
.receipt-table .cell,
.reorder-table .cell,
.inventory-table span,
.receipt-table span,
.reorder-table span,
.inventory-table input,
.receipt-table input,
.reorder-table input,
.inventory-table textarea,
.receipt-table textarea,
.reorder-table textarea {
    background: #0a2f25 !important;
    color: var(--kirana-text) !important;
    -webkit-text-fill-color: var(--kirana-text) !important;
}

.inventory-table td:hover,
.receipt-table td:hover,
.reorder-table td:hover,
.inventory-table [role="gridcell"]:hover,
.receipt-table [role="gridcell"]:hover,
.reorder-table [role="gridcell"]:hover {
    background: #123f34 !important;
}

.inventory-table .selected,
.receipt-table .selected,
.reorder-table .selected,
.inventory-table .current,
.receipt-table .current,
.reorder-table .current {
    background: rgba(244, 166, 42, 0.18) !important;
    color: var(--kirana-text) !important;
    -webkit-text-fill-color: var(--kirana-text) !important;
}

.speech-control,
.speech-control *,
.speech-control audio,
.speech-control button {
    background-color: #0a2f25 !important;
    color: var(--kirana-text) !important;
    border-color: var(--kirana-line) !important;
}

.trace-box textarea {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
    font-size: 12px !important;
    background: #071f18 !important;
    color: #cae9dd !important;
}

button.primary,
.primary {
    background: var(--kirana-gold) !important;
    border-color: var(--kirana-gold) !important;
    color: #081a14 !important;
    font-weight: 800 !important;
}

button.secondary,
button:not(.selected) {
    border-color: var(--kirana-line) !important;
}

.info-strip {
    border: 1px solid var(--kirana-line);
    border-left: 4px solid var(--kirana-gold);
    background: rgba(244, 166, 42, 0.08);
    border-radius: 8px;
    padding: 12px 14px;
    color: var(--kirana-text);
    margin: 8px 0 16px;
}

.route-note {
    border: 1px solid var(--kirana-line);
    background: rgba(220, 246, 229, 0.05);
    border-radius: 8px;
    padding: 16px;
    margin-top: 12px;
}

.capability-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin: 0 0 18px;
}

.capability-card {
    border: 1px solid var(--kirana-line);
    background: rgba(220, 246, 229, 0.05);
    border-radius: 8px;
    padding: 16px;
}

.capability-card strong {
    display: block;
    margin-bottom: 8px;
    color: var(--kirana-text) !important;
    font-weight: 850;
}

.capability-card span {
    color: var(--kirana-muted);
    font-size: 13px;
}

.info-strip strong,
.route-note strong {
    color: var(--kirana-text) !important;
}

.howto-list {
    margin: 0;
    padding-left: 22px;
}

.howto-list li {
    margin: 10px 0;
    color: var(--kirana-text);
}

.howto-section {
    border: 1px solid var(--kirana-line);
    background: rgba(220, 246, 229, 0.05);
    border-radius: 8px;
    padding: 16px;
    margin: 14px 0;
}

.howto-section h3 {
    margin: 0 0 10px !important;
    color: var(--kirana-text) !important;
    font-size: 18px !important;
    line-height: 1.25 !important;
}

.howto-section p,
.howto-section li,
.howto-section strong,
.howto-section span,
.howto-section ol,
.howto-section ul {
    color: var(--kirana-text) !important;
    font-family: inherit !important;
}

.howto-section li::marker {
    color: #f7c66f !important;
}

.howto-section .note {
    color: #f7c66f !important;
    font-weight: 750;
}

.prose code,
.markdown code,
code {
    background: rgba(244, 166, 42, 0.16) !important;
    border: 1px solid rgba(244, 166, 42, 0.28) !important;
    color: #ffe0a3 !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
    border-radius: 5px !important;
    padding: 1px 5px !important;
}

@media (max-width: 900px) {
    .app-shell {
        display: block !important;
    }

    .sidebar {
        min-width: 100% !important;
        max-width: 100% !important;
    }

    .sidebar-footer {
        margin-top: 18px;
    }

    .main-surface {
        padding: 22px 16px 36px !important;
    }

    .hero-bar {
        display: block;
    }

    .backend-pill {
        display: inline-block;
        margin-top: 14px;
    }

    .metric-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .capability-grid {
        grid-template-columns: 1fr;
    }
}
"""

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.orange,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)


def list_sample_receipts() -> list[str]:
    if not SAMPLE_RECEIPT_DIR.exists():
        return []
    return sorted(path.name for path in SAMPLE_RECEIPT_DIR.glob("*.txt"))


def load_sample_receipt(filename: str) -> str:
    if not filename:
        return SAMPLE_RECEIPT

    path = SAMPLE_RECEIPT_DIR / filename
    if not path.exists():
        return SAMPLE_RECEIPT

    return path.read_text()

def bi(en: str) -> str:
    return en


def inventory_df() -> pd.DataFrame:
    return pd.DataFrame(get_inventory(), columns=INVENTORY_COLUMNS)


def empty_receipt_df() -> pd.DataFrame:
    return pd.DataFrame(columns=RECEIPT_COLUMNS)


def empty_reorder_df() -> pd.DataFrame:
    return pd.DataFrame(columns=REORDER_COLUMNS)


def dashboard_stats() -> dict[str, int | float]:
    inventory = get_inventory()
    low_stock = [
        row
        for row in inventory
        if int(row["current_stock"]) <= int(row["reorder_threshold"])
    ]
    estimated_reorder_value = sum(
        max(int(row["target_stock"]) - int(row["current_stock"]), 0)
        * float(row.get("last_unit_cost") or 0)
        for row in low_stock
    )
    return {
        "total_items": len(inventory),
        "low_stock_count": len(low_stock),
        "out_count": sum(1 for row in inventory if row.get("status") == "OUT"),
        "estimated_reorder_value": round(estimated_reorder_value, 2),
    }


def sidebar_brand_html() -> str:
    return """
    <aside>
        <div class="brand-lockup">
            <div class="brand-icon">KS</div>
            <div>
                <div class="brand-title">Kirana AI</div>
                <div class="brand-subtitle">Sample</div>
            </div>
        </div>
        <div class="sidebar-label">Workspace</div>
    </aside>
    """


def endpoint_status() -> dict[str, bool]:
    return {
        "ocr": bool(os.getenv("MODAL_RECEIPT_ENDPOINT", "").strip()),
        "speech": bool(
            (
                os.getenv("MODAL_SPEECH_ENDPOINT")
                or os.getenv("SPEECH_ASR_ENDPOINT")
                or ""
            ).strip()
        ),
        "hf_model": bool(os.getenv("HF_RECEIPT_MODEL_REPO", "").strip()),
        "modal_parser": bool(
            (
                os.getenv("MODAL_RECEIPT_LLM_ENDPOINT")
                or os.getenv("MODAL_RECEIPT_PARSER_ENDPOINT")
                or ""
            ).strip()
        ),
    }


def sidebar_footer_html() -> str:
    status = endpoint_status()
    ocr_text = "OCR ready" if status["ocr"] else "OCR endpoint missing"
    speech_text = "Speech ready" if status["speech"] else "Speech endpoint missing"
    return f"""
    <aside>
        <div class="sidebar-footer">
            <div class="sidebar-status"><span class="status-dot"></span>{ocr_text}</div>
            <div>{speech_text}</div>
        </div>
    </aside>
    """


def select_tab(tab_id: str):
    return gr.update(selected=tab_id)


def dashboard_header_html() -> str:
    stats = dashboard_stats()
    return f"""
    <section class="hero-bar">
        <div>
            <h1 class="hero-title">Dukaan Saathi</h1>
            <p class="hero-copy">
                Inventory copilot for stock commands, receipt intake, owner approval,
                and reorder drafting.
            </p>
        </div>
        <div class="backend-pill">Receipt backend: {config.RECEIPT_BACKEND}</div>
    </section>
    <section class="metric-grid">
        <div class="metric-card">
            <div class="metric-value">{stats["total_items"]}</div>
            <div class="metric-subtitle">items across all categories</div>
        </div>
        <div class="metric-card">
            <div class="metric-value warn">{stats["low_stock_count"]}</div>
            <div class="metric-subtitle">need restocking</div>
        </div>
        <div class="metric-card">
            <div class="metric-value danger">{stats["out_count"]}</div>
            <div class="metric-subtitle">currently out of stock</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">Rs {stats["estimated_reorder_value"]:,.0f}</div>
            <div class="metric-subtitle">estimated replenishment value</div>
        </div>
    </section>
    """


def capabilities_html() -> str:
    status = endpoint_status()
    receipt_backend_status = {
        "hf_inference": "HF model configured" if status["hf_model"] else "HF model repo missing",
        "modal_llm": "Modal parser configured" if status["modal_parser"] else "Modal parser endpoint missing",
        "llamacpp": "Local llama.cpp backend selected",
        "deterministic": "Rule-based parser selected",
    }.get(config.RECEIPT_BACKEND, "Unknown parser backend")
    ocr_status = "configured" if status["ocr"] else "not configured"
    speech_status = "configured" if status["speech"] else "not configured"
    return f"""
    <div class="capability-grid">
        <div class="capability-card">
            <strong>Receipt text parser</strong>
            <span>Backend: <strong>{config.RECEIPT_BACKEND}</strong>. {receipt_backend_status}. The fine-tuned model parses receipt text into editable rows.</span>
        </div>
        <div class="capability-card">
            <strong>Photo OCR</strong>
            <span>MiniCPM-V endpoint is {ocr_status}. When configured, uploaded receipt photos are converted to text before parsing.</span>
        </div>
        <div class="capability-card">
            <strong>Voice correction</strong>
            <span>Speech ASR endpoint is {speech_status}. When configured, audio fills the correction command only.</span>
        </div>
    </div>
    """


def _react_agent():
    from dukaan_saathi.agent.react_agent import get_react_agent

    return get_react_agent()


def _parse_receipt_with_configured_backend(raw_text: str):
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


def handle_parse_command(command: str):
    try:
        result = _react_agent().parse_stock_command(command)
        action = result.action or {}
        trace = "\n".join(result.trace)
        if action.get("status") != "pending_approval":
            raise ValueError("ReAct agent returned no pending approval action")
    except Exception as exc:
        action, trace_list = parse_stock_command(command)
        trace = "\n".join([f"ReAct agent unavailable; using deterministic parser: {exc}", *trace_list])
    return action, trace, action


def handle_parse_command_for_ui(command: str):
    _action, trace, pending = handle_parse_command(command)
    return trace, pending


def handle_approve_command(action):
    message, trace = approve_command_action(action)
    return inventory_df(), message, "\n".join(trace), None


def handle_parse_receipt(image, raw_text: str):
    if image is not None and not raw_text.strip():
        trace = [
            "Receipt image received.",
            "Use 'Read uploaded photo' to run OCR.",
        ]
        return empty_receipt_df(), "\n".join(trace)

    try:
        result = _react_agent().parse_receipt_text(raw_text)
        rows = result.receipt_rows or []
        trace = "\n".join(result.trace)
        if not rows:
            raise ValueError("ReAct agent returned no receipt rows")
    except Exception as exc:
        try:
            rows, trace_list = _parse_receipt_with_configured_backend(raw_text)
            trace = "\n".join([
                f"ReAct agent unavailable; using configured receipt backend ({config.RECEIPT_BACKEND}): {exc}",
                *trace_list,
            ])
        except Exception as backend_exc:
            rows, fallback_trace = parse_receipt_text(raw_text)
            trace = "\n".join([
                f"Configured receipt backend ({config.RECEIPT_BACKEND}) failed: {backend_exc}",
                "Fallback parser produced editable rows; verify carefully before approval.",
                *fallback_trace,
            ])
    df = pd.DataFrame(rows, columns=RECEIPT_COLUMNS)
    return df, trace


def handle_load_sample_receipt(filename: str):
    text = load_sample_receipt(filename)
    df, trace = handle_parse_receipt(None, text)
    return text, df, "Loaded sample receipt and parsed editable rows.\n" + trace


def handle_extract_receipt_image(image_path, raw_text: str = ""):
    if not image_path and raw_text.strip():
        df, trace = handle_parse_receipt(None, raw_text)
        return df, "No photo uploaded; parsed the receipt text instead.\n" + trace

    if not image_path:
        return empty_receipt_df(), "Upload a receipt photo or load a sample receipt first."

    try:
        result = _react_agent().extract_receipt_image(str(image_path or ""))
        rows = result.receipt_rows or []
        trace = "\n".join(result.trace)
        if not rows:
            raise ValueError("ReAct agent returned no rows")
    except Exception as exc:
        rows, trace_list = extract_receipt_with_modal(image_path)
        trace = "\n".join([f"ReAct image flow unavailable; using Modal receipt client: {exc}", *trace_list])
    df = pd.DataFrame(rows, columns=RECEIPT_COLUMNS)
    return df, trace


def handle_transcribe_correction_audio(audio_path, current_command: str):
    transcript, trace = transcribe_audio(audio_path)
    if transcript.strip():
        trace.append("Filled correction command from speech transcript.")
        return transcript.strip(), "\n".join(trace)

    trace.append("No transcript produced; keeping existing correction command.")
    return current_command or "", "\n".join(trace)


def handle_apply_receipt_correction(receipt_df, command_text: str):
    rows, trace = apply_receipt_correction_command(receipt_df, command_text)
    df = pd.DataFrame(rows, columns=RECEIPT_COLUMNS)
    return df, "\n".join(trace)


def handle_approve_receipt(receipt_df):
    message, trace = approve_receipt_rows(receipt_df)
    updated_inventory = inventory_df()
    return updated_inventory, updated_inventory, message, "\n".join(trace)


def handle_draft_reorder():
    rows, trace = draft_reorder()
    df = pd.DataFrame(rows, columns=REORDER_COLUMNS)
    return df, "\n".join(trace)


def build_demo() -> gr.Blocks:
    init_db()

    with gr.Blocks(
        title="Dukaan Saathi",
    ) as demo:
        pending_action = gr.State(None)

        with gr.Row(elem_classes=["app-shell"]):
            with gr.Column(elem_classes=["sidebar"]):
                gr.HTML(sidebar_brand_html())
                nav_overview = gr.Button("Overview", elem_classes=["nav-button", "nav-button-primary"])
                nav_how_to = gr.Button("How to?", elem_classes=["nav-button"])
                nav_inventory = gr.Button("Inventory", elem_classes=["nav-button"])
                nav_stock_command = gr.Button("Stock Command", elem_classes=["nav-button"])
                nav_receipt_ai = gr.Button("Bill Desk", elem_classes=["nav-button"])
                nav_reorder = gr.Button("Reorder", elem_classes=["nav-button"])
                gr.HTML(sidebar_footer_html())

            with gr.Column(elem_classes=["main-surface"]):
                gr.HTML(dashboard_header_html())

                with gr.Tabs(selected="overview", elem_classes=["gradio-tabs"]) as workspace_tabs:
                    with gr.Tab(bi("Overview"), id="overview"):
                        gr.Markdown(capabilities_html())
                        with gr.Row():
                            overview_receipt_btn = gr.Button("Open Bill Desk", variant="primary")
                            overview_reorder_open_btn = gr.Button("Open reorder draft")
                        with gr.Row():
                            with gr.Column():
                                gr.Markdown(
                                    """
                                    <div class="panel-heading">
                                    <h2>Command intake</h2>
                                    <div class="panel-subtitle">Parse stock updates, then approve before inventory changes.</div>
                                    </div>
                                    <div class="info-strip">
                                    Try: <strong>add Bun 12</strong>, <strong>set OBM stock 5</strong>, or <strong>Happy Happy low</strong>.
                                    </div>
                                    """
                                )
                                overview_command_input = gr.Textbox(
                                    label=bi("Quick stock command"),
                                    placeholder="add Bun 12",
                                )
                                overview_parse_command_btn = gr.Button(
                                    bi("Parse command"),
                                    variant="primary",
                                )
                                overview_command_trace = gr.Textbox(
                                    label=bi("Agent trace"),
                                    lines=6,
                                    elem_classes=["trace-box"],
                                )
                                overview_approve_command_btn = gr.Button(
                                    bi("Approve command update"),
                                    variant="primary",
                                )
                                overview_command_result = gr.Textbox(label=bi("Approval result"))

                    with gr.Tab("How to?", id="how-to"):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>How to use the app</h2>
                            <div class="panel-subtitle">Follow this frontend pipeline from left to right. Inventory changes only happen after approval.</div>
                            </div>
                            <div class="info-strip">
                            The app has four real workflows: inventory review, stock command approval, receipt intake, and reorder drafting.
                            </div>
                            """
                        )
                        gr.Markdown(
                            f"""
                            <div class="howto-section">
                            <h3>1. Check the current shop state</h3>
                            <ol class="howto-list">
                                <li>Open <strong>Overview</strong> to see which model backend is active and whether OCR or speech endpoints are configured.</li>
                                <li>Open <strong>Inventory</strong> to inspect current stock, reorder thresholds, suppliers, and item status.</li>
                                <li>Use <strong>Refresh inventory</strong> after approving changes if you want to reload the table.</li>
                            </ol>
                            </div>

                            <div class="howto-section">
                            <h3>2. Update stock from a typed command</h3>
                            <ol class="howto-list">
                                <li>Open <strong>Stock Command</strong>.</li>
                                <li>Type a stock command in the command box. Example: <strong>add Bun 12</strong>.</li>
                                <li>Click <strong>Parse command</strong>.</li>
                                <li>Review the agent trace.</li>
                                <li>Click <strong>Approve command update</strong> only if the proposal is correct. This is when inventory changes.</li>
                            </ol>
                            </div>

                            <div class="howto-section">
                            <h3>3. Import a receipt with text or photo</h3>
                            <ol class="howto-list">
                                <li>Open <strong>Bill Desk</strong>.</li>
                                <li>For a photo receipt, upload or capture the image, then click <strong>Read uploaded photo</strong>.</li>
                                <li>Photo OCR uses MiniCPM-V only when <strong>MODAL_RECEIPT_ENDPOINT</strong> is configured.</li>
                                <li>For pasted receipt text, paste the text into <strong>Receipt text / OCR text</strong>, then click <strong>Parse receipt text</strong>.</li>
                                <li>Receipt text parsing uses <strong>{config.RECEIPT_BACKEND}</strong>. The fine-tuned model is this receipt text parser.</li>
                                <li>Parsed rows appear in the editable receipt table. Nothing has changed inventory yet.</li>
                            </ol>
                            </div>

                            <div class="howto-section">
                            <h3>4. Correct receipt rows by typing or voice</h3>
                            <ol class="howto-list">
                                <li>To correct by typing, enter a command in <strong>Correction command from text or speech</strong>.</li>
                                <li>Example correction: <strong>first one Parle bulk, second one Bingo</strong>.</li>
                                <li>To correct by voice, record or upload audio under <strong>Record or upload correction audio</strong>.</li>
                                <li>Click <strong>Transcribe audio to command</strong>. Speech runs only when <strong>MODAL_SPEECH_ENDPOINT</strong> or <strong>SPEECH_ASR_ENDPOINT</strong> is configured.</li>
                                <li>The transcript fills the same correction command box.</li>
                                <li>Click <strong>Apply correction</strong> to update the editable receipt rows.</li>
                            </ol>
                            </div>

                            <div class="howto-section">
                            <h3>5. Approve receipt rows</h3>
                            <ol class="howto-list">
                                <li>Review each editable row, especially product match, quantity, price, and warning columns.</li>
                                <li>Use the apply column to skip rows that should not affect inventory.</li>
                                <li>Click <strong>Approve rows and update inventory</strong> only when the table is correct.</li>
                                <li>Confirm the changed stock in <strong>Inventory after approval</strong>.</li>
                                <li class="note">Approval is the only step that writes receipt changes to inventory.</li>
                            </ol>
                            </div>

                            <div class="howto-section">
                            <h3>6. Generate reorder suggestions</h3>
                            <ol class="howto-list">
                                <li>Open <strong>Reorder</strong>.</li>
                                <li>Click <strong>Generate reorder draft</strong>.</li>
                                <li>The app compares current stock to reorder thresholds and suggests purchase quantities.</li>
                                <li>The reorder table is read-only. It does not send a purchase order.</li>
                            </ol>
                            </div>
                            """
                        )
                        howto_receipt_btn = gr.Button("Open Bill Desk", variant="primary")

                    with gr.Tab(bi("Inventory"), id="inventory"):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>Inventory</h2>
                            <div class="panel-subtitle">Current stock, thresholds, targets, and status.</div>
                            </div>
                            """
                        )
                        inventory_table = gr.Dataframe(
                            value=inventory_df,
                            headers=INVENTORY_COLUMNS,
                            interactive=False,
                            wrap=True,
                            label=bi("Current inventory"),
                            elem_classes=["inventory-table"],
                        )
                        refresh_btn = gr.Button(bi("Refresh inventory"))
                        refresh_btn.click(fn=inventory_df, outputs=inventory_table)

                    with gr.Tab(bi("Stock command"), id="stock-command"):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>Stock command</h2>
                            <div class="panel-subtitle">Every proposed update waits for owner approval.</div>
                            </div>
                            <div class="info-strip">
                            Try: <strong>add Bun 12</strong>, <strong>set OBM stock 5</strong>,
                            or <strong>Happy Happy low</strong>.
                            </div>
                            """
                        )

                        command_input = gr.Textbox(
                            label=bi("Typed stock command"),
                            placeholder="add Bun 12",
                        )
                        parse_command_btn = gr.Button(bi("Parse command"), variant="primary")

                        command_trace = gr.Textbox(
                            label=bi("Agent trace"),
                            lines=10,
                            elem_classes=["trace-box"],
                        )

                        approve_command_btn = gr.Button(
                            bi("Approve command update"),
                            variant="primary",
                        )
                        command_result = gr.Textbox(label=bi("Approval result"))

                        parse_command_btn.click(
                            fn=handle_parse_command_for_ui,
                            inputs=command_input,
                            outputs=[command_trace, pending_action],
                        )
                        approve_command_btn.click(
                            fn=handle_approve_command,
                            inputs=pending_action,
                            outputs=[inventory_table, command_result, command_trace, pending_action],
                        )
                        overview_parse_command_btn.click(
                            fn=handle_parse_command_for_ui,
                            inputs=overview_command_input,
                            outputs=[overview_command_trace, pending_action],
                        )
                        overview_approve_command_btn.click(
                            fn=handle_approve_command,
                            inputs=pending_action,
                            outputs=[inventory_table, overview_command_result, overview_command_trace, pending_action],
                        )

                    with gr.Tab(bi("Bill Desk"), id="receipt-import"):
                        gr.Markdown(
                            f"""
                            <div class="panel-heading">
                            <h2>Bill Desk</h2>
                            <div class="panel-subtitle">Photo OCR, fine-tuned receipt text parsing, speech correction, editable rows, then owner approval.</div>
                            </div>
                            <div class="info-strip">
                            Pipeline: receipt photo → MiniCPM-V OCR → <strong>{config.RECEIPT_BACKEND}</strong> receipt parser → editable table → typed or spoken correction → approval.
                            </div>
                            """
                        )

                        with gr.Row():
                            sample_receipt_dropdown = gr.Dropdown(
                                choices=list_sample_receipts(),
                                label="Sample receipt",
                                value=None,
                                scale=3,
                            )
                            load_sample_btn = gr.Button("Load and parse sample", scale=1)

                        with gr.Row():
                            receipt_image = gr.Image(
                                label=bi("Receipt image"),
                                type="filepath",
                                sources=["upload", "webcam"],
                            )
                            receipt_text = gr.Textbox(
                                label=bi("Receipt text / OCR text"),
                                value=SAMPLE_RECEIPT,
                                lines=10,
                            )

                        with gr.Row():
                            parse_receipt_btn = gr.Button(
                                bi("Parse receipt text"),
                                variant="primary",
                            )
                            extract_image_btn = gr.Button(
                                bi("Read uploaded photo"),
                            )
                        receipt_table = gr.Dataframe(
                            value=empty_receipt_df,
                            headers=RECEIPT_COLUMNS,
                            interactive=True,
                            wrap=True,
                            label=bi("Editable extracted receipt rows"),
                            elem_classes=["receipt-table"],
                        )
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h3>Correct extracted rows</h3>
                            <div class="panel-subtitle">Type a correction, or record/upload audio and transcribe it into the same command box.</div>
                            </div>
                            """
                        )
                        with gr.Row():
                            receipt_correction_audio = gr.Audio(
                                label=bi("Record or upload correction audio"),
                                type="filepath",
                                sources=["microphone", "upload"],
                                scale=3,
                                elem_classes=["speech-control"],
                            )
                            transcribe_correction_btn = gr.Button(
                                bi("Transcribe audio to command"),
                                scale=1,
                            )
                        receipt_correction_input = gr.Textbox(
                            label=bi("Correction command from text or speech"),
                            placeholder="first one Parle bulk, second one Bingo",
                            lines=2,
                        )
                        apply_receipt_correction_btn = gr.Button(
                            bi("Apply correction"),
                        )
                        receipt_trace = gr.Textbox(
                            label=bi("Receipt trace"),
                            lines=10,
                            elem_classes=["trace-box"],
                        )
                        approve_receipt_btn = gr.Button(
                            bi("Approve rows and update inventory"),
                            variant="primary",
                        )
                        receipt_result = gr.Textbox(label=bi("Approval result"))
                        receipt_inventory_snapshot = gr.Dataframe(
                            value=inventory_df,
                            headers=INVENTORY_COLUMNS,
                            interactive=False,
                            wrap=True,
                            label=bi("Inventory after approval"),
                            elem_classes=["inventory-table"],
                        )

                        load_sample_btn.click(
                            fn=handle_load_sample_receipt,
                            inputs=sample_receipt_dropdown,
                            outputs=[receipt_text, receipt_table, receipt_trace],
                        )
                        parse_receipt_btn.click(
                            fn=handle_parse_receipt,
                            inputs=[receipt_image, receipt_text],
                            outputs=[receipt_table, receipt_trace],
                        )
                        extract_image_btn.click(
                            fn=handle_extract_receipt_image,
                            inputs=[receipt_image, receipt_text],
                            outputs=[receipt_table, receipt_trace],
                        )
                        transcribe_correction_btn.click(
                            fn=handle_transcribe_correction_audio,
                            inputs=[receipt_correction_audio, receipt_correction_input],
                            outputs=[receipt_correction_input, receipt_trace],
                        )
                        apply_receipt_correction_btn.click(
                            fn=handle_apply_receipt_correction,
                            inputs=[receipt_table, receipt_correction_input],
                            outputs=[receipt_table, receipt_trace],
                        )

                        approve_receipt_btn.click(
                            fn=handle_approve_receipt,
                            inputs=receipt_table,
                            outputs=[
                                inventory_table,
                                receipt_inventory_snapshot,
                                receipt_result,
                                receipt_trace,
                            ],
                        )

                    with gr.Tab(bi("Reorder draft"), id="reorder-draft"):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>Reorder draft</h2>
                            <div class="panel-subtitle">Calculates low-stock items from the current inventory and suggests how much to buy. Nothing is sent automatically.</div>
                            </div>
                            <div class="info-strip">
                            Click <strong>Generate reorder draft</strong> after inventory changes. The table is read-only because purchasing is outside this MVP.
                            </div>
                            """
                        )

                        reorder_btn = gr.Button(bi("Generate reorder draft"), variant="primary")
                        reorder_table = gr.Dataframe(
                            value=empty_reorder_df,
                            headers=REORDER_COLUMNS,
                            interactive=False,
                            wrap=True,
                            label=bi("Reorder draft"),
                            elem_classes=["reorder-table"],
                        )
                        reorder_trace = gr.Textbox(
                            label=bi("Reorder trace"),
                            lines=10,
                            elem_classes=["trace-box"],
                        )

                        reorder_btn.click(
                            fn=handle_draft_reorder,
                            outputs=[reorder_table, reorder_trace],
                        )
                        overview_receipt_btn.click(fn=lambda: select_tab("receipt-import"), outputs=workspace_tabs)
                        overview_reorder_open_btn.click(fn=lambda: select_tab("reorder-draft"), outputs=workspace_tabs)

                demo.load(fn=inventory_df, outputs=inventory_table)

                nav_overview.click(fn=lambda: select_tab("overview"), outputs=workspace_tabs)
                nav_how_to.click(fn=lambda: select_tab("how-to"), outputs=workspace_tabs)
                nav_inventory.click(fn=lambda: select_tab("inventory"), outputs=workspace_tabs)
                nav_stock_command.click(fn=lambda: select_tab("stock-command"), outputs=workspace_tabs)
                nav_receipt_ai.click(fn=lambda: select_tab("receipt-import"), outputs=workspace_tabs)
                nav_reorder.click(fn=lambda: select_tab("reorder-draft"), outputs=workspace_tabs)
                howto_receipt_btn.click(fn=lambda: select_tab("receipt-import"), outputs=workspace_tabs)

        # Gradio 6 moved css/theme to launch(), but hosted Gradio runtimes often
        # launch the exported Blocks object themselves. Keep the exported demo styled.
        demo._deprecated_css = CUSTOM_CSS
        demo._deprecated_theme = THEME

    return demo
