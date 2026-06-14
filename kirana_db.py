"""
kirana_db — adapter that exposes kirana-ai's DB surface on top of the
Dukaan Saathi storage layer.

Why this exists:
- The UI ported from kirana-ai expects a SQLite schema with product columns
  for quantity / min_stock / buy_price / sell_price / expiry_date, plus
  `orders`, `sales`, and `settings` tables.
- Dukaan Saathi's canonical store is a ledger-backed schema where
  `current_stock` is `SUM(stock_ledger.delta)`. The store is authoritative.
- This module extends the Dukaan schema with the few extra columns/tables
  the UI needs, and presents read/write helpers shaped the way
  `ui.py` calls them.

All stock writes still flow through Dukaan's `apply_stock_delta` /
`set_product_stock` — the model-output-never-writes-inventory rule is
preserved.
"""

from __future__ import annotations

import datetime as _dt
import math
import sqlite3
import uuid
from typing import Any

from dukaan_saathi.services.inventory import apply_owner_stock_delta, set_owner_stock
from dukaan_saathi.storage import (
    SCHEMA_SQL,
    find_product as _dukaan_find_product,
    get_conn,
    init_db as _dukaan_init_db,
)


# ──────────────────────────────────────────────────────────────────────────────
# Schema extensions
# ──────────────────────────────────────────────────────────────────────────────
UNITS = ["kg", "g", "litre", "ml", "piece", "packet", "dozen", "box", "bag", "bottle"]

CATEGORIES = [
    "Grains & Flour",
    "Pulses & Lentils",
    "Spices & Masala",
    "Oils & Ghee",
    "Dairy",
    "Snacks & Biscuits",
    "Beverages",
    "Cleaning & Hygiene",
    "Personal Care",
    "Fruits & Vegetables",
    "Other",
]


EXTRA_PRODUCT_COLUMNS: list[tuple[str, str]] = [
    ("name_local",   "TEXT DEFAULT ''"),
    ("category",     "TEXT DEFAULT 'Other'"),
    ("sell_price",   "REAL DEFAULT 0"),
    ("expiry_date",  "TEXT"),
    ("updated_at",   "TEXT"),
]

EXTRA_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    product_id      TEXT NOT NULL,
    product_name    TEXT NOT NULL DEFAULT '',
    qty_needed      REAL NOT NULL DEFAULT 0,
    unit            TEXT NOT NULL DEFAULT '',
    reason          TEXT NOT NULL DEFAULT '',
    ai_confidence   REAL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sales (
    id              TEXT PRIMARY KEY,
    product_id      TEXT NOT NULL,
    qty_sold        REAL NOT NULL,
    price_per_unit  REAL NOT NULL DEFAULT 0,
    sale_date       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX IF NOT EXISTS idx_sales_product_id ON sales(product_id);
CREATE INDEX IF NOT EXISTS idx_sales_date       ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_orders_status    ON orders(status);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def _apply_extensions() -> None:
    """Idempotently add the extra product columns and helper tables."""
    with get_conn() as conn:
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
        for col_name, col_def in EXTRA_PRODUCT_COLUMNS:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_def}")
        conn.executescript(EXTRA_TABLES_SQL)


_initialized = False


def init_db() -> None:
    """Initialize Dukaan Saathi storage and apply kirana-ai extensions."""
    global _initialized
    if _initialized:
        return
    _dukaan_init_db(seed_demo_data=True)
    _apply_extensions()
    _seed_default_settings()
    _seed_kirana_demo_products()
    _initialized = True


def _seed_default_settings() -> None:
    defaults = {
        "shop_name":           "Dukaan Saathi",
        "owner_name":          "",
        "region":              "Telangana",
        "low_stock_days_ahead": "3",
        "expiry_warn_days":    "7",
    }
    with get_conn() as conn:
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (k, v),
            )


