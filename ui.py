"""
Kirana AI — UI renderer.
Loads Jinja2 templates and builds the per-page context from database state.
"""

import datetime
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import os

import kirana_db as db
from seasonal_calendar import (
    get_upcoming_festivals,
    get_seasonal_context,
    build_seasonal_summary,
)


def is_model_available() -> bool:
    return bool(os.getenv("MODAL_RECEIPT_ENDPOINT", "").strip())

# ──────────────────────────────────────────────────────────────────────────────
TEMPLATES_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# SVG icon library  (1.6px stroke, rounded — SF Symbols-inspired)
# ──────────────────────────────────────────────────────────────────────────────
def _svg(body: str, size: int = 18) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )

ICON = {
    "dashboard": _svg('<rect x="3" y="3" width="7" height="9" rx="1.5"/>'
                      '<rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                      '<rect x="14" y="12" width="7" height="9" rx="1.5"/>'
                      '<rect x="3" y="16" width="7" height="5" rx="1.5"/>'),
    "inventory": _svg('<path d="M3 7l9-4 9 4-9 4-9-4z"/>'
                      '<path d="M3 7v10l9 4 9-4V7"/>'
                      '<path d="M12 11v10"/>'),
    "add":       _svg('<circle cx="12" cy="12" r="9"/>'
                      '<path d="M12 8v8M8 12h8"/>'),
    "orders":    _svg('<path d="M9 4h6a2 2 0 012 2v0H7v0a2 2 0 012-2z"/>'
                      '<rect x="5" y="6" width="14" height="15" rx="2"/>'
                      '<path d="M9 12l2 2 4-4"/>'),
    "analytics": _svg('<path d="M3 21h18"/>'
                      '<rect x="5"  y="13" width="3" height="6" rx="1"/>'
                      '<rect x="10.5" y="9"  width="3" height="10" rx="1"/>'
                      '<rect x="16" y="5"  width="3" height="14" rx="1"/>'),
    "seasonal":  _svg('<rect x="3" y="5" width="18" height="16" rx="2"/>'
                      '<path d="M3 9h18M8 3v4M16 3v4"/>'
                      '<circle cx="12" cy="14" r="1.6" fill="currentColor"/>'),
    "settings":  _svg('<circle cx="12" cy="12" r="3"/>'
                      '<path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.6 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.6-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>'),
    "play":      _svg('<polygon points="6 4 20 12 6 20" fill="currentColor" stroke="none"/>', 14),
    "refresh":   _svg('<path d="M21 12a9 9 0 11-3-6.7"/><path d="M21 4v5h-5"/>', 14),
    "sparkles":  _svg('<path d="M12 3l1.8 4.4L18 9l-4.2 1.6L12 15l-1.8-4.4L6 9l4.2-1.6L12 3z"/>'
                      '<path d="M19 14l.8 1.7L21 17l-1.2.8L19 19l-.8-1.2L17 17l1.2-1L19 14z"/>', 14),
    "plus":      _svg('<path d="M12 5v14M5 12h14"/>', 14),
    "edit":      _svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 113 3L7 19l-4 1 1-4z"/>'),
    "rupee":     _svg('<path d="M6 4h12M6 8h12M9 13c4 0 6-2 6-4M6 13h2.5L15 20"/>'),
    "trash":     _svg('<path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>'
                      '<path d="M5 6l1 14a2 2 0 002 2h8a2 2 0 002-2l1-14"/>'),
    "search":    _svg('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>'),
    "filter":    _svg('<path d="M3 5h18l-7 9v6l-4-2v-4z"/>'),
    "mic":       _svg('<rect x="9" y="3" width="6" height="12" rx="3"/>'
                      '<path d="M5 11a7 7 0 0014 0M12 18v4M9 22h6"/>'),
    "camera":    _svg('<path d="M3 8h3l2-3h8l2 3h3a1 1 0 011 1v10a2 2 0 01-2 2H4a2 2 0 01-2-2V9a1 1 0 011-1z"/>'
                      '<circle cx="12" cy="13" r="4"/>'),
    "check":     _svg('<path d="M5 12l5 5L20 7"/>', 14),
    "x":         _svg('<path d="M6 6l12 12M18 6L6 18"/>', 14),
    "package":   _svg('<path d="M3 7l9-4 9 4-9 4-9-4z"/>'
                      '<path d="M3 7v10l9 4 9-4V7"/>'),
    "alert":     _svg('<path d="M12 2L1 21h22L12 2z"/><path d="M12 9v5M12 17v.5"/>'),
    "clock":     _svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    "trend":     _svg('<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'),
    "trophy":    _svg('<path d="M8 4h8v4a4 4 0 11-8 0V4z"/>'
                      '<path d="M16 4h3v2a3 3 0 01-3 3M8 4H5v2a3 3 0 003 3M10 13h4l1 5H9z"/>'),
    "store":     _svg('<path d="M3 9l1.5-5h15L21 9"/>'
                      '<path d="M3 9v11a1 1 0 001 1h16a1 1 0 001-1V9"/>'
                      '<path d="M3 9a3 3 0 006 0M9 9a3 3 0 006 0M15 9a3 3 0 006 0"/>'
                      '<rect x="9" y="13" width="6" height="8"/>'),
    "info":      _svg('<circle cx="12" cy="12" r="9"/><path d="M12 8v.01M11 12h1v5h1"/>'),
    "pulse":     _svg('<path d="M3 12h4l3-8 4 16 3-8h4"/>'),
    "shipped":   _svg('<path d="M3 7h11v10H3z"/><path d="M14 10h5l2 3v4h-7"/>'
                      '<circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>'),
    "medal":     _svg('<circle cx="12" cy="14" r="6"/>'
                      '<path d="M8 8L6 2h4l2 4M16 8l2-6h-4l-2 4"/>'),
    "bell":      _svg('<path d="M6 8a6 6 0 1112 0v5l2 3H4l2-3V8z"/>'
                      '<path d="M10 20a2 2 0 004 0"/>'),
    "sun":       _svg('<circle cx="12" cy="12" r="4"/>'
                      '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', 16),
    "moon":      _svg('<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>', 16),
}

