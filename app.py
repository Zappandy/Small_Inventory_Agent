"""
Dukaan Inventory - Telugu Convenience Store Inventory Agent
Veera Bhadra WS, Malkajgiri, Hyderabad

HF Space entry point. Launches Gradio UI with:
- Telugu ASR via Whisper
- Receipt OCR via Qwen2.5-VL
- LangGraph orchestrator + sub-agents
- llama.cpp local inference (no cloud)
- Bilingual Telugu/English UI
"""

import gradio as gr
import json
import asyncio
from pathlib import Path

from agents.graph import build_graph
from agents.state import AgentState
from db.database import init_db, get_stock_levels, get_pending_pos
from models.asr import transcribe_telugu
from models.translate import te_to_en, en_to_te
from models.ocr import parse_receipt_image

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

init_db()
graph = build_graph()

# ---------------------------------------------------------------------------
# Gradio event handlers
# ---------------------------------------------------------------------------

def handle_voice(audio_path: str):
    """Transcribe Telugu audio → translate → run agent graph."""
    if audio_path is None:
        return "", "", []

    telugu_text = transcribe_telugu(audio_path)
    english_text = te_to_en(telugu_text)
    trace_log = []

    result = run_agent(english_text, source="voice", trace_log=trace_log)
    return telugu_text, english_text, trace_log, result


def handle_receipt(image_path: str):
    """OCR receipt image → run agent graph."""
    if image_path is None:
        return "", []

    trace_log = []
    structured = parse_receipt_image(image_path)
    result = run_agent(
        json.dumps(structured, ensure_ascii=False),
        source="receipt",
        trace_log=trace_log,
    )
    return json.dumps(structured, indent=2, ensure_ascii=False), trace_log, result


def handle_text_query(text: str):
    """Direct text query (Telugu or English)."""
    if not text.strip():
        return [], ""

    # Detect script: Telugu Unicode range U+0C00–U+0C7F
    has_telugu = any("\u0C00" <= c <= "\u0C7F" for c in text)
    english_text = te_to_en(text) if has_telugu else text

    trace_log = []
    result = run_agent(english_text, source="query", trace_log=trace_log)
    response_te = en_to_te(result.get("response", ""))
    return trace_log, result.get("response", ""), response_te


def run_agent(input_text: str, source: str, trace_log: list) -> dict:
    """Run the LangGraph agent and collect trace events."""
    initial_state = AgentState(
        input=input_text,
        source=source,
        trace=[],
        structured_data=None,
        intent=None,
        po_draft=None,
        response=None,
    )

    final_state = None
    for step in graph.stream(initial_state):
        node_name = list(step.keys())[0]
        node_state = list(step.values())[0]
        trace_line = f"→ {node_name}: {_summarise(node_state)}"
        trace_log.append(trace_line)
        final_state = node_state

    return final_state or {}


def _summarise(state: dict) -> str:
    if state.get("intent"):
        return f"intent={state['intent']}"
    if state.get("po_draft"):
        total = sum(i.get("total", 0) for i in state["po_draft"].get("items", []))
        return f"PO draft ₹{total}"
    if state.get("response"):
        return state["response"][:60] + "..."
    return "processing"


def refresh_stock():
    rows = get_stock_levels()
    # Returns list of [product, supplier, stock, threshold, status_te, status_en]
    return rows


def approve_po(po_id: str):
    from db.database import approve_purchase_order
    approve_purchase_order(po_id)
    return get_pending_pos()


def reject_po(po_id: str):
    from db.database import reject_purchase_order
    reject_purchase_order(po_id)
    return get_pending_pos()


