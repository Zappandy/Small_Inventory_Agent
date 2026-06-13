from __future__ import annotations
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
    --kirana-muted: #9fb6ad;
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
}

.brand-subtitle,
.sidebar-label,
.sidebar-status,
.metric-subtitle,
.panel-subtitle {
    color: var(--kirana-muted);
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

def bi(en: str, te: str) -> str:
    return f"{en} · {te}"


def inventory_df() -> pd.DataFrame:
    return pd.DataFrame(get_inventory(), columns=INVENTORY_COLUMNS)


def empty_receipt_df() -> pd.DataFrame:
    return pd.DataFrame(columns=RECEIPT_COLUMNS)


def empty_reorder_df() -> pd.DataFrame:
    return pd.DataFrame(columns=REORDER_COLUMNS)


def sidebar_html() -> str:
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
        <div class="nav-item active"><span>Overview</span><span class="nav-count">14</span></div>
        <div class="nav-item"><span>Inventory</span></div>
        <div class="nav-item"><span>Add Product</span></div>
        <div class="nav-item"><span>Orders</span><span class="nav-count">565</span></div>
        <div class="nav-item"><span>Analytics</span></div>
        <div class="nav-item"><span>Seasonal</span></div>
        <div class="nav-item"><span>Settings</span></div>
        <div class="sidebar-footer">
            <div class="sidebar-status"><span class="status-dot"></span>Vision offline</div>
            <div>Andhra Pradesh · runs locally</div>
        </div>
    </aside>
    """


def dashboard_header_html() -> str:
    return f"""
    <section class="hero-bar">
        <div>
            <h1 class="hero-title">Dukaan Saathi</h1>
            <p class="hero-copy">
                Telugu and code-mixed inventory copilot for stock commands, receipt intake,
                owner approval, and reorder drafting.
            </p>
        </div>
        <div class="backend-pill">Receipt backend: {config.RECEIPT_BACKEND}</div>
    </section>
    <section class="metric-grid">
        <div class="metric-card">
            <div class="metric-value">36</div>
            <div class="metric-subtitle">items across all categories</div>
        </div>
        <div class="metric-card">
            <div class="metric-value warn">14</div>
            <div class="metric-subtitle">need restocking</div>
        </div>
        <div class="metric-card">
            <div class="metric-value danger">7</div>
            <div class="metric-subtitle">expired, clear today</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">Rs 27,449</div>
            <div class="metric-subtitle">estimated replenishment value</div>
        </div>
    </section>
    """


def _react_agent():
    from dukaan_saathi.agent.react_agent import get_react_agent

    return get_react_agent()


def _parse_receipt_with_configured_backend(raw_text: str):
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
        trace = result.trace
        if action.get("status") != "pending_approval":
            raise ValueError("ReAct agent returned no pending approval action")
    except Exception as exc:
        action, trace_list = parse_stock_command(command)
        trace = "\n".join([f"ReAct agent unavailable; using deterministic parser: {exc}", *trace_list])
    return action, trace, action


def handle_approve_command(action):
    message, trace = approve_command_action(action)
    return inventory_df(), message, "\n".join(trace), None


def handle_parse_receipt(image, raw_text: str):
    if image is not None and not raw_text.strip():
        trace = [
            "Receipt image received.",
            "Use 'Extract from image with model' button to run MiniCPM-V OCR.",
        ]
        return empty_receipt_df(), "\n".join(trace)

    try:
        result = _react_agent().parse_receipt_text(raw_text)
        rows = result.receipt_rows or []
        trace = result.trace
        if not rows:
            raise ValueError("ReAct agent returned no receipt rows")
    except Exception as exc:
        rows, trace_list = _parse_receipt_with_configured_backend(raw_text)
        trace = "\n".join([
            f"ReAct agent unavailable; using configured receipt backend ({config.RECEIPT_BACKEND}): {exc}",
            *trace_list,
        ])
    df = pd.DataFrame(rows, columns=RECEIPT_COLUMNS)
    return df, trace


def handle_extract_receipt_image(image_path):
    try:
        result = _react_agent().extract_receipt_image(str(image_path or ""))
        rows = result.receipt_rows or []
        trace = result.trace
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
    return inventory_df(), message, "\n".join(trace)


def handle_draft_reorder():
    rows, trace = draft_reorder()
    df = pd.DataFrame(rows, columns=REORDER_COLUMNS)
    return df, "\n".join(trace)


def build_demo() -> gr.Blocks:
    init_db()

    with gr.Blocks(
        title="Dukaan Saathi",
        css=CUSTOM_CSS,
        theme=THEME,
    ) as demo:
        pending_action = gr.State(None)

        with gr.Row(elem_classes=["app-shell"]):
            with gr.Column(elem_classes=["sidebar"]):
                gr.HTML(sidebar_html())

            with gr.Column(elem_classes=["main-surface"]):
                gr.HTML(dashboard_header_html())

                with gr.Tabs(elem_classes=["gradio-tabs"]):
                    with gr.Tab(bi("Overview", "సారాంశం")):
                        with gr.Row():
                            with gr.Column(scale=3):
                                gr.Markdown(
                                    """
                                    <div class="panel-heading">
                                    <h2>Reorder queue</h2>
                                    <div class="panel-subtitle">Low stock items proposed for owner review.</div>
                                    </div>
                                    """
                                )
                                reorder_preview = gr.Dataframe(
                                    value=empty_reorder_df,
                                    headers=REORDER_COLUMNS,
                                    interactive=True,
                                    wrap=True,
                                    label=bi("Editable reorder draft", "సవరించగలిగే ఆర్డర్ డ్రాఫ్ట్"),
                                )
                                overview_reorder_btn = gr.Button(
                                    bi("Refresh reorder queue", "రీఆర్డర్ రిఫ్రెష్"),
                                    variant="primary",
                                )
                                overview_reorder_trace = gr.Textbox(
                                    label=bi("Reorder trace", "రీఆర్డర్ ట్రేస్"),
                                    lines=6,
                                    elem_classes=["trace-box"],
                                )
                            with gr.Column(scale=2):
                                gr.Markdown(
                                    """
                                    <div class="panel-heading">
                                    <h2>Command intake</h2>
                                    <div class="panel-subtitle">Parse Telugu/code-mixed updates, then approve.</div>
                                    </div>
                                    <div class="info-strip">
                                    Try: <code>Bingo అయిపోయింది</code>, <code>add Thums Up 12</code>, or <code>Lays Classic low</code>.
                                    </div>
                                    """
                                )
                                overview_command_input = gr.Textbox(
                                    label=bi("Quick stock command", "త్వరిత కమాండ్"),
                                    placeholder="Bingo అయిపోయింది",
                                )
                                overview_parse_command_btn = gr.Button(
                                    bi("Parse command", "కమాండ్ చదవు"),
                                    variant="primary",
                                )
                                overview_proposed_action = gr.JSON(
                                    label=bi("Proposed action", "ప్రతిపాదిత చర్య")
                                )
                                overview_command_trace = gr.Textbox(
                                    label=bi("Agent trace", "ఏజెంట్ ట్రేస్"),
                                    lines=6,
                                    elem_classes=["trace-box"],
                                )
                                overview_approve_command_btn = gr.Button(
                                    bi("Approve command update", "ఆమోదించు"),
                                    variant="primary",
                                )
                                overview_command_result = gr.Textbox(label=bi("Approval result", "ఫలితం"))

                    with gr.Tab(bi("Inventory", "స్టాక్")):
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
                            label=bi("Current inventory", "ప్రస్తుత స్టాక్"),
                        )
                        refresh_btn = gr.Button(bi("Refresh inventory", "స్టాక్ రిఫ్రెష్"))
                        refresh_btn.click(fn=inventory_df, outputs=inventory_table)

                    with gr.Tab(bi("Stock command", "కమాండ్")):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>Stock command</h2>
                            <div class="panel-subtitle">Every proposed update waits for owner approval.</div>
                            </div>
                            <div class="info-strip">
                            Try: <code>Bingo అయిపోయింది</code>, <code>add Thums Up 12</code>,
                            <code>Lays Classic low</code>, or <code>Parle-G 100g stock 5</code>.
                            </div>
                            """
                        )

                        command_input = gr.Textbox(
                            label=bi("Typed Telugu / code-mixed command", "కమాండ్"),
                            placeholder="Bingo అయిపోయింది",
                        )
                        parse_command_btn = gr.Button(bi("Parse command", "కమాండ్ చదవు"), variant="primary")

                        with gr.Row():
                            proposed_action = gr.JSON(label=bi("Proposed action", "ప్రతిపాదిత చర్య"))
                            command_trace = gr.Textbox(
                                label=bi("Agent trace", "ఏజెంట్ ట్రేస్"),
                                lines=10,
                                elem_classes=["trace-box"],
                            )

                        approve_command_btn = gr.Button(
                            bi("Approve command update", "ఆమోదించు"),
                            variant="primary",
                        )
                        command_result = gr.Textbox(label=bi("Approval result", "ఫలితం"))

                        parse_command_btn.click(
                            fn=handle_parse_command,
                            inputs=command_input,
                            outputs=[proposed_action, command_trace, pending_action],
                        )
                        approve_command_btn.click(
                            fn=handle_approve_command,
                            inputs=pending_action,
                            outputs=[inventory_table, command_result, command_trace, pending_action],
                        )
                        overview_parse_command_btn.click(
                            fn=handle_parse_command,
                            inputs=overview_command_input,
                            outputs=[overview_proposed_action, overview_command_trace, pending_action],
                        )
                        overview_approve_command_btn.click(
                            fn=handle_approve_command,
                            inputs=pending_action,
                            outputs=[inventory_table, overview_command_result, overview_command_trace, pending_action],
                        )

                    with gr.Tab(bi("Receipt import", "బిల్ ఇంపోర్ట్")):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>Receipt import</h2>
                            <div class="panel-subtitle">Model output fills editable rows first; approval updates stock.</div>
                            </div>
                            """
                        )

                        with gr.Row():
                            sample_receipt_dropdown = gr.Dropdown(
                                choices=list_sample_receipts(),
                                label="Load sample receipt",
                                value=None,
                                scale=3,
                            )
                            load_sample_btn = gr.Button("Load selected sample", scale=1)

                        with gr.Row():
                            receipt_image = gr.Image(
                                label=bi("Receipt image", "బిల్ ఫోటో"),
                                type="filepath",
                                sources=["upload", "webcam"],
                            )
                            receipt_text = gr.Textbox(
                                label=bi("Receipt text / OCR text", "బిల్ టెక్స్ట్"),
                                value=SAMPLE_RECEIPT,
                                lines=10,
                            )

                        load_sample_btn.click(
                            fn=load_sample_receipt,
                            inputs=sample_receipt_dropdown,
                            outputs=receipt_text,
                        )

                        with gr.Row():
                            parse_receipt_btn = gr.Button(
                                bi("Parse pasted/sample text", "టెక్స్ట్ బిల్ చదవు"),
                                variant="primary",
                            )
                            extract_image_btn = gr.Button(
                                bi("Extract from image with model", "ఫోటో నుండి చదవు"),
                            )
                        receipt_table = gr.Dataframe(
                            value=empty_receipt_df,
                            headers=RECEIPT_COLUMNS,
                            interactive=True,
                            wrap=True,
                            label=bi("Editable extracted receipt rows", "సవరించగలిగే బిల్ వరుసలు"),
                        )
                        with gr.Row():
                            receipt_correction_audio = gr.Audio(
                                label=bi("Correction audio", "సవరణ ఆడియో"),
                                type="filepath",
                                sources=["microphone", "upload"],
                                scale=3,
                            )
                            transcribe_correction_btn = gr.Button(
                                bi("Transcribe correction audio", "ఆడియోను టెక్స్ట్ చేయి"),
                                scale=1,
                            )
                        receipt_correction_input = gr.Textbox(
                            label=bi("Correction command", "సవరణ కమాండ్"),
                            placeholder="first one Parle bulk, second one Bingo",
                            lines=2,
                        )
                        apply_receipt_correction_btn = gr.Button(
                            bi("Apply correction", "సవరణ వర్తింపజేయి"),
                        )
                        receipt_trace = gr.Textbox(
                            label=bi("Receipt trace", "బిల్ ట్రేస్"),
                            lines=10,
                            elem_classes=["trace-box"],
                        )
                        approve_receipt_btn = gr.Button(
                            bi("Approve receipt rows", "బిల్ వరుసలు ఆమోదించు"),
                            variant="primary",
                        )
                        receipt_result = gr.Textbox(label=bi("Approval result", "ఫలితం"))

                        parse_receipt_btn.click(
                            fn=handle_parse_receipt,
                            inputs=[receipt_image, receipt_text],
                            outputs=[receipt_table, receipt_trace],
                        )
                        extract_image_btn.click(
                            fn=handle_extract_receipt_image,
                            inputs=receipt_image,
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
                            outputs=[inventory_table, receipt_result, receipt_trace],
                        )

                    with gr.Tab(bi("Reorder draft", "రీఆర్డర్")):
                        gr.Markdown(
                            """
                            <div class="panel-heading">
                            <h2>Reorder draft</h2>
                            <div class="panel-subtitle">Drafts a purchase order from inventory thresholds. Nothing is sent automatically.</div>
                            </div>
                            """
                        )

                        reorder_btn = gr.Button(bi("Draft reorder PO", "ఆర్డర్ డ్రాఫ్ట్ చేయి"), variant="primary")
                        reorder_table = gr.Dataframe(
                            value=empty_reorder_df,
                            headers=REORDER_COLUMNS,
                            interactive=True,
                            wrap=True,
                            label=bi("Editable reorder draft", "సవరించగలిగే ఆర్డర్ డ్రాఫ్ట్"),
                        )
                        reorder_trace = gr.Textbox(
                            label=bi("Reorder trace", "రీఆర్డర్ ట్రేస్"),
                            lines=10,
                            elem_classes=["trace-box"],
                        )

                        reorder_btn.click(
                            fn=handle_draft_reorder,
                            outputs=[reorder_table, reorder_trace],
                        )
                        overview_reorder_btn.click(
                            fn=handle_draft_reorder,
                            outputs=[reorder_preview, overview_reorder_trace],
                        )

                demo.load(fn=inventory_df, outputs=inventory_table)

    return demo
