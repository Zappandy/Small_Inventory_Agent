"""
SQLite database layer.
Schema initialised on first run. All writes use parameterised queries.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "dukaan.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    variant         TEXT,
    supplier_id     TEXT,
    unit_type       TEXT DEFAULT 'unit',
    units_per_case  INTEGER DEFAULT 1,
    reorder_threshold INTEGER DEFAULT 2,
    last_unit_cost  REAL DEFAULT 0,
    expiry_tracked  INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aliases (
    alias       TEXT PRIMARY KEY,
    product_id  TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    gstin           TEXT,
    phone           TEXT,
    min_order_value REAL DEFAULT 0,
    avg_lead_days   INTEGER DEFAULT 2
);

CREATE TABLE IF NOT EXISTS stock_ledger (
    id          TEXT PRIMARY KEY,
    product_id  TEXT NOT NULL,
    delta       INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    source_doc  TEXT,
    unit_cost   REAL DEFAULT 0,
    recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sales_log (
    id          TEXT PRIMARY KEY,
    product_id  TEXT NOT NULL,
    qty_sold    INTEGER NOT NULL,
    unit_price  REAL DEFAULT 0,
    note_ref    TEXT,
    sold_date   TEXT DEFAULT CURRENT_DATE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id              TEXT PRIMARY KEY,
    supplier_id     TEXT NOT NULL,
    supplier_name   TEXT,
    status          TEXT DEFAULT 'pending',
    items_json      TEXT,
    po_total        REAL DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    approved_at     TEXT,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS policies (
    id          TEXT PRIMARY KEY,
    rule_type   TEXT NOT NULL,
    target      TEXT,
    value_json  TEXT,
    active      INTEGER DEFAULT 1
);

CREATE VIEW IF NOT EXISTS current_stock AS
SELECT
    p.id,
    p.name,
    p.supplier_id,
    p.reorder_threshold,
    p.units_per_case,
    COALESCE(SUM(sl.delta), 0) AS current_units
FROM products p
LEFT JOIN stock_ledger sl ON sl.product_id = p.id
GROUP BY p.id;
"""

SEED_DATA = """
INSERT OR IGNORE INTO suppliers VALUES
    ('sup_mahalakshmi', 'Mahalakshmi Marketing', '36RSLPS0259D1Z6', '7300000000', 2000, 1),
    ('sup_venkateshwara', 'Sri Venkateshwara Marketing', '36AZLIPV6442K12M', '9959404640', 5000, 2);

INSERT OR IGNORE INTO products VALUES
    ('parle_g_100g',  'Parle-G 100g',    NULL, 'sup_venkateshwara', 'case', 24, 3, 8.625, 0, CURRENT_TIMESTAMP),
    ('bingo_c',       'Bingo (C)',        NULL, 'sup_mahalakshmi',   'case', 12, 2, 870.0, 0, CURRENT_TIMESTAMP),
    ('happy_24p',     'Happy (24P)',      NULL, 'sup_venkateshwara', 'case', 24, 3, 4.464, 0, CURRENT_TIMESTAMP),
    ('parle_bulk',    'Parle (bulk)',     NULL, 'sup_mahalakshmi',   'case',  1, 1, 2450.0,0, CURRENT_TIMESTAMP);

INSERT OR IGNORE INTO aliases VALUES
    ('Bm',         'bingo_c'),
    ('bingo',      'bingo_c'),
    ('Bingo(C)',   'bingo_c'),
    ('Bingo (C)',  'bingo_c'),
    ('parle',      'parle_g_100g'),
    ('parle-g',    'parle_g_100g'),
    ('Parle-G',    'parle_g_100g'),
    ('happy',      'happy_24p'),
    ('Happy 2',    'happy_24p');

INSERT OR IGNORE INTO policies VALUES
    ('pol_min_order_maha',  'min_order', 'sup_mahalakshmi',   '{"value": 2000}', 1),
    ('pol_min_order_venk',  'min_order', 'sup_venkateshwara', '{"value": 5000}', 1),
    ('pol_price_spike',     'price_spike_alert_pct', NULL,    '{"value": 10}',   1);
"""


def init_db():
    with _conn() as conn:
        conn.executescript(SCHEMA)
        conn.executescript(SEED_DATA)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_stock_levels() -> list:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                p.name,
                s.name AS supplier,
                cs.current_units || ' units' AS stock,
                p.reorder_threshold || ' units' AS threshold,
                CASE
                    WHEN cs.current_units <= 0 THEN 'అయిపోయింది'
                    WHEN cs.current_units <= p.reorder_threshold THEN 'తక్కువగా'
                    ELSE 'OK'
                END AS status
            FROM current_stock cs
            JOIN products p ON p.id = cs.id
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            ORDER BY cs.current_units ASC
        """).fetchall()
        return [list(r) for r in rows]


def get_products_below_threshold() -> list:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT cs.id AS product_id, p.name, p.supplier_id,
                   cs.current_units AS current_stock,
                   p.reorder_threshold, p.last_unit_cost
            FROM current_stock cs
            JOIN products p ON p.id = cs.id
            WHERE cs.current_units <= p.reorder_threshold
        """).fetchall()
        return [dict(r) for r in rows]