LOGO_SVG = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
    'stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 9l1.5-5h15L21 9"/>'
    '<path d="M3 9v11a1 1 0 001 1h16a1 1 0 001-1V9"/>'
    '<path d="M3 9a3 3 0 006 0M9 9a3 3 0 006 0M15 9a3 3 0 006 0"/>'
    '<rect x="9" y="13" width="6" height="8"/>'
    '</svg>'
)


# ──────────────────────────────────────────────────────────────────────────────
# Navigation definition
# ──────────────────────────────────────────────────────────────────────────────
NAV_PAGES = [
    {"key": "dashboard", "label": "Overview",    "icon": ICON["dashboard"], "title": "Overview",
     "subtitle": "Real-time snapshot of your store"},
    {"key": "inventory", "label": "Inventory",   "icon": ICON["inventory"], "title": "Inventory",
     "subtitle": "Browse, search, and update your full stock"},
    {"key": "add",       "label": "Add Product", "icon": ICON["add"],       "title": "Add Product",
     "subtitle": "Photo, voice, or manual entry"},
    {"key": "orders",    "label": "Orders",      "icon": ICON["orders"],    "title": "Restock Orders",
     "subtitle": "AI-suggested orders awaiting your approval"},
    {"key": "analytics", "label": "Analytics",   "icon": ICON["analytics"], "title": "Analytics",
     "subtitle": "Category mix and best-selling products"},
    {"key": "seasonal",  "label": "Seasonal",    "icon": ICON["seasonal"],  "title": "Seasonal Forecast",
     "subtitle": "Upcoming festivals and demand spikes"},
    {"key": "settings",  "label": "Settings",    "icon": ICON["settings"],  "title": "Settings",
     "subtitle": "Shop info, thresholds, model status"},
]

STATUS_FILTERS = ["All", "OK", "Low Stock", "Expiring", "Expired"]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _status_of(p: dict) -> tuple[str, str, str]:
    """Return (label, kind, raw_key) for a product."""
    today = datetime.date.today().isoformat()
    week = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    exp = p.get("expiry_date") or ""
    if exp and exp < today:
        return "Expired", "danger", "Expired"
    if exp and exp <= week:
        return "Expiring", "warn", "Expiring"
    if (p.get("quantity") or 0) <= (p.get("min_stock") or 0):
        return "Low", "warn", "Low Stock"
    return "OK", "success", "OK"


