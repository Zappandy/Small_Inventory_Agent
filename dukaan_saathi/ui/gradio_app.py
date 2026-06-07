from __future__ import annotations

import pandas as pd
import gradio as gr

from dukaan_saathi.parsers.receipt_text import parse_receipt_text
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


def bi(en: str, te: str) -> str:
    return f"{en} · {te}"


def inventory_df() -> pd.DataFrame:
    return pd.DataFrame(get_inventory(), columns=INVENTORY_COLUMNS)


def empty_receipt_df() -> pd.DataFrame:
    return pd.DataFrame(columns=RECEIPT_COLUMNS)


def empty_reorder_df() -> pd.DataFrame:
    return pd.DataFrame(columns=REORDER_COLUMNS)


def handle_parse_command(command: str):
    action, trace = parse_stock_command(command)
    return action, "\n".join(trace), action


def handle_approve_command(action):
    message, trace = approve_command_action(action)
    return inventory_df(), message, "\n".join(trace), None


def handle_parse_receipt(image, raw_text: str):
    if image is not None and not raw_text.strip():
        trace = [
            "Receipt image received.",
            "MVP note: OCR/VLM is not connected yet.",
            "Paste OCR text manually for now; Modal VLM will replace this step later.",
        ]
        return empty_receipt_df(), "\n".join(trace)

    rows, trace = parse_receipt_text(raw_text)
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
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.gray,
        ),
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
                v0 uses pasted receipt text. Uploading an image is included so the UI already matches the final workflow.
                Next step: replace pasted text with Modal-hosted OCR/VLM extraction.
                """
            )

            with gr.Row():
                receipt_image = gr.Image(
                    label=bi("Receipt image", "బిల్ ఫోటో"),
                    type="pil",
                    sources=["upload", "webcam"],
                )
                receipt_text = gr.Textbox(
                    label=bi("Receipt text / OCR text", "బిల్ టెక్స్ట్"),
                    value=SAMPLE_RECEIPT,
                    lines=10,
                )

            parse_receipt_btn = gr.Button(bi("Parse receipt", "బిల్ చదవు"), variant="primary")
            receipt_table = gr.Dataframe(
                value=empty_receipt_df,
                headers=RECEIPT_COLUMNS,
                interactive=True,
                wrap=True,
                label=bi("Editable extracted receipt rows", "సవరించగలిగే బిల్ వరుసలు"),
            )
            receipt_trace = gr.Textbox(
                label=bi("Receipt trace", "బిల్ ట్రేస్"),
                lines=10,
                elem_classes=["trace-box"],
            )
            approve_receipt_btn = gr.Button(
                bi("Approve receipt import", "బిల్ ఇంపోర్ట్ ఆమోదించు"),
                variant="primary",
            )
            receipt_result = gr.Textbox(label=bi("Approval result", "ఫలితం"))

            parse_receipt_btn.click(
                fn=handle_parse_receipt,
                inputs=[receipt_image, receipt_text],
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