def get_product(product_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None


def get_supplier(supplier_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE id = ?", (supplier_id,)
        ).fetchone()
        return dict(row) if row else None


def get_policies() -> dict:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT rule_type, target, value_json FROM policies WHERE active=1"
        ).fetchall()
    import json
    result: dict = {"min_order_per_supplier": {}}
    for r in rows:
        val = json.loads(r["value_json"] or "{}").get("value")
        if r["rule_type"] == "min_order" and r["target"]:
            sup = get_supplier(r["target"])
            if sup:
                result["min_order_per_supplier"][sup["name"]] = val
        else:
            result[r["rule_type"]] = val
    return result


def get_last_unit_cost(product_id: str) -> float | None:
    with _conn() as conn:
        row = conn.execute(
            """SELECT unit_cost FROM stock_ledger
               WHERE product_id=? AND event_type='receipt' AND unit_cost > 0
               ORDER BY recorded_at DESC LIMIT 1""",
            (product_id,),
        ).fetchone()
        return row["unit_cost"] if row else None


def get_pending_pos() -> list:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, supplier_name, items_json, po_total
               FROM purchase_orders WHERE status='pending'
               ORDER BY created_at DESC"""
        ).fetchall()
    result = []
    import json
    for r in rows:
        items = json.loads(r["items_json"] or "[]")
        item_summary = ", ".join(
            f"{i.get('product_name','?')} ×{i.get('suggested_qty_cases','?')}"
            for i in items
        )
        reason_te = "; ".join(i.get("reason_te", "") for i in items)
        result.append([r["id"], r["supplier_name"], item_summary,
                        f"₹{r['po_total']:.0f}", reason_te])
    return result


def get_weekly_summary() -> dict:
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    with _conn() as conn:
        purchases = conn.execute(
            """SELECT COALESCE(SUM(delta * unit_cost), 0) as total
               FROM stock_ledger WHERE event_type='receipt' AND recorded_at >= ?""",
            (week_ago,),
        ).fetchone()["total"]
        sales_qty = conn.execute(
            """SELECT COALESCE(SUM(ABS(delta)), 0) as qty
               FROM stock_ledger WHERE event_type='sale' AND recorded_at >= ?""",
            (week_ago,),
        ).fetchone()["qty"]
    return {"purchases_inr": purchases, "units_sold": sales_qty, "period": "7 days"}


def get_shrinkage_report() -> dict:
    with _conn() as conn:
        received = conn.execute(
            "SELECT COALESCE(SUM(delta),0) FROM stock_ledger WHERE event_type='receipt'"
        ).fetchone()[0]
        sold = abs(conn.execute(
            "SELECT COALESCE(SUM(delta),0) FROM stock_ledger WHERE event_type='sale'"
        ).fetchone()[0])
        current = conn.execute(
            "SELECT COALESCE(SUM(current_units),0) FROM current_stock"
        ).fetchone()[0]
    expected = received - sold
    shrinkage = expected - current
    pct = (shrinkage / received * 100) if received else 0
    return {
        "received": received, "sold": sold,
        "expected_on_shelf": expected, "actual_on_shelf": current,
        "shrinkage_units": shrinkage, "shrinkage_pct": round(pct, 2),
    }


def get_cost_vs_revenue() -> dict:
    with _conn() as conn:
        cost = conn.execute(
            "SELECT COALESCE(SUM(ABS(delta)*unit_cost),0) FROM stock_ledger WHERE event_type='receipt'"
        ).fetchone()[0]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(qty_sold*unit_price),0) FROM sales_log"
        ).fetchone()[0]
    return {"total_cost_inr": cost, "estimated_revenue_inr": revenue,
            "gross_margin_inr": revenue - cost}


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def update_stock(product_id, delta, event_type, source_doc, unit_cost=0):
    with _conn() as conn:
        conn.execute(
            """INSERT INTO stock_ledger (id, product_id, delta, event_type, source_doc, unit_cost)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), product_id, delta, event_type, source_doc, unit_cost),
        )
        if unit_cost > 0 and event_type == "receipt":
            conn.execute(
                "UPDATE products SET last_unit_cost=? WHERE id=?",
                (unit_cost, product_id),
            )


def log_receipt(receipt: dict) -> str:
    doc_id = str(uuid.uuid4())
    import json
    with _conn() as conn:
        conn.execute(
            """INSERT INTO stock_ledger (id, product_id, delta, event_type, source_doc)
               VALUES (?, 'raw_receipt', 0, 'receipt_log', ?)""",
            (doc_id, json.dumps(receipt, ensure_ascii=False)),
        )
    return doc_id


def save_pending_po(po: dict) -> str:
    import json
    po_id = f"PO-{str(uuid.uuid4())[:8].upper()}"
    with _conn() as conn:
        conn.execute(
            """INSERT INTO purchase_orders
               (id, supplier_id, supplier_name, status, items_json, po_total)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (
                po_id,
                po.get("supplier_id", "unknown"),
                po.get("supplier_name", "Unknown"),
                json.dumps(po.get("items", []), ensure_ascii=False),
                po.get("po_total", 0),
            ),
        )
    return po_id


def approve_purchase_order(po_id: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE purchase_orders SET status='approved', approved_at=CURRENT_TIMESTAMP WHERE id=?",
            (po_id,),
        )


def reject_purchase_order(po_id: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE purchase_orders SET status='rejected' WHERE id=?", (po_id,)
        )