def _nav_with_badges() -> list[dict]:
    s = db.get_summary()
    badges = {
        "dashboard": s.get("low_stock", 0) or 0,
        "orders":    len(db.get_pending_orders()),
    }
    result = []
    for item in NAV_PAGES:
        copy = dict(item)
        n = badges.get(item["key"], 0)
        if n:
            copy["badge"] = n
            copy["badge_kind"] = "warn"
        result.append(copy)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Page builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_kpis() -> list[dict]:
    s = db.get_summary()
    total = s.get("total", 0) or 0
    low   = s.get("low_stock", 0) or 0
    expd  = s.get("expired", 0) or 0
    exp7  = s.get("expiring_soon", 0) or 0
    val   = s.get("total_value", 0) or 0
    cost  = s.get("cost_value", 0) or 0
    margin = val - cost
    needs = expd + exp7
    if expd and exp7:
        needs_foot = f"{expd} expired · {exp7} expiring 7d"
    elif expd:
        needs_foot = f"{expd} expired, clear today"
    elif exp7:
        needs_foot = f"{exp7} expiring within 7 days"
    else:
        needs_foot = "Nothing on the clock"
    return [
        {"label": "Products",         "value": total,          "icon": ICON["package"], "color": "primary",
         "foot": "across all categories"},
        {"label": "Low stock",        "value": low,            "icon": ICON["trend"],   "color": "warn" if low else "success",
         "foot": f"{low} need restocking" if low else "All stocked"},
        {"label": "Needs attention",  "value": needs,          "icon": ICON["alert"],   "color": "danger" if expd else ("warn" if exp7 else "success"),
         "foot": needs_foot},
        {"label": "Inventory value",  "value": f"₹{val:,.0f}", "icon": ICON["rupee"],   "color": "info",
         "foot": f"Margin ≈ ₹{margin:,.0f}"},
    ]


def _build_health() -> dict:
    products = db.get_all_products()
    today = datetime.date.today().isoformat()
    week  = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    healthy = low = expiring = expired = 0
    for p in products:
        exp = p.get("expiry_date") or ""
        if exp and exp < today: expired += 1
        elif exp and exp <= week: expiring += 1
        elif (p["quantity"] or 0) <= (p["min_stock"] or 0): low += 1
        else: healthy += 1
    total = max(len(products), 1)
    def pct(n): return max(round((n / total) * 100, 1), 2 if n else 1)
    return {
        "total": len(products),
        "segments": [
            {"label": "Healthy",  "value": healthy,  "cls": "healthy",  "flex": pct(healthy)},
            {"label": "Low",      "value": low,      "cls": "low",      "flex": pct(low)},
            {"label": "Expiring", "value": expiring, "cls": "expiring", "flex": pct(expiring)},
            {"label": "Expired",  "value": expired,  "cls": "expired",  "flex": pct(expired)},
        ],
    }


def _build_alerts() -> dict:
    low_items   = db.get_low_stock()
    expir_items = db.get_expiring_soon(7)
    expd_items  = db.get_expired()

    n_expd, n_exp7, n_low = len(expd_items), len(expir_items), len(low_items)
    total = n_expd + n_exp7 + n_low

    chips = [
        {"label": "Expired",      "value": n_expd, "kind": "danger"},
        {"label": "Expiring 7d",  "value": n_exp7, "kind": "warn"},
        {"label": "Low stock",    "value": n_low,  "kind": "warn"},
    ]

    # Top 3 most urgent: expired first, then soonest expiry, then lowest %-of-min
    top = []
    for p in expd_items[:3]:
        top.append({
            "kind": "danger", "icon": "🚨", "tag": "EXPIRED",
            "title": p["name"],
            "sub": f"{p['quantity']} {p['unit']} · Expired {p['expiry_date']}",
        })
    if len(top) < 3:
        for p in expir_items[: 3 - len(top)]:
            days = (datetime.date.fromisoformat(p["expiry_date"]) - datetime.date.today()).days
            top.append({
                "kind": "warn", "icon": "⏰", "tag": f"{days}d LEFT",
                "title": p["name"],
                "sub": f"{p['quantity']} {p['unit']} · Expires {p['expiry_date']}",
            })
    if len(top) < 3:
        for p in low_items[: 3 - len(top)]:
            pct = int((p["quantity"] / max(p["min_stock"], 0.01)) * 100)
            top.append({
                "kind": "warn", "icon": "📉", "tag": "LOW",
                "title": p["name"],
                "sub": f"{p['quantity']} {p['unit']} ({pct}% of min {p['min_stock']}) · {p['supplier'] or '—'}",
            })

    overflow = max(total - len(top), 0)
    badge_cls = ("badge-danger" if expd_items else
                 "badge-warn" if (low_items or expir_items) else "badge-success")
    return {
        "chips": chips,
        "top": top,
        "overflow": overflow,
        "total": total,
        "badge_cls": badge_cls,
        # back-compat alias for any template still reading `.entries`
        "entries": top,
    }


def _build_festivals() -> dict:
    ctx = get_seasonal_context()
    upcoming = get_upcoming_festivals(30)
    cards = [{
        "name": f["name"], "name_te": f["name_te"],
        "mult": f["demand_multiplier"],
        "demand_items": ", ".join(f["demand_items"][:6]),
        "tips": f["tips"],
    } for f in upcoming[:6]]
    return {
        "season": ctx["season"], "note": ctx["note"],
        "cards": cards, "count": len(upcoming),
    }


