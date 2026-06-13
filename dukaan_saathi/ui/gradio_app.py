from __future__ import annotations
from pathlib import Path

import pandas as pd
import gradio as gr

from dukaan_saathi.integrations.modal_receipt import extract_receipt_with_modal
from dukaan_saathi.integrations.speech import transcribe_audio
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
.trace-box textarea {
    font-family: monospace !important;
    font-size: 12px !important;
    background: #f8f8f6 !important;
}
.status-note {
    border-left: 4px solid #378ADD;
    padding: 10px 14px;
    background: #f8fbff;
    border-radius: 8px;
}
footer { display: none !important; }
"""

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.blue,
    neutral_hue=gr.themes.colors.gray,
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


def _run_agent(prompt: str) -> tuple[object, str]:
    from dukaan_saathi.agent import tools as agent_tools
    from dukaan_saathi.agent.agent import format_agent_trace, get_agent

    agent_tools.reset_state()
    agent = get_agent()
    result = agent.run(prompt)
    return result, format_agent_trace(agent)


def handle_parse_command(command: str):
    try:
        _, trace = _run_agent(
            f"Parse this stock command and propose an inventory update: '{command}'"
        )
        from dukaan_saathi.agent import tools as agent_tools

        action = agent_tools.get_last_action() or {}
        if action.get("status") != "pending_approval":
            raise ValueError("Agent returned no pending approval action")
    except Exception as exc:
        action, trace_list = parse_stock_command(command)
        trace = "\n".join([f"Agent unavailable; using deterministic parser: {exc}", *trace_list])
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
        _, trace = _run_agent(f"Parse this receipt text and extract all line items:\n{raw_text}")
        from dukaan_saathi.agent import tools as agent_tools

        rows = agent_tools.get_last_receipt_rows() or []
        if not rows:
            raise ValueError("Agent returned no receipt rows")
    except Exception as exc:
        rows, trace_list = parse_receipt_text(raw_text)
        trace = "\n".join([f"Agent unavailable; using deterministic parser: {exc}", *trace_list])
    df = pd.DataFrame(rows, columns=RECEIPT_COLUMNS)
    return df, trace


def handle_extract_receipt_image(image_path):
    try:
        _, trace = _run_agent(
            f"Extract items from this receipt image and propose inventory updates. "
            f"Image path: {image_path}"
        )
        from dukaan_saathi.agent import tools as agent_tools

        rows = agent_tools.get_last_receipt_rows() or []
        if not rows:
            raise ValueError("Agent returned no rows")
    except Exception as exc:
        rows, trace_list = extract_receipt_with_modal(image_path)
        trace = "\n".join([f"Agent image flow unavailable; using Modal receipt client: {exc}", *trace_list])
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
    ) as demo:
        pending_action = gr.State(None)

        gr.Markdown(
            """
            # Dukaan Saathi · దుకాణం సాథి

            <div class="status-note">
            A small-model inventory copilot MVP for a Telugu/code-mixed kirana store workflow:
            command or receipt → proposed action → owner approval → inventory update → reorder draft.
            </div>
            """
        )

        with gr.Tab(bi("Inventory", "స్టాక్")):
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
                Try:
                - `Bingo అయిపోయింది`
                - `add Thums Up 12`
                - `Lays Classic low`
                - `Parle-G 100g stock 5`
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

        with gr.Tab(bi("Receipt import", "బిల్ ఇంపోర్ట్")):
            gr.Markdown(
                """
                Use either path:
                1. Load/paste receipt text for the deterministic MVP parser.
                2. Upload a receipt image and extract it with the model endpoint.
                In both cases, extracted rows are editable and require owner approval before inventory changes.
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
                Drafts a purchase order from inventory thresholds. Nothing is sent automatically.
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

        demo.load(fn=inventory_df, outputs=inventory_table)

    return demo
