"""
LangGraph graph definition.

Topology:
    orchestrator
        ├─(receipt_parse)──► receipt_parser ──► inventory_manager ──► po_check
        ├─(reorder_trigger)─► inventory_manager ──► reorder_agent ──► po_check
        ├─(sales_log)───────► inventory_manager ──► END
        ├─(stock_query)─────► inventory_manager ──► END
        └─(report)──────────► reporting_agent ──► END

po_check:
    if po_draft exists → HITL pause node (streams draft to UI, waits)
    else              → END
"""

from langgraph.graph import StateGraph, END

from state import AgentState
from orchestrator import orchestrator_node
from receipt_parser import receipt_parser_node
from inventory_manager import inventory_manager_node
from reorder_agent import reorder_agent_node
from reporting_agent import reporting_agent_node
from po_check import po_check_node


def route_from_orchestrator(state: AgentState) -> str:
    """Conditional edge: orchestrator → sub-agent based on classified intent."""
    intent: str = state.get("intent") or "stock_query"
    routes = {
        "receipt_parse":    "receipt_parser",
        "reorder_trigger":  "inventory_manager",
        "sales_log":        "inventory_manager",
        "stock_query":      "inventory_manager",
        "report":           "reporting_agent",
    }
    return routes.get(intent, "inventory_manager")


def route_after_inventory(state: AgentState) -> str:
    """After inventory manager: go to reorder if that was the intent."""
    intent: str = state.get("intent") or "stock_query"
    if intent in ("reorder_trigger", "receipt_parse"):
        return "reorder_agent"
    return "po_check"


def route_po_check(state: AgentState) -> str:
    """If a PO draft exists, surface it; otherwise finish."""
    if state.get("po_draft"):
        return "po_check"
    return END


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("orchestrator",      orchestrator_node)
    g.add_node("receipt_parser",    receipt_parser_node)
    g.add_node("inventory_manager", inventory_manager_node)
    g.add_node("reorder_agent",     reorder_agent_node)
    g.add_node("reporting_agent",   reporting_agent_node)
    g.add_node("po_check",          po_check_node)

    # Entry point
    g.set_entry_point("orchestrator")

    # Orchestrator → sub-agents (conditional)
    g.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "receipt_parser":    "receipt_parser",
            "inventory_manager": "inventory_manager",
            "reporting_agent":   "reporting_agent",
        },
    )

    # Receipt parser always feeds inventory manager
    g.add_edge("receipt_parser", "inventory_manager")

    # Inventory manager branches
    g.add_conditional_edges(
        "inventory_manager",
        route_after_inventory,
        {
            "reorder_agent": "reorder_agent",
            "po_check":      "po_check",
        },
    )

    # Reorder agent → po_check
    g.add_edge("reorder_agent", "po_check")

    # Reporting agent → END
    g.add_edge("reporting_agent", END)

    # po_check → END (HITL pause is handled inside the node)
    g.add_edge("po_check", END)

    return g.compile()