def _build_pulse(days: int = 14) -> dict:
    """Daily revenue series for the dashboard hero sparkline.

    Returns a path-ready SVG polyline + area, indexed counts, peak/avg
    summary, and a "today vs prior-week" delta so the viz can pulse and
    label itself without any client-side math.
    """
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT date(sale_date) AS d, "
        "       COALESCE(SUM(qty_sold * price_per_unit), 0) AS rev, "
        "       COALESCE(SUM(qty_sold), 0) AS units "
        "FROM sales WHERE sale_date >= date('now', ?) "
        "GROUP BY date(sale_date)",
        (f"-{days - 1} days",),
    ).fetchall()
    conn.close()

    by_day = {r["d"]: (float(r["rev"] or 0), float(r["units"] or 0)) for r in rows}
    today = datetime.date.today()
    series: list[dict] = []
    for i in range(days):
        d = today - datetime.timedelta(days=days - 1 - i)
        rev, units = by_day.get(d.isoformat(), (0.0, 0.0))
        series.append({
            "date": d.isoformat(),
            "label": d.strftime("%a"),
            "rev": rev, "units": units,
        })

    revs = [pt["rev"] for pt in series]
    peak = max(revs) if revs else 0
    total = sum(revs)
    avg = total / max(len(revs), 1)
    today_rev = revs[-1] if revs else 0
    prior_week = sum(revs[:7])  # days 1..7 of the 14-day window
    last_week = sum(revs[7:])   # days 8..14
    if prior_week > 0:
        delta_pct = round(((last_week - prior_week) / prior_week) * 100, 1)
    else:
        delta_pct = 100.0 if last_week else 0.0

    # SVG path generation — 100-wide × 36-tall normalized viewBox
    W, H, PAD = 100.0, 36.0, 2.0
    n = len(series)
    if n < 2 or peak <= 0:
        line_path = f"M{PAD},{H - PAD}L{W - PAD},{H - PAD}"
        area_path = (f"M{PAD},{H - PAD}L{W - PAD},{H - PAD}"
                     f"L{W - PAD},{H}L{PAD},{H}Z")
        points = []
    else:
        step = (W - PAD * 2) / (n - 1)
        coords = []
        for i, pt in enumerate(series):
            x = PAD + step * i
            y = (H - PAD) - (pt["rev"] / peak) * (H - PAD * 2)
            coords.append((x, y))
        # Smooth Catmull-Rom-ish path via Bezier
        def _seg(p0, p1, p2, p3):
            t = 0.18
            c1x = p1[0] + (p2[0] - p0[0]) * t
            c1y = p1[1] + (p2[1] - p0[1]) * t
            c2x = p2[0] - (p3[0] - p1[0]) * t
            c2y = p2[1] - (p3[1] - p1[1]) * t
            return f" C{c1x:.2f},{c1y:.2f} {c2x:.2f},{c2y:.2f} {p2[0]:.2f},{p2[1]:.2f}"
        parts = [f"M{coords[0][0]:.2f},{coords[0][1]:.2f}"]
        for i in range(len(coords) - 1):
            p0 = coords[i - 1] if i > 0 else coords[i]
            p1 = coords[i]
            p2 = coords[i + 1]
            p3 = coords[i + 2] if i + 2 < len(coords) else coords[i + 1]
            parts.append(_seg(p0, p1, p2, p3))
        line_path = "".join(parts)
        area_path = (line_path
                     + f"L{coords[-1][0]:.2f},{H}L{coords[0][0]:.2f},{H}Z")
        points = [{
            "x": round(x, 2), "y": round(y, 2),
            "rev": pt["rev"], "label": pt["label"], "date": pt["date"],
        } for (x, y), pt in zip(coords, series)]

    return {
        "series":    series,
        "points":    points,
        "line_path": line_path,
        "area_path": area_path,
        "viewbox":   f"0 0 {int(W)} {int(H)}",
        "today_rev_fmt": f"₹{today_rev:,.0f}",
        "avg_rev_fmt":   f"₹{avg:,.0f}",
        "peak_rev_fmt":  f"₹{peak:,.0f}",
        "total_rev_fmt": f"₹{total:,.0f}",
        "delta_pct":     delta_pct,
        "delta_kind":    "up" if delta_pct > 0 else ("down" if delta_pct < 0 else "flat"),
        "delta_label":   f"{'+' if delta_pct > 0 else ''}{delta_pct}%",
        "has_data":      peak > 0,
        "days":          days,
    }


