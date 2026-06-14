from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from dukaan_saathi.agent import tools


@dataclass
class ReactResult:
    trace: list[str]
    action: dict[str, Any] | None = None
    receipt_rows: list[dict[str, Any]] | None = None
    raw_text: str | None = None


def _preview(value: Any, limit: int = 240) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


class ReceiptReActAgent:
    """
    Lean ReAct-style router for the small Dukaan Saathi task set.

    It chooses from existing safe tools, records Thought/Action/Observation
    traces, and never writes inventory. Approval functions remain outside the
    agent path.
    """

    def _trace(self) -> list[str]:
        tools.reset_state()
        return ["Thought: Identify the user workflow and select the smallest safe tool chain."]

    def parse_stock_command(self, command: str) -> ReactResult:
        trace = self._trace()
        trace.append("Thought: This is a stock command, so parse it into a pending owner action.")
        trace.append("Action: parse_stock_command_tool")
        output = tools.parse_stock_command_tool(command=command)
        action = tools.get_last_action()
        trace.append(f"Observation: {_preview(output)}")
        trace.append("Thought: Return the proposed action for owner approval; do not write inventory.")
        return ReactResult(trace=trace, action=action)

    def parse_receipt_text(self, raw_text: str) -> ReactResult:
        trace = self._trace()
        trace.append("Thought: This is receipt text, so parse it into editable receipt rows.")
        trace.append("Action: parse_receipt_text_tool")
        output = tools.parse_receipt_text_tool(raw_text=raw_text)
        rows = tools.get_last_receipt_rows() or []
        trace.append(f"Observation: {_preview(output)}")
        trace.append("Thought: Return editable rows; owner approval is required before stock changes.")
        return ReactResult(trace=trace, receipt_rows=rows)

    def extract_receipt_image(self, image_path: str) -> ReactResult:
        trace = self._trace()
        trace.append("Thought: This is a receipt image, so extract OCR text before parsing rows.")
        trace.append("Action: extract_text_from_receipt_image")
        raw_text = tools.extract_text_from_receipt_image(image_path=image_path)
        trace.append(f"Observation: {_preview(raw_text)}")

        if not raw_text.strip():
            trace.append("Thought: No OCR text was returned; caller should use the image fallback path.")
            return ReactResult(trace=trace, raw_text=raw_text, receipt_rows=[])

        trace.append("Thought: OCR text is available, so parse it into editable receipt rows.")
        trace.append("Action: parse_receipt_text_tool")
        output = tools.parse_receipt_text_tool(raw_text=raw_text)
        rows = tools.get_last_receipt_rows() or []
        trace.append(f"Observation: {_preview(output)}")
        trace.append("Thought: Return editable rows; owner approval is required before stock changes.")
        return ReactResult(trace=trace, raw_text=raw_text, receipt_rows=rows)


_react_agent: ReceiptReActAgent | None = None


def get_react_agent() -> ReceiptReActAgent:
    global _react_agent
    if _react_agent is None:
        _react_agent = ReceiptReActAgent()
    return _react_agent
