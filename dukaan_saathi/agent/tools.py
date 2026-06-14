"""
tools.py — smolagents @tool definitions for Dukaan Saathi.

Each tool wraps an existing service/parser function and returns a JSON string
so the active ReAct router or optional ToolCallingAgent can reason over results.

Results are also stored in _state so Gradio handlers can access structured data
after agent.run() without having to parse agent.logs internals.
"""

from __future__ import annotations

import json
from typing import Any

from smolagents import tool

# Shared session state — stores last structured result from each tool.
# Single-user app (kirana owner's phone), so no concurrency concern.
_state: dict[str, Any] = {
    "last_action": None,
    "last_proposal": None,
    "last_receipt_rows": None,
    "last_raw_text": None,
}


def reset_state() -> None:
    _state.update(
        {
            "last_action": None,
            "last_proposal": None,
            "last_receipt_rows": None,
            "last_raw_text": None,
        }
    )


def get_last_action() -> dict | None:
    return _state.get("last_action")


def get_last_proposal() -> Any:
    return _state.get("last_proposal")


def get_last_receipt_rows() -> list[dict] | None:
    return _state.get("last_receipt_rows")


def get_last_raw_text() -> str | None:
    return _state.get("last_raw_text")


# ── Read-only tools ────────────────────────────────────────────────────────────

@tool
def get_inventory_snapshot() -> str:
    """Returns the current inventory of the kirana store as a JSON string.

    Use this before proposing any inventory changes.
    """
    from dukaan_saathi.storage import get_inventory
    items = get_inventory()
    return json.dumps(items)


@tool
def draft_reorder_tool() -> str:
    """Generates a reorder purchase-order draft based on current low-stock items.

    Returns a JSON list of suggested orders.
    """
    from dukaan_saathi.services.reorder import draft_reorder
    rows, _ = draft_reorder()
    return json.dumps(rows)


# ── Parsing tools ──────────────────────────────────────────────────────────────

@tool
def parse_stock_command_tool(command: str) -> str:
    """Parse a natural language stock command (Telugu/English code-mixed) into a
    proposed inventory action. Input examples: "add Bun 12",
    "set OBM stock 5", "Happy Happy low". Returns a JSON action dict.

    Args:
        command: The owner's raw stock command text.
    """
    from dukaan_saathi.parsers.stock_command import parse_stock_command
    action, _ = parse_stock_command(command)
    _state["last_action"] = action
    return json.dumps(action)


@tool
def extract_text_from_receipt_image(image_path: str) -> str:
    """Extract raw OCR text from a receipt image using MiniCPM-V 4.6 on the Modal
    endpoint. Returns the raw pipe-separated text output from the vision model.
    Must be followed by parse_receipt_text_tool to get structured rows.

    Args:
        image_path: Local filesystem path to the uploaded receipt image.
    """
    from dukaan_saathi.integrations.modal_receipt import _extract_receipt_result_with_modal
    result = _extract_receipt_result_with_modal(image_path)
    raw_text = result.raw_text or ""
    _state["last_raw_text"] = raw_text
    return raw_text


@tool
def parse_receipt_text_tool(raw_text: str) -> str:
    """Parse OCR receipt text into structured line items. Uses the configured
    receipt backend: HF Inference API, local llama.cpp, Modal-hosted LLM, or deterministic parser.
    Returns a JSON list of row dicts with fields: product_raw,
    matched_product_name, quantity, unit_price, total_price.

    Args:
        raw_text: Receipt OCR text or pasted receipt text to parse.
    """
    from dukaan_saathi import config
    if config.RECEIPT_BACKEND == "hf_inference":
        from dukaan_saathi.integrations.hf_inference_receipt import parse_receipt_via_hf_inference
        rows, _ = parse_receipt_via_hf_inference(raw_text)
    elif config.RECEIPT_BACKEND == "llamacpp":
        from dukaan_saathi.integrations.llamacpp_receipt import parse_receipt_via_llm
        rows, _ = parse_receipt_via_llm(raw_text)
    elif config.RECEIPT_BACKEND == "modal_llm":
        from dukaan_saathi.integrations.modal_receipt_llm import parse_receipt_with_modal_llm
        rows, _ = parse_receipt_with_modal_llm(raw_text)
    else:
        from dukaan_saathi.parsers.receipt_text import parse_receipt_text
        rows, _ = parse_receipt_text(raw_text)
    _state["last_receipt_rows"] = rows
    return json.dumps(rows)


@tool
def apply_correction_to_receipt(rows_json: str, correction_command: str) -> str:
    """Apply a human correction command to receipt rows. Correction examples:
    "first one Parle bulk, second one Bingo", "skip row 3", "row 2 quantity 10".
    Returns updated rows as JSON.

    Args:
        rows_json: JSON array of editable receipt row dictionaries.
        correction_command: Owner's typed correction command.
    """
    from dukaan_saathi.parsers.receipt_correction import apply_receipt_correction_command
    rows = json.loads(rows_json)
    updated_rows, _ = apply_receipt_correction_command(rows, correction_command)
    _state["last_receipt_rows"] = updated_rows
    return json.dumps(updated_rows)


@tool
def transcribe_audio_tool(audio_path: str) -> str:
    """Transcribe a correction audio recording to text using Distil-Whisper via
    the Modal ASR endpoint. Returns the transcription string.

    Args:
        audio_path: Local filesystem path to the audio file.
    """
    from dukaan_saathi.integrations.speech import transcribe_audio
    transcript, _ = transcribe_audio(audio_path)
    return transcript


# ── Proposal tool (write-gate) ─────────────────────────────────────────────────

@tool
def propose_inventory_update(changes_json: str) -> str:
    """Propose inventory changes for human review. This tool does NOT write to the
    database — it formats the proposed changes and returns them for display.
    The owner must click the Approve button in the UI to apply the changes.

    Args:
        changes_json: JSON object or array describing proposed inventory changes.
    """
    try:
        changes = json.loads(changes_json)
        _state["last_proposal"] = changes
        if isinstance(changes, dict) and changes.get("status") == "pending_approval":
            _state["last_action"] = changes
        lines = [
            "Proposed inventory update (pending owner approval):",
            json.dumps(changes, indent=2, ensure_ascii=False),
        ]
        return "\n".join(lines)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"Could not format proposal: {exc}\nRaw: {changes_json}"