def _build_categories() -> dict:
    products = db.get_all_products()
    if not products:
        return {"rows": [], "total_value": 0, "total_count": 0}
    by_cat = defaultdict(lambda: {"count": 0, "value": 0.0})
    for p in products:
        by_cat[p["category"]]["count"] += 1
        by_cat[p["category"]]["value"] += (p["quantity"] or 0) * (p["sell_price"] or 0)
    rows_raw = sorted(by_cat.items(), key=lambda kv: kv[1]["value"], reverse=True)
    grand = sum(v["value"] for _, v in rows_raw) or 1
    max_v = max((v["value"] for _, v in rows_raw), default=1) or 1
    rows = [{
        "name": cat,
        "count": v["count"],
        "value": v["value"],
        "value_fmt": f"{v['value']:,.0f}",
        "share":     round((v["value"] / grand) * 100, 1),  # % of total
        "bar_pct":   round((v["value"] / max_v) * 100, 1),  # bar width (vs leader)
    } for cat, v in rows_raw]
    return {
        "rows": rows,
        "total_value": grand,
        "total_value_fmt": f"{grand:,.0f}",
        "total_count": sum(r["count"] for r in rows),
    }


def _build_sellers(days: int = 30) -> dict:
    raw = db.get_top_sellers(n=10, days=days)
    if not raw:
        return {"rows": [], "total_revenue": 0}
    revs = [(t.get("revenue") or 0) for t in raw]
    total_rev = sum(revs) or 1
    max_rev = max(revs) or 1
    rows = [{
        "name":       t["name"],
        "name_local": t.get("name_local") or "",
        "sold":       f"{t['total_sold']:.1f}",
        "unit":       t["unit"],
        "revenue":    t.get("revenue") or 0,
        "revenue_fmt": f"{(t.get('revenue') or 0):,.0f}",
        "share":      round(((t.get("revenue") or 0) / total_rev) * 100, 1),
        "bar_pct":    round(((t.get("revenue") or 0) / max_rev) * 100, 1),
    } for t in raw]
    return {"rows": rows, "total_revenue": total_rev,
            "total_revenue_fmt": f"{total_rev:,.0f}"}


# ──────────────────────────────────────────────────────────────────────────────
# Per-page context
# ──────────────────────────────────────────────────────────────────────────────

# ── AI insights cache (auto-run, 5-min TTL) ───────────────────────────────────
_INSIGHTS_TTL = 300
_INSIGHTS_CACHE: dict = {"ts": None, "data": None, "running": False}


def invalidate_insights() -> None:
    """Mark the insights cache stale so the next dashboard render re-runs analysis."""
    _INSIGHTS_CACHE["ts"] = None
    _INSIGHTS_CACHE["data"] = None


def _confidence_band(pct: int) -> tuple[str, str]:
    if pct >= 85: return "high", "High confidence"
    if pct >= 70: return "med",  "Medium confidence"
    return "low", "Low confidence"


