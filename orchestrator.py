"""
Orchestrator node.

Responsibilities:
1. Classify the intent of the (already English) input
2. Load relevant policy rules from SQLite
3. Resolve any product aliases via ChromaDB fuzzy match
4. Inject both into state before routing

Uses Llama-3.2-3B-Instruct via llama.cpp for fast intent classification.
Structured output enforced via JSON mode.
"""

import json
import logging
from state import AgentState
from db.database import get_policies
from db.vector_store import resolve_aliases
from models.llm import call_llm

logger = logging.getLogger(__name__)

ORCHESTRATOR_SYSTEM = """You are an inventory management orchestrator for a small
Indian convenience store in Hyderabad. Your job is to classify the user's intent
and extract key entities. Always respond with valid JSON only, no markdown.

Valid intents:
- receipt_parse   : user uploaded or described a supplier receipt
- reorder_trigger : user says something is out of stock or wants to reorder
- sales_log       : user is recording what was sold today
- stock_query     : user wants to know current stock levels
- report          : user wants a weekly/monthly report or shrinkage analysis

Respond with:
{
  "intent": "<one of the above>",
  "entities": {
    "products": ["<product name>", ...],
    "supplier": "<supplier name or null>",
    "quantities": {"<product>": <number>, ...}
  },
  "confidence": 0.0–1.0
}"""


def orchestrator_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    input_text = state.get("input", "")

    # 1. Classify intent via LLM
    raw = call_llm(
        model="llama-3.2-3b",
        system=ORCHESTRATOR_SYSTEM,
        user=input_text,
        max_tokens=256,
        json_mode=True,
    )

    try:
        parsed = json.loads(raw)
        intent = parsed.get("intent", "stock_query")
        entities = parsed.get("entities", {})
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Orchestrator JSON parse failed, defaulting to stock_query")
        intent = "stock_query"
        entities = {}

    trace.append(f"orchestrator: intent={intent} confidence={parsed.get('confidence', '?')}")

    # 2. Load policies from SQLite
    policies = get_policies()
    trace.append(f"orchestrator: loaded {len(policies)} policy rules")

    # 3. Resolve product aliases via ChromaDB
    product_mentions = entities.get("products", [])
    resolved = {}
    if product_mentions:
        resolved = resolve_aliases(product_mentions)
        trace.append(f"orchestrator: alias resolved {resolved}")

    return {
        **state,
        "intent": intent,
        "active_policies": policies,
        "resolved_aliases": resolved,
        "trace": trace,
    }
