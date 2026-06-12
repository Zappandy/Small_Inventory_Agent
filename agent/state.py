"""
LangGraph agent state for Kirana AI.

Every node reads from and writes to KiranaState.
The SLM (Small Language Model) will be plugged into nodes that currently
return rule-based or stub responses — search for SLM_INTEGRATION_POINT.
"""

from __future__ import annotations
import operator
from typing import Annotated, Any
from typing_extensions import TypedDict


class KiranaState(TypedDict, total=False):
    # ── Trigger ───────────────────────────────────────────────────────────────
    trigger: str                    # "scheduled" | "voice" | "photo" | "manual"
    user_input: str                 # raw text from voice or manual input

    # ── Inventory snapshot ───────────────────────────────────────────────────
    all_products: list[dict]
    low_stock_items: list[dict]
    expiring_items: list[dict]
    expired_items: list[dict]
    top_sellers: list[dict]
    summary: dict                   # totals from get_summary()

    # ── Seasonal context ─────────────────────────────────────────────────────
    seasonal_summary: str           # plain-text for SLM prompt
    upcoming_festivals: list[dict]

    # ── Vision results ───────────────────────────────────────────────────────
    vision_result: dict             # output of vision_handler.analyse_image()

    # ── SLM outputs ──────────────────────────────────────────────────────────
    ai_inventory_analysis: str      # narrative inventory advice
    ai_seasonal_advice: str         # festival stocking narrative
    ai_expiry_advice: str           # liquidation suggestions for expiring stock
    ai_parsed_command: dict         # structured parse of voice/text command

    # ── Orders ───────────────────────────────────────────────────────────────
    suggested_orders: list[dict]    # [{product_name, qty_needed, unit, reason, confidence}]
    needs_human_approval: bool

    # ── Errors / meta ────────────────────────────────────────────────────────
    # Annotated with operator.add so parallel nodes can safely append to these lists
    errors:          Annotated[list[str], operator.add]
    completed_nodes: Annotated[list[str], operator.add]