def _build_structured_insights(agent_state: dict) -> dict:
    """Convert the agent's KiranaState into typed dashboard rows.

    Each row carries the verb + noun + qty + reason needed for Principle 1
    (AI suggestions must be concrete). No row renders without all four.
    """
    today = datetime.date.today()

    # ── Reorder queue (ranked) ────────────────────────────────────────────────
    reorders: list[dict] = []
    for o in agent_state.get("suggested_orders", []) or []:
        pid = o.get("product_id")
        prod = db.get_product(pid) if pid else None
        name_te = (prod or {}).get("name_local") or ""
        on_hand = (prod or {}).get("quantity")
        unit = o.get("unit") or ((prod or {}).get("unit") or "")
        qty = o.get("qty_needed") or 0
        if not o.get("product_name") or not qty or not unit:
            continue
        conf_pct = int(round((o.get("ai_confidence") or 0) * 100))
        conf_cls, conf_label = _confidence_band(conf_pct)
        reorders.append({
            "pid":        pid,
            "name":       o["product_name"],
            "name_te":    name_te,
            "qty":        qty,
            "qty_fmt":    (f"{qty:g}"),
            "unit":       unit,
            "on_hand":    f"{on_hand:g} {unit}" if on_hand is not None else "",
            "reason":     o.get("reason") or "Below minimum stock.",
            "conf_pct":   conf_pct,
            "conf_cls":   conf_cls,
            "conf_label": conf_label,
        })
    reorders.sort(key=lambda r: -r["conf_pct"])

    # ── Expiry liquidation (stacked) ──────────────────────────────────────────
    liquidation: list[dict] = []
    for p in agent_state.get("expired_items", []) or []:
        liquidation.append({
            "pid":         p.get("id"),
            "name":        p["name"],
            "name_te":     p.get("name_local") or "",
            "qty_fmt":     f"{p['quantity']:g} {p['unit']}",
            "days_left":   -1,
            "kind":        "expired",
            "chip_label":  "Past expiry",
            "expiry_date": p.get("expiry_date") or "",
            "action_verb": "Pull from godown",
            "action_hint": "Past expiry. Remove from godown today.",
        })
    for p in agent_state.get("expiring_items", []) or []:
        try:
            days = (datetime.date.fromisoformat(p["expiry_date"]) - today).days
        except (ValueError, TypeError):
            days = 99
        if days <= 2:
            kind, discount, route = "danger", "15%", "route-3 kiranas"
        elif days <= 4:
            kind, discount, route = "warn",   "12%", "your nearest route"
        else:
            kind, discount, route = "warn",   "10%", "route-3 kiranas"
        chip = "Expires today" if days == 0 else ("Expires tomorrow" if days == 1 else f"{days} days left")
        liquidation.append({
            "pid":         p.get("id"),
            "name":        p["name"],
            "name_te":     p.get("name_local") or "",
            "qty_fmt":     f"{p['quantity']:g} {p['unit']}",
            "days_left":   days,
            "kind":        kind,
            "chip_label":  chip,
            "expiry_date": p["expiry_date"],
            "action_verb": f"Offer {discount} off",
            "action_hint": f"Discount {discount} to {route} to clear {p['quantity']:g} {p['unit']} before expiry.",
        })
    liquidation.sort(key=lambda r: (r["days_left"] if r["days_left"] >= 0 else -1))

    # ── Festival demand strip (timeline) ──────────────────────────────────────
    inv = agent_state.get("all_products", []) or []
    inv_names = {p["name"].lower() for p in inv}
    fest_strip: list[dict] = []
    for f in (agent_state.get("upcoming_festivals", []) or [])[:4]:
        demand_items = f.get("demand_items", []) or []
        missing = [i for i in demand_items if i.lower() not in inv_names]
        stocked = [i for i in demand_items if i.lower() in inv_names]
        prep_days = f.get("prep_days", 14)
        # Approximate timing: festival is "this month" or "next month".
        # Without exact dates we render "within prep window" / "stocking starts soon".
        this_month = today.month in (f.get("months") or [])
        urgent = this_month  # stocking window has opened
        eta_label = "This month" if this_month else "Next month"
        fest_strip.append({
            "key":          f.get("key"),
            "name":         f["name"],
            "name_te":      f.get("name_te", ""),
            "mult":         f.get("demand_multiplier", 1.0),
            "mult_fmt":     f"{f.get('demand_multiplier', 1.0):g}×",
            "prep_days":    prep_days,
            "eta_label":    eta_label,
            "urgent":       urgent,
            "stocked_n":    len(stocked),
            "demand_n":     len(demand_items),
            "missing_n":    len(missing),
            "missing_preview": ", ".join(missing[:3]),
            "tip":          f.get("tips", ""),
        })

    return {
        "reorders":       reorders,
        "liquidation":    liquidation,
        "festival_strip": fest_strip,
        "counts": {
            "reorders":    len(reorders),
            "liquidation": len(liquidation),
            "festivals":   len(fest_strip),
        },
    }


def _get_insights(force: bool = False) -> tuple[dict, datetime.datetime | None, str | None]:
    """Return (structured_data, last_run_ts, error). Auto-runs analysis on TTL miss."""
    now = datetime.datetime.now()
    cache = _INSIGHTS_CACHE
    fresh = (
        cache["data"] is not None
        and cache["ts"] is not None
        and (now - cache["ts"]).total_seconds() < _INSIGHTS_TTL
    )
    if fresh and not force:
        return cache["data"], cache["ts"], None
    try:
        from frontend_backend import run_analysis  # local import: avoid circular at module load
        agent_state = run_analysis()
        data = _build_structured_insights(agent_state)
        cache["ts"] = now
        cache["data"] = data
        return data, now, None
    except Exception as e:  # noqa: BLE001
        # Fall back to last good data if available
        return (cache["data"] or _empty_insights()), cache["ts"], str(e)


def _empty_insights() -> dict:
    return {
        "reorders": [], "liquidation": [], "festival_strip": [],
        "counts": {"reorders": 0, "liquidation": 0, "festivals": 0},
    }


def _format_ts(ts: datetime.datetime | None) -> str:
    if ts is None:
        return "Never analysed"
    delta = datetime.datetime.now() - ts
    secs = int(delta.total_seconds())
    if secs < 60:  return "just now"
    if secs < 3600: return f"{secs // 60} min ago"
    if secs < 86400: return f"{secs // 3600} hr ago"
    return ts.strftime("%b %d, %H:%M")


