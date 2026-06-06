"""
Reporting agent node — weekly/monthly summaries and shrinkage reports.
Uses RAG: retrieves relevant stock_ledger records, then generates summary.
"""

from state import AgentState
from db.database import (
    get_weekly_summary,
    get_shrinkage_report,
    get_cost_vs_revenue,
)
from models.llm import call_llm

REPORT_SYSTEM = """You are a reporting assistant for a small Indian convenience store.
Summarize the provided inventory data clearly and concisely. Use simple English.
Include: total stock purchased (₹), estimated revenue, shrinkage %, and top 3 alerts.
Keep the response under 150 words. Do not use markdown headers."""


def reporting_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    input_text = state.get("input", "").lower()

    # Determine report type from input
    if "shrinkage" in input_text or "తేడా" in input_text:
        data = get_shrinkage_report()
        report_type = "shrinkage"
    elif "weekly" in input_text or "week" in input_text or "వారం" in input_text:
        data = get_weekly_summary()
        report_type = "weekly"
    else:
        data = get_cost_vs_revenue()
        report_type = "cost_revenue"

    trace.append(f"reporting_agent: generating {report_type} report")

    summary = call_llm(
        model="mistral-7b",
        system=REPORT_SYSTEM,
        user=str(data),
        max_tokens=300,
        json_mode=False,
    )

    trace.append("reporting_agent: report generated")

    return {**state, "response": summary, "trace": trace}
