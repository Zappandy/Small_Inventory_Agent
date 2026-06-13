"""
agent.py — legacy smolagents ToolCallingAgent for Dukaan Saathi.

The active Gradio path uses dukaan_saathi.agent.react_agent. This module is kept
as an optional heavier agent implementation for experiments with model-driven
tool calling.

The agent proposes actions but never writes to the inventory database directly —
all writes go through the Gradio approval step (approve_command_action /
approve_receipt_rows called outside the agent loop).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from smolagents import ToolCallingAgent, OpenAIServerModel

from dukaan_saathi import config
from dukaan_saathi.agent.tools import (
    get_inventory_snapshot,
    parse_stock_command_tool,
    extract_text_from_receipt_image,
    parse_receipt_text_tool,
    apply_correction_to_receipt,
    transcribe_audio_tool,
    draft_reorder_tool,
    propose_inventory_update,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Dukaan Saathi, an inventory assistant for a Telugu-speaking kirana (convenience store) owner.

Your job:
1. Understand the owner's request (stock commands in Telugu/English, receipt photos, reorder drafts).
2. Call the appropriate tools to parse and structure the data.
3. Always call propose_inventory_update before finishing — the owner must approve before any changes are written.

Rules:
- Never write to the inventory database directly. Only propose.
- If a stock command is unclear, ask for clarification rather than guessing.
- For receipt parsing: first extract text with extract_text_from_receipt_image, then parse with parse_receipt_text_tool.
- Respond concisely in English (the owner reads English labels even if they speak Telugu).
"""


def _build_agent() -> ToolCallingAgent:
    model = OpenAIServerModel(
        model_id="llama-3.2-3b",
        api_base=f"{config.LLAMACPP_HOST}:8080/v1",
        api_key="none",
    )
    return ToolCallingAgent(
        tools=[
            get_inventory_snapshot,
            parse_stock_command_tool,
            extract_text_from_receipt_image,
            parse_receipt_text_tool,
            apply_correction_to_receipt,
            transcribe_audio_tool,
            draft_reorder_tool,
            propose_inventory_update,
        ],
        model=model,
        system_prompt=SYSTEM_PROMPT,
        max_steps=6,
    )


# Module-level agent instance — created once at import.
# Re-create if the llama.cpp server wasn't up on first import.
_agent: ToolCallingAgent | None = None


def get_agent() -> ToolCallingAgent:
    """Return the module-level agent, building it on first call."""
    global _agent
    if _agent is None:
        try:
            _agent = _build_agent()
        except Exception as exc:
            logger.warning(f"Could not build agent (llama.cpp not running?): {exc}")
            raise
    return _agent


def format_agent_trace(agent: ToolCallingAgent) -> str:
    """Format agent.logs into a human-readable trace string for the UI."""
    lines: list[str] = []
    for step in agent.logs:
        step_str = str(step)
        if step_str.strip():
            lines.append(step_str)
    return "\n\n".join(lines) if lines else "(no agent trace)"
