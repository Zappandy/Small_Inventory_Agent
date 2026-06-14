"""
LangGraph graph definition for Kirana AI.

Graph flow:
    START
      └─► load_inventory
            ├─► analyse_inventory
            ├─► seasonal_context ──► seasonal_advice
            └─► expiry_advice
                        │
                        ▼
                  generate_orders
                        │
              [if orders exist]
                        │
                        ▼
                human_approval ──► END

SLM_INTEGRATION_POINT: nodes.py contains all the stubs. Once the model
is ready, swap the rule-based logic in each node for llama.cpp calls.
"""

from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from agent.state import KiranaState
from agent.nodes import (
    node_load_inventory,
    node_seasonal_context,
    node_analyse_inventory,
    node_seasonal_advice,
    node_expiry_advice,
    node_generate_orders,
    node_human_approval,
    node_parse_command,
)


def _route_from_start(state: KiranaState) -> str:
    return "parse_command" if state.get("trigger") == "voice" else "load_inventory"


def _route_after_orders(state: KiranaState) -> str:
    if state.get("needs_human_approval") and state.get("suggested_orders"):
        return "human_approval"
    return END


def build_graph():
    g = StateGraph(KiranaState)

    g.add_node("load_inventory",    node_load_inventory)
    g.add_node("seasonal_context",  node_seasonal_context)
    g.add_node("analyse_inventory", node_analyse_inventory)
    g.add_node("seasonal_advice",   node_seasonal_advice)
    g.add_node("expiry_advice",     node_expiry_advice)
    g.add_node("generate_orders",   node_generate_orders)
    g.add_node("human_approval",    node_human_approval)
    g.add_node("parse_command",     node_parse_command)

    # Entry routing: voice commands take the standalone parse_command path;
    # everything else runs the full analysis pipeline.
    g.add_conditional_edges(
        START,
        _route_from_start,
        {"parse_command": "parse_command", "load_inventory": "load_inventory"},
    )

    # Main analysis flow — sequential to avoid parallel write conflicts on state
    g.add_edge("load_inventory",    "seasonal_context")
    g.add_edge("seasonal_context",  "seasonal_advice")
    g.add_edge("seasonal_advice",   "analyse_inventory")
    g.add_edge("analyse_inventory", "expiry_advice")
    g.add_edge("expiry_advice",     "generate_orders")

    # Order routing
    g.add_conditional_edges(
        "generate_orders",
        _route_after_orders,
        {"human_approval": "human_approval", END: END},
    )
    g.add_edge("human_approval", END)

    # Command parsing is a standalone mini-flow triggered separately
    g.add_edge("parse_command", END)

    return g.compile()


# Singleton compiled graph
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_analysis() -> KiranaState:
    """Run the full inventory analysis pipeline and return the final state."""
    graph = _get_graph()
    result = graph.invoke({"trigger": "scheduled", "errors": [], "completed_nodes": []})
    return result


def run_command_parse(text: str) -> dict:
    """Parse a single voice/text command without running full analysis."""
    graph = _get_graph()
    result = graph.invoke({
        "trigger":     "voice",
        "user_input":  text,
        "errors":      [],
        "completed_nodes": [],
    })
    return result.get("ai_parsed_command", {})