def _ctx_dashboard(state: dict) -> dict:
    insights, ts, err = _get_insights()
    return {
        "kpis":      _build_kpis(),
        "pulse":     _build_pulse(14),
        "health":    _build_health(),
        "alerts":    _build_alerts(),
        "festivals": _build_festivals(),
        "icons": {
            "health":    ICON["pulse"],
            "alerts":    ICON["bell"],
            "festivals": ICON["seasonal"],
            "ai":        ICON["sparkles"],
            "play":      ICON["play"],
            "refresh":   ICON["refresh"],
            "package":   ICON["package"],
            "search":    ICON["search"],
            "trophy":    ICON["trophy"],
            "plus":      ICON["plus"],
            "clock":     ICON["clock"],
            "trend":     ICON["trend"],
            "shipped":   ICON["shipped"],
        },
        "insights":  insights,
        "insights_meta": {
            "last_run":   _format_ts(ts),
            "stale":      ts is None,
            "error":      err,
        },
    }


def _ctx_inventory(state: dict) -> dict:
    f = state.get("filters") or {}
    q = f.get("q", "") or ""
    category = f.get("category", "All") or "All"
    status   = f.get("status", "All") or "All"

    products = db.search_products(q) if q.strip() else db.get_all_products()
    if category != "All":
        products = [p for p in products if p["category"] == category]
    if status != "All":
        products = [p for p in products if _status_of(p)[2] == status]

    rows = []
    for p in products:
        label, kind, _ = _status_of(p)
        rows.append({
            "id": p["id"], "name": p["name"],
            "name_local": p["name_local"], "category": p["category"],
            "qty_str": f"{p['quantity']} {p['unit']}",
            "min_str": f"{p['min_stock']} {p['unit']}",
            "sell_price": p["sell_price"],
            "expiry": p.get("expiry_date") or "",
            "supplier": p.get("supplier") or "",
            "status_label": label, "status_kind": kind,
        })
    return {
        "products": rows,
        "categories": ["All"] + db.CATEGORIES,
        "statuses": STATUS_FILTERS,
        "filters": {"q": q, "category": category, "status": status},
    }


def _ctx_add(state: dict) -> dict:
    return {
        "categories": db.CATEGORIES,
        "units": db.UNITS,
        "active_method": state.get("active_method", "manual"),
        "photo_result": state.get("photo_result"),
        "voice_result": state.get("voice_result"),
    }


def _ctx_orders(state: dict) -> dict:
    active_filter = state.get("orders_filter", "pending")
    all_orders = db.get_all_orders()
    if active_filter != "all":
        all_orders = [o for o in all_orders if o["status"] == active_filter]

    status_kind = {"pending": "warn", "approved": "success",
                   "received": "success", "rejected": "danger"}
    rows = [{
        "id": o["id"], "product_name": o["product_name"],
        "product_id": o["product_id"],
        "qty_needed": o["qty_needed"],
        "unit": o["unit"],
        "qty_str": f"{o['qty_needed']} {o['unit']}",
        "reason": (o["reason"] or "")[:80],
        "confidence": f"{o['ai_confidence']*100:.0f}",
        "status_raw": o["status"],
        "status": o["status"].upper(),
        "status_kind": status_kind.get(o["status"], "neutral"),
        "created_at": (o["created_at"] or "")[:16],
    } for o in all_orders]
    return {
        "orders": rows,
        "order_filters": ["pending", "approved", "received", "rejected", "all"],
        "active_filter": active_filter,
    }


def _ctx_analytics(state: dict) -> dict:
    try:
        days = int(state.get("analytics_days", 30))
    except (TypeError, ValueError):
        days = 30
    if days not in {7, 30, 90}:
        days = 30

    s = db.get_summary()
    val  = s.get("total_value", 0) or 0
    cost = s.get("cost_value", 0) or 0
    margin = val - cost
    margin_pct = (margin / val * 100) if val else 0

    top = db.get_top_sellers(n=5, days=days)
    units_sold = sum(t["total_sold"] for t in top) if top else 0
    revenue = sum((t.get("revenue") or 0) for t in top) if top else 0

    return {
        "categories":  _build_categories(),
        "sellers":     _build_sellers(days),
        "analytics_days": days,
        "analytics_ranges": [7, 30, 90],
        "icon_chart":  ICON["analytics"],
        "icon_trophy": ICON["trophy"],
        "metrics": [
            {"label": f"{days}-Day Revenue", "value": f"₹{revenue:,.0f}",
             "icon": ICON["rupee"],   "color": "success", "foot": "from top 5 sellers"},
            {"label": "Units Sold",     "value": f"{units_sold:.0f}",
             "icon": ICON["shipped"], "color": "primary", "foot": f"last {days} days"},
            {"label": "Gross Margin",   "value": f"{margin_pct:.1f}%",
             "icon": ICON["trend"],   "color": "info",
             "foot": f"₹{margin:,.0f} held on shelf"},
        ],
    }


