"""
Shared state object threaded through every LangGraph node.
All fields are Optional so nodes only populate what they produce.
"""

from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # Raw input from voice / receipt / text
    input: str
    source: str                  # "voice" | "receipt" | "query"

    # Intent classified by orchestrator
    intent: Optional[str]        # "receipt_parse" | "reorder_trigger" |
                                 # "sales_log" | "stock_query" | "report"

    # Structured data produced by receipt parser or inventory manager
    structured_data: Optional[dict]

    # Draft purchase order waiting for HITL approval
    po_draft: Optional[dict]

    # Final natural-language response (English; translated to Telugu in UI)
    response: Optional[str]

    # Step-by-step trace accumulated across nodes
    trace: list[str]

    # Policy rules injected by orchestrator before routing
    active_policies: Optional[dict]

    # Alias resolution result from vector DB lookup
    resolved_aliases: Optional[dict]