def _seed_kirana_demo_products() -> None:
    """Idempotently add friendlier demo products for stakeholder demos."""
    demo_products = [
        ("Tomato", "టమాట", "Fruits & Vegetables", 18, "kg", 8, 28, 40, "Fresh Mandi Supplier"),
        ("Onion", "ఉల్లిపాయ", "Fruits & Vegetables", 25, "kg", 10, 22, 34, "Fresh Mandi Supplier"),
        ("Potato", "బంగాళాదుంప", "Fruits & Vegetables", 20, "kg", 10, 20, 32, "Fresh Mandi Supplier"),
        ("Banana", "అరటి పండు", "Fruits & Vegetables", 36, "piece", 18, 4, 7, "Fresh Mandi Supplier"),
        ("Apple", "ఆపిల్", "Fruits & Vegetables", 24, "piece", 12, 18, 30, "Fresh Mandi Supplier"),
        ("Coriander", "కొత్తిమీర", "Fruits & Vegetables", 15, "bunch", 8, 5, 10, "Fresh Mandi Supplier"),
        ("Green Chilli", "పచ్చి మిర్చి", "Fruits & Vegetables", 6, "kg", 3, 45, 70, "Fresh Mandi Supplier"),

        ("Milk 500ml", "పాలు 500ml", "Dairy", 30, "packet", 12, 24, 28, "Daily Dairy Distributor"),
        ("Curd 500g", "పెరుగు 500g", "Dairy", 18, "packet", 8, 28, 35, "Daily Dairy Distributor"),
        ("Eggs", "గుడ్లు", "Dairy", 60, "piece", 24, 5, 7, "Daily Dairy Distributor"),

        ("Toor Dal", "కందిపప్పు", "Other", 14, "kg", 6, 118, 145, "Sri Lakshmi Traders"),
        ("Basmati Rice", "బాస్మతి బియ్యం", "Other", 22, "kg", 10, 82, 105, "Sri Lakshmi Traders"),
        ("Sunflower Oil 1L", "సన్‌ఫ్లవర్ ఆయిల్ 1L", "Other", 16, "bottle", 8, 118, 145, "Sri Lakshmi Traders"),
        ("Maggi 70g", "మ్యాగీ 70g", "Other", 40, "packet", 20, 12, 14, "Sri Venkateshwara Marketing"),
    ]

    for name, name_local, category, quantity, unit, min_stock, buy_price, sell_price, supplier in demo_products:
        if find_by_name(name):
            continue

        try:
            add_product(
                name,
                category,
                quantity,
                unit,
                min_stock,
                buy_price,
                sell_price,
                name_local=name_local,
                supplier=supplier,
            )
        except Exception:
            # Demo seeding must never block app startup.
            continue


def _new_id() -> str:
    return str(uuid.uuid4())


def _round_stock_quantity(value: float) -> int:
    value_f = float(value or 0)
    if value_f >= 0:
        return int(math.floor(value_f + 0.5))
    return int(math.ceil(value_f - 0.5))


def _today() -> str:
    return _dt.date.today().isoformat()


def _today_plus(days: int) -> str:
    return (_dt.date.today() + _dt.timedelta(days=days)).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Product reads — return kirana-ai-shaped dicts
# ──────────────────────────────────────────────────────────────────────────────
PRODUCT_SELECT = """
SELECT
    p.id                                                                AS id,
    p.name                                                              AS name,
    COALESCE(p.name_local, '')                                          AS name_local,
    COALESCE(p.category, 'Other')                                       AS category,
    COALESCE(p.unit_type, 'unit')                                       AS unit,
    COALESCE(SUM(sl.delta), 0)                                          AS quantity,
    COALESCE(p.reorder_threshold, 0)                                    AS min_stock,
    COALESCE(p.last_unit_cost, 0)                                       AS buy_price,
    COALESCE(p.sell_price, 0)                                           AS sell_price,
    p.expiry_date                                                       AS expiry_date,
    COALESCE(s.name, 'Unknown Supplier')                                AS supplier,
    COALESCE(p.updated_at, p.created_at)                                AS updated_at,
    p.target_stock                                                      AS target_stock
FROM products p
LEFT JOIN suppliers     s  ON s.id = p.supplier_id
LEFT JOIN stock_ledger  sl ON sl.product_id = p.id
"""


def _rows_to_products(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def get_all_products() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            f"{PRODUCT_SELECT} WHERE p.active = 1 GROUP BY p.id ORDER BY p.name COLLATE NOCASE"
        ).fetchall()
    return _rows_to_products(rows)