def _ctx_seasonal(_state: dict) -> dict:
    return {
        "festivals": _build_festivals(),
        "brief": build_seasonal_summary().replace("\n", "<br>"),
    }


def _ctx_settings(_state: dict) -> dict:
    return {
        "s": {
            "shop_name":            db.get_setting("shop_name", ""),
            "owner_name":           db.get_setting("owner_name", ""),
            "region":               db.get_setting("region", ""),
            "low_stock_days_ahead": db.get_setting("low_stock_days_ahead", "7"),
            "expiry_warn_days":     db.get_setting("expiry_warn_days", "7"),
        },
        "vision_online": is_model_available(),
        "vision_status": (
            "Vision model available (LLaVA)" if is_model_available()
            else "Vision model not loaded — run setup.sh to download"
        ),
    }


_CTX = {
    "dashboard": _ctx_dashboard,
    "inventory": _ctx_inventory,
    "add":       _ctx_add,
    "orders":    _ctx_orders,
    "analytics": _ctx_analytics,
    "seasonal":  _ctx_seasonal,
    "settings":  _ctx_settings,
}


# ──────────────────────────────────────────────────────────────────────────────
# Top-bar action buttons
# ──────────────────────────────────────────────────────────────────────────────

def _theme_toggle() -> str:
    return (
        '<button class="theme-toggle" type="button" id="theme-toggle" '
        'onclick="kirana.toggleTheme()" aria-label="Switch theme" '
        'aria-pressed="false" title="Switch to light theme">'
        '<span class="theme-toggle-icon theme-toggle-sun">' + ICON["sun"] + '</span>'
        '<span class="theme-toggle-icon theme-toggle-moon">' + ICON["moon"] + '</span>'
        '</button>'
    )


def _topbar_actions(page: str) -> str:
    today = datetime.date.today().strftime("%a, %d %b %Y")
    badge = f'<span class="badge badge-neutral">{today}</span>'
    toggle = _theme_toggle()
    if page == "dashboard":
        return (
            badge +
            '<button class="btn btn-secondary btn-sm" onclick="kirana.quickAction(\'refresh\')">'
            + ICON["refresh"] + ' Refresh</button>'
            '<button class="btn btn-primary btn-sm" onclick="kirana.quickAction(\'run_analysis\')">'
            + ICON["play"] + ' Run Analysis</button>'
            + toggle
        )
    if page == "inventory":
        return (
            badge +
            '<button class="btn btn-primary btn-sm" onclick="kirana.navigate(\'add\')">'
            + ICON["plus"] + ' Add Product</button>'
            + toggle
        )
    if page == "orders":
        return (
            badge +
            '<button class="btn btn-primary btn-sm" onclick="kirana.quickAction(\'generate_orders\')">'
            + ICON["sparkles"] + ' Generate Orders</button>'
            + toggle
        )
    return badge + toggle


# ──────────────────────────────────────────────────────────────────────────────
# Public render entry
# ──────────────────────────────────────────────────────────────────────────────

def render(page: str, state: dict | None = None, toast: str = "") -> str:
    state = state or {}
    if page not in _CTX:
        page = "dashboard"

    nav_info = NAV_PAGES_BY_KEY[page]
    body_template = env.get_template(f"{page}.html")
    ctx = _CTX[page](state)
    ctx.setdefault("icons", {})
    for _k in ("seasonal", "sparkles", "package", "bell", "info", "clock",
               "edit", "trash", "store", "settings", "mic", "camera",
               "plus", "refresh", "search", "trend", "pulse", "rupee",
               "shipped", "trophy", "alert", "check", "play", "x"):
        if _k in ICON:
            ctx["icons"].setdefault(_k, ICON[_k])
    # Aliases used by dashboard
    _aliases = {"health": "pulse", "alerts": "bell",
                "festivals": "seasonal", "ai": "sparkles"}
    for _a, _src in _aliases.items():
        ctx["icons"].setdefault(_a, ICON[_src])
    body = body_template.render(**ctx)

    return env.get_template("base.html").render(
        page=page,
        nav=_nav_with_badges(),
        title=nav_info["title"],
        subtitle=nav_info["subtitle"],
        topbar_actions=_topbar_actions(page),
        body=body,
        logo_svg=LOGO_SVG,
        shop_name=db.get_setting("shop_name", "My Kirana Store"),
        region=db.get_setting("region", "India"),
        vision_online=is_model_available(),
        toast=toast,
    )


NAV_PAGES_BY_KEY = {p["key"]: p for p in NAV_PAGES}