# ---------------------------------------------------------------------------
# Custom CSS — pushes past basic Gradio
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
/* Top bar */
.topbar-html { font-size: 13px; padding: 10px 0 4px; }
.store-name { font-size: 16px; font-weight: 500; }
.store-sub { font-size: 12px; color: #888; margin-left: 8px; }
.status-pill {
    display: inline-block; font-size: 11px; font-weight: 500;
    padding: 3px 10px; border-radius: 20px;
    background: #EAF3DE; color: #27500A; margin-left: 8px;
}

/* Section headers */
.section-te { font-size: 11px; color: #aaa; font-weight: 400; margin-left: 6px; }

/* Stock table */
.stock-wrap table { font-size: 13px !important; }
.stock-wrap th { font-weight: 500 !important; }
.badge-ok   { background:#EAF3DE; color:#27500A; padding:2px 8px; border-radius:4px; font-size:11px; }
.badge-low  { background:#FAEEDA; color:#633806; padding:2px 8px; border-radius:4px; font-size:11px; }
.badge-out  { background:#FCEBEB; color:#791F1F; padding:2px 8px; border-radius:4px; font-size:11px; }

/* Agent trace */
.trace-box textarea {
    font-family: monospace !important;
    font-size: 12px !important;
    background: #f8f8f6 !important;
    color: #3d3d3a !important;
}

/* Voice button */
.voice-record-btn { border: 2px solid #378ADD !important; }

/* PO approval panel */
.po-panel { border-left: 3px solid #EF9F27; padding-left: 12px; }

/* Bilingual labels */
.bi-label { display: flex; flex-direction: column; gap: 0px; }
.bi-label .en { font-size: 13px; font-weight: 500; }
.bi-label .te { font-size: 11px; color: #aaa; }

/* Gradio overrides */
.gr-button-primary { font-weight: 500 !important; }
footer { display: none !important; }
"""

# ---------------------------------------------------------------------------
# Bilingual label helper
# ---------------------------------------------------------------------------

def bi(en: str, te: str) -> str:
    return f"{en} · {te}"


# ---------------------------------------------------------------------------
# Build Gradio UI
# ---------------------------------------------------------------------------

def build_ui():
    with gr.Blocks(
        title="Dukaan Inventory · దుకాణం",
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.gray,
            font=[gr.themes.GoogleFont("Inter"), "sans-serif"],
        ),
    ) as demo:

        # ── Top bar ──────────────────────────────────────────────────────────
        gr.HTML("""
        <div class="topbar-html">
            <span class="store-name">Dukaan Inventory</span>
            <span class="store-sub">వేర బాధర స్టోర్ · Veera Bhadra WS, Malkajgiri</span>
            <span class="status-pill">llama.cpp online</span>
        </div>
        """)

        # ── Metric cards row ─────────────────────────────────────────────────
        with gr.Row():
            gr.Metric(
                label=bi("Total products", "మొత్తం వస్తువులు"),
                value="42",
            )
            gr.Metric(
                label=bi("Low stock alerts", "హెచ్చరికలు"),
                value="5",
            )
            gr.Metric(
                label=bi("This week sales", "ఈ వారం అమ్మకాలు"),
                value="₹12,450",
            )
            gr.Metric(
                label=bi("Pending POs", "పెండింగ్ ఆర్డర్లు"),
                value="2",
            )

        # ── Main two-column layout ───────────────────────────────────────────
        with gr.Row():

            # Left column: inputs
            with gr.Column(scale=1):
                gr.Markdown(f"### {bi('Input', 'ఇన్‌పుట్')}")

                # Voice input
                with gr.Group():
                    gr.Markdown(f"**{bi('Voice command', 'మాట్లాడండి')}**")
                    audio_input = gr.Audio(
                        sources=["microphone"],
                        type="filepath",
                        label=bi("Speak in Telugu", "Telugu లో మాట్లాడండి"),
                        elem_classes=["voice-record-btn"],
                    )
                    with gr.Row():
                        telugu_heard = gr.Textbox(
                            label=bi("Heard (Telugu)", "విన్నది"),
                            interactive=False,
                            scale=1,
                        )
                        english_translation = gr.Textbox(
                            label=bi("Translated", "అనువాదం"),
                            interactive=False,
                            scale=1,
                        )
                    voice_btn = gr.Button(
                        bi("Process voice", "వాయిస్ ప్రాసెస్ చేయి"),
                        variant="primary",
                    )

                # Receipt upload
                with gr.Group():
                    gr.Markdown(f"**{bi('Receipt photo', 'బిల్ ఫోటో')}**")
                    receipt_image = gr.Image(
                        sources=["upload", "webcam"],
                        type="filepath",
                        label=bi("Upload receipt", "బిల్ అప్‌లోడ్ చేయండి"),
                        height=160,
                    )
                    receipt_btn = gr.Button(
                        bi("Parse receipt", "బిల్ చదవు"),
                        variant="primary",
                    )
                    parsed_json = gr.Code(
                        label=bi("Parsed data", "చదివిన డేటా"),
                        language="json",
                        lines=6,
                    )

                # Text query
                with gr.Group():
                    gr.Markdown(f"**{bi('Ask a question', 'అడగండి')}**")
                    query_input = gr.Textbox(
                        label=bi(
                            "Type in Telugu or English",
                            "Telugu లో లేదా English లో రాయండి",
                        ),
                        placeholder="e.g. 'Bingo stock ఎంత ఉంది?' or 'Show weekly report'",
                        lines=2,
                    )
                    query_btn = gr.Button(
                        bi("Ask", "అడుగు"),
                        variant="primary",
                    )
                    with gr.Row():
                        response_en = gr.Textbox(
                            label=bi("Response (English)", "సమాధానం"),
                            interactive=False,
                            scale=1,
                        )
                        response_te = gr.Textbox(
                            label=bi("Response (Telugu)", "సమాధానం తెలుగులో"),
                            interactive=False,
                            scale=1,
                        )

            # Right column: stock + trace + PO
            with gr.Column(scale=1):
                gr.Markdown(f"### {bi('Live stock', 'స్టాక్ స్థాయిలు')}")

                stock_table = gr.Dataframe(
                    headers=[
                        bi("Product", "వస్తువు"),
                        bi("Supplier", "వ్యాపారి"),
                        bi("Stock", "స్టాక్"),
                        "Threshold",
                        bi("Status", "స్థితి"),
                    ],
                    datatype=["str", "str", "str", "str", "str"],
                    interactive=False,
                    elem_classes=["stock-wrap"],
                    wrap=True,
                )
                refresh_btn = gr.Button(
                    bi("Refresh stock", "స్టాక్ రిఫ్రెష్"),
                    size="sm",
                )

                gr.Markdown(f"### {bi('Agent trace', 'ఏజెంట్ పని')}")
                trace_output = gr.Textbox(
                    label=bi("Live execution trace", "లైవ్ ట్రేస్"),
                    lines=8,
                    interactive=False,
                    elem_classes=["trace-box"],
                )

                gr.Markdown(
                    f"### {bi('Purchase order approval', 'ఆర్డర్ ఆమోదం')} "
                    f"_(HITL · మీ అనుమతి కావాలి)_"
                )
                with gr.Group(elem_classes=["po-panel"]):
                    po_display = gr.Dataframe(
                        headers=[
                            "PO ID",
                            bi("Supplier", "వ్యాపారి"),
                            bi("Items", "వస్తువులు"),
                            bi("Total", "మొత్తం"),
                            bi("Reason (Telugu)", "కారణం"),
                        ],
                        datatype=["str", "str", "str", "str", "str"],
                        interactive=False,
                    )
                    po_id_input = gr.Textbox(
                        label=bi("PO ID to action", "PO ID"),
                        placeholder="e.g. PO-001",
                    )
                    with gr.Row():
                        approve_btn = gr.Button(
                            bi("Approve", "ఆమోదించు"),
                            variant="primary",
                        )
                        reject_btn = gr.Button(
                            bi("Reject", "వద్దు"),
                            variant="stop",
                        )
                        edit_btn = gr.Button(
                            bi("Edit qty", "పరిమాణం మార్చు"),
                        )

        # ── Settings tab ─────────────────────────────────────────────────────
        with gr.Accordion(
            bi("Product setup & policies", "వస్తువు సెటప్ & నియమాలు"),
            open=False,
        ):
            gr.Markdown(
                f"_{bi('Configure products, aliases, thresholds, suppliers', 'వస్తువులు, పేర్లు, హెచ్చరిక స్థాయిలు సెటప్ చేయండి')}_"
            )
            with gr.Row():
                with gr.Column():
                    gr.Markdown(f"**{bi('Add / edit product', 'వస్తువు చేర్చు')}**")
                    prod_name = gr.Textbox(label=bi("Product name (English)", "వస్తువు పేరు"))
                    prod_alias = gr.Textbox(
                        label=bi("Aliases / shorthand", "సంక్షిప్త పేర్లు"),
                        placeholder="e.g. Bm, bingo, Bingo(C)",
                    )
                    prod_supplier = gr.Textbox(label=bi("Supplier", "వ్యాపారి"))
                    prod_threshold = gr.Number(
                        label=bi("Reorder threshold (units)", "ఆర్డర్ హెచ్చరిక"),
                        value=2,
                    )
                    prod_price = gr.Number(label=bi("Unit cost (₹)", "ధర"), value=0)
                    save_product_btn = gr.Button(
                        bi("Save product", "వస్తువు సేవ్ చేయి"),
                        variant="primary",
                    )
                with gr.Column():
                    gr.Markdown(f"**{bi('Policies', 'నియమాలు')}**")
                    gr.Textbox(
                        label=bi("Min order value per supplier (₹)", "కనీస ఆర్డర్ విలువ"),
                        placeholder='{"Mahalakshmi Marketing": 2000, "Sri Venkateshwara": 5000}',
                        lines=3,
                    )
                    gr.Textbox(
                        label=bi("Price spike alert threshold (%)", "ధర పెరుగుదల హెచ్చరిక"),
                        placeholder="10",
                    )
                    gr.Checkbox(
                        label=bi(
                            "Auto-group POs by supplier",
                            "వ్యాపారి వారీగా ఆర్డర్లు కలపండి",
                        ),
                        value=True,
                    )
                    save_policy_btn = gr.Button(
                        bi("Save policies", "నియమాలు సేవ్ చేయి"),
                        variant="primary",
                    )

        # ── Wire events ──────────────────────────────────────────────────────

        voice_btn.click(
            fn=handle_voice,
            inputs=[audio_input],
            outputs=[telugu_heard, english_translation, trace_output],
        )

        receipt_btn.click(
            fn=handle_receipt,
            inputs=[receipt_image],
            outputs=[parsed_json, trace_output],
        )

        query_btn.click(
            fn=handle_text_query,
            inputs=[query_input],
            outputs=[trace_output, response_en, response_te],
        )

        refresh_btn.click(fn=refresh_stock, outputs=[stock_table])

        approve_btn.click(
            fn=approve_po,
            inputs=[po_id_input],
            outputs=[po_display],
        )

        reject_btn.click(
            fn=reject_po,
            inputs=[po_id_input],
            outputs=[po_display],
        )

        # Load stock on startup
        demo.load(fn=refresh_stock, outputs=[stock_table])
        demo.load(fn=get_pending_pos, outputs=[po_display])

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860)