def get_product(product_id: Any) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            f"{PRODUCT_SELECT} WHERE p.id = ? AND p.active = 1 GROUP BY p.id",
            (str(product_id),),
        ).fetchone()
    return dict(row) if row else None


def get_low_stock() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            f"""{PRODUCT_SELECT}
                WHERE p.active = 1
                GROUP BY p.id
                HAVING quantity <= min_stock
                ORDER BY (CASE WHEN min_stock = 0 THEN 0 ELSE quantity * 1.0 / min_stock END) ASC"""
        ).fetchall()
    return _rows_to_products(rows)


def get_expiring_soon(days: int = 7) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            f"""{PRODUCT_SELECT}
                WHERE p.active = 1
                  AND p.expiry_date IS NOT NULL
                  AND p.expiry_date BETWEEN ? AND ?
                GROUP BY p.id
                ORDER BY p.expiry_date""",
            (_today(), _today_plus(days)),
        ).fetchall()
    return _rows_to_products(rows)


def get_expired() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            f"""{PRODUCT_SELECT}
                WHERE p.active = 1
                  AND p.expiry_date IS NOT NULL
                  AND p.expiry_date < ?
                GROUP BY p.id
                ORDER BY p.expiry_date""",
            (_today(),),
        ).fetchall()
    return _rows_to_products(rows)


def search_products(query: str) -> list[dict[str, Any]]:
    q = f"%{query}%"
    with get_conn() as conn:
        rows = conn.execute(
            f"""{PRODUCT_SELECT}
                WHERE p.active = 1
                  AND (p.name LIKE ? OR COALESCE(p.name_local,'') LIKE ? OR COALESCE(p.category,'') LIKE ?)
                GROUP BY p.id
                ORDER BY p.name COLLATE NOCASE""",
            (q, q, q),
        ).fetchall()
    return _rows_to_products(rows)


def find_by_name(name: str) -> list[dict[str, Any]]:
    """Compat with kirana-ai. Returns list (often 1 item) using Dukaan's matcher."""
    p = _dukaan_find_product(name)
    if not p:
        return []
    full = get_product(p["id"])
    return [full] if full else []


# ──────────────────────────────────────────────────────────────────────────────
# Summary / KPIs
# ──────────────────────────────────────────────────────────────────────────────
def get_summary() -> dict[str, Any]:
    products = get_all_products()
    total = len(products)
    low = sum(1 for p in products if p["quantity"] <= p["min_stock"])
    total_value = sum(p["quantity"] * p["sell_price"] for p in products)
    cost_value  = sum(p["quantity"] * p["buy_price"]  for p in products)
    expiring = len(get_expiring_soon(7))
    expired  = len(get_expired())
    return {
        "total":          total,
        "low_stock":      low,
        "total_value":    total_value,
        "cost_value":     cost_value,
        "expiring_soon":  expiring,
        "expired":        expired,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Stock writes — all go through the Dukaan ledger
# ──────────────────────────────────────────────────────────────────────────────
def adjust_stock(product_id: Any, delta: float, mode: str = "add") -> dict[str, Any]:
    pid = str(product_id)
    if mode == "set":
        return set_owner_stock(
            product_id=pid,
            new_stock=float(delta),
            event_type="manual",
            source_doc="ui_adjustment",
            note="Owner set absolute stock from UI",
        )
    return apply_owner_stock_delta(
        product_id=pid,
        delta=float(delta),
        event_type="manual",
        source_doc="ui_adjustment",
        note="Owner added stock from UI",
    )


def record_sale(product_id: Any, qty: float, price: float) -> None:
    pid = str(product_id)
    apply_owner_stock_delta(
        product_id=pid,
        delta=-float(qty),
        event_type="sale",
        source_doc="pos",
        note=f"Sale @ {price}/unit",
    )
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sales (id, product_id, qty_sold, price_per_unit) VALUES (?, ?, ?, ?)",
            (_new_id(), pid, float(qty), float(price)),
        )


def delete_product(product_id: Any) -> None:
    """Soft delete — sets active=0. Ledger history is preserved."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(product_id),),
        )


def add_product(
    name: str,
    category: str,
    quantity: float,
    unit: str,
    min_stock: float,
    buy_price: float,
    sell_price: float,
    *,
    name_local: str = "",
    expiry_date: str | None = None,
    supplier: str = "",
) -> str:
    pid = _new_id()
    supplier_id = _ensure_supplier(supplier) if supplier else None

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO products
            (id, name, supplier_id, unit_type, units_per_case,
             reorder_threshold, target_stock, last_unit_cost,
             active, name_local, category, sell_price, expiry_date,
             updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                pid, name, supplier_id, unit,
                _round_stock_quantity(min_stock or 0),
                max(_round_stock_quantity(min_stock or 0) * 3, 10),
                float(buy_price or 0),
                name_local, category or "Other", float(sell_price or 0), expiry_date,
            ),
        )

    if quantity and float(quantity) > 0:
        apply_owner_stock_delta(
            product_id=pid,
            delta=float(quantity),
            event_type="initial",
            source_doc="ui_add",
            unit_cost=float(buy_price or 0),
            note=f"Initial stock for {name}",
        )
    return pid


def _ensure_supplier(name: str) -> str | None:
    name = (name or "").strip()
    if not name:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM suppliers WHERE LOWER(name) = LOWER(?)",
            (name,),
        ).fetchone()
        if row:
            return row[0]
        sid = _new_id()
        conn.execute(
            "INSERT INTO suppliers (id, name) VALUES (?, ?)",
            (sid, name),
        )
        return sid


# ──────────────────────────────────────────────────────────────────────────────
# Orders
# ──────────────────────────────────────────────────────────────────────────────
def get_pending_orders() -> list[dict[str, Any]]:
    return get_all_orders(status="pending")


def get_all_orders(limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM orders"
    args: tuple = ()
    if status:
        sql += " WHERE status = ?"
        args = (status,)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args = (*args, int(limit))
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def insert_orders(orders: list[dict[str, Any]]) -> int:
    if not orders:
        return 0
    with get_conn() as conn:
        for o in orders:
            conn.execute(
                """
                INSERT INTO orders
                (id, product_id, product_name, qty_needed, unit, reason,
                 ai_confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    _new_id(),
                    str(o.get("product_id") or ""),
                    str(o.get("product_name") or ""),
                    float(o.get("qty_needed") or 0),
                    str(o.get("unit") or ""),
                    str(o.get("reason") or ""),
                    float(o.get("ai_confidence") or 0.8),
                ),
            )
    return len(orders)


def create_order(
    product_name: str,
    product_id: Any,
    qty_needed: float,
    unit: str,
    reason: str = "",
    ai_confidence: float = 0.8,
) -> str:
    oid = _new_id()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO orders
            (id, product_id, product_name, qty_needed, unit, reason,
             ai_confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                oid, str(product_id or ""), product_name,
                float(qty_needed or 0), unit or "", reason,
                float(ai_confidence or 0.8),
            ),
        )
    return oid


def get_sales_history(product_id: Any, days: int = 30) -> list[dict[str, Any]]:
    since = _today_plus(-int(days))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sales WHERE product_id = ? AND sale_date >= ? "
            "ORDER BY sale_date DESC",
            (str(product_id), since),
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_velocity(product_id: Any, days: int = 30) -> float:
    since = _today_plus(-int(days))
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(qty_sold), 0) * 1.0 / ? AS v "
            "FROM sales WHERE product_id = ? AND sale_date >= ?",
            (max(int(days), 1), str(product_id), since),
        ).fetchone()
    return round(float(row["v"]) if row else 0.0, 3)


def update_order_status(order_id: Any, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, str(order_id)),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Sales analytics
# ──────────────────────────────────────────────────────────────────────────────
def get_top_sellers(n: int = 5, days: int = 30) -> list[dict[str, Any]]:
    since = _today_plus(-int(days))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id                                       AS id,
                p.name                                     AS name,
                COALESCE(p.name_local, '')                 AS name_local,
                COALESCE(p.unit_type, 'unit')              AS unit,
                SUM(s.qty_sold)                            AS total_sold,
                SUM(s.qty_sold * s.price_per_unit)         AS revenue
            FROM sales s
            JOIN products p ON p.id = s.product_id
            WHERE s.sale_date >= ?
            GROUP BY p.id
            ORDER BY revenue DESC
            LIMIT ?
            """,
            (since, int(n)),
        ).fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────────────────────────────────────
def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
