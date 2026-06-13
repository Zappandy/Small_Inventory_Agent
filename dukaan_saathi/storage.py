from __future__ import annotations

from contextlib import contextmanager
import sqlite3
import uuid
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from dukaan_saathi.config import DB_PATH


# =============================================================================
# Demo seed data
# =============================================================================
# MVP note:
# This is intentionally hardcoded for the first hackathon demo.
# Keep all seed assumptions here so they are easy to audit and replace later with:
# - samples/catalog.csv
# - samples/suppliers.csv
# - a Gradio product setup screen
# - real shop inventory export
# =============================================================================

DEMO_SUPPLIERS = [
    {
        "id": "sup_mahalakshmi",
        "name": "Mahalakshmi Marketing",
        "phone": "",
        "min_order_value": 2000.0,
        "avg_lead_days": 1,
    },
    {
        "id": "sup_venkateshwara",
        "name": "Sri Venkateshwara Marketing",
        "phone": "",
        "min_order_value": 5000.0,
        "avg_lead_days": 2,
    },
    {
        "id": "sup_brundavan_buns",
        "name": "Brundavan Buns",
        "phone": "",
        "min_order_value": 0.0,
        "avg_lead_days": 1,
    },
]


DEMO_PRODUCTS = [
    {
        "id": "bingo_c",
        "name": "Bingo (C)",
        "supplier_id": "sup_mahalakshmi",
        "unit_type": "case",
        "units_per_case": 12,
        "reorder_threshold": 2,
        "target_stock": 6,
        "last_unit_cost": 870.0,
        "initial_stock": 1,
    },
    {
        "id": "parle_bulk",
        "name": "Parle (bulk)",
        "supplier_id": "sup_mahalakshmi",
        "unit_type": "case",
        "units_per_case": 1,
        "reorder_threshold": 1,
        "target_stock": 3,
        "last_unit_cost": 2450.0,
        "initial_stock": 1,
    },
    {
        "id": "parle_60gm_72p",
        "name": "PARLE-G 60GM RS.72P",
        "supplier_id": "sup_venkateshwara",
        "unit_type": "case",
        "units_per_case": 72,
        "reorder_threshold": 3,
        "target_stock": 8,
        "last_unit_cost": 8.625,
        "initial_stock": 2,
    },
    {
        "id": "happy_24p",
        "name": "Happy Happy 27.5G (24P)",
        "supplier_id": "sup_venkateshwara",
        "unit_type": "case",
        "units_per_case": 24,
        "reorder_threshold": 3,
        "target_stock": 8,
        "last_unit_cost": 4.464,
        "initial_stock": 4,
    },
    {
        "id": "bun",
        "name": "Bun",
        "supplier_id": "sup_brundavan_buns",
        "unit_type": "piece",
        "units_per_case": 1,
        "reorder_threshold": 10,
        "target_stock": 20,
        "last_unit_cost": 10.0,
        "initial_stock": 8,
    },
    {
        "id": "obm",
        "name": "OBM",
        "supplier_id": "sup_brundavan_buns",
        "unit_type": "piece",
        "units_per_case": 1,
        "reorder_threshold": 10,
        "target_stock": 20,
        "last_unit_cost": 9.5,
        "initial_stock": 5,
    },
]


DEMO_ALIASES = {
    "bingo_c": [
        "Bingo",
        "bingo",
        "Bingo C",
        "Bingo(C)",
        "Bingo (C)",
        "Bm",
    ],
    "parle_bulk": [
        "Parle bulk",
        "parle bulk",
        "Parle",
    ],
    "parle_60gm_72p": [
        "PARLE-G 60GM RS.72P",
        "PARLE G 60GM",
        "PARLE-G 60GM",
        "Parle-G 60GM",
        "Parle-G",
        "parle-g",
    ],
    "happy_24p": [
        "Happy",
        "Happy Happy",
        "Happy Happy 27.5G",
        "Happy Happy 27.5G(24P)*13",
        "HAPPY HAPPY 27.5G(24P)*13",
        "Happy 24P",
        "Happy 2",
    ],
    "bun": [
        "Bun",
        "Buns",
        "bun",
        "buns",
    ],
    "obm": [
        "OBM",
        "Obm",
        "obm",
    ],
}


# =============================================================================
# SQLite schema
# =============================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    phone TEXT DEFAULT '',
    min_order_value REAL NOT NULL DEFAULT 0,
    avg_lead_days INTEGER NOT NULL DEFAULT 2,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    supplier_id TEXT,
    unit_type TEXT NOT NULL DEFAULT 'unit',
    units_per_case INTEGER NOT NULL DEFAULT 1,
    reorder_threshold INTEGER NOT NULL DEFAULT 2,
    target_stock INTEGER NOT NULL DEFAULT 10,
    last_unit_cost REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS aliases (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS stock_ledger (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    delta INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    source_doc TEXT DEFAULT '',
    unit_cost REAL DEFAULT 0,
    note TEXT DEFAULT '',
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX IF NOT EXISTS idx_stock_ledger_product_id
ON stock_ledger(product_id);

CREATE VIEW IF NOT EXISTS current_stock AS
SELECT
    p.id AS product_id,
    p.name AS product_name,
    p.supplier_id,
    p.unit_type,
    p.units_per_case,
    p.reorder_threshold,
    p.target_stock,
    p.last_unit_cost,
    COALESCE(SUM(sl.delta), 0) AS current_stock
FROM products p
LEFT JOIN stock_ledger sl ON sl.product_id = p.id
WHERE p.active = 1
GROUP BY p.id;
"""


# =============================================================================
# Helpers
# =============================================================================

def normalize_text(text: str) -> str:
    """
    Normalize product names and aliases for matching.

    Examples:
    - "Bingo(C)" -> "bingo c"
    - "PARLE-G 60GM RS.72P" -> "parle g 60gm rs 72p"
    """
    text = text or ""
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return " ".join(cleaned.split())


def _new_id() -> str:
    return str(uuid.uuid4())


def _ensure_db_parent() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    _ensure_db_parent()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_conn():
    conn = get_conn()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# =============================================================================
# Initialization / seed
# =============================================================================

def init_db(seed_demo_data: bool = True) -> None:
    """
    Initialize the SQLite DB.

    seed_demo_data=True is for the hackathon MVP.
    Later, we can set this false and load catalog/supplier data from user files.
    """
    with db_conn() as conn:
        conn.executescript(SCHEMA_SQL)

    if seed_demo_data:
        seed_database()


def seed_database() -> None:
    """
    Insert demo suppliers, products, aliases, and initial stock exactly once.
    """
    with db_conn() as conn:
        for supplier in DEMO_SUPPLIERS:
            conn.execute(
                """
                INSERT OR IGNORE INTO suppliers
                (id, name, phone, min_order_value, avg_lead_days)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    supplier["id"],
                    supplier["name"],
                    supplier["phone"],
                    supplier["min_order_value"],
                    supplier["avg_lead_days"],
                ),
            )

        for product in DEMO_PRODUCTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO products
                (
                    id,
                    name,
                    supplier_id,
                    unit_type,
                    units_per_case,
                    reorder_threshold,
                    target_stock,
                    last_unit_cost
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product["id"],
                    product["name"],
                    product["supplier_id"],
                    product["unit_type"],
                    product["units_per_case"],
                    product["reorder_threshold"],
                    product["target_stock"],
                    product["last_unit_cost"],
                ),
            )

        for product_id, aliases in DEMO_ALIASES.items():
            for alias in aliases:
                add_alias(conn, product_id=product_id, alias=alias)

        existing_seed_count = conn.execute(
            "SELECT COUNT(*) FROM stock_ledger WHERE event_type = 'seed'"
        ).fetchone()[0]

        if existing_seed_count == 0:
            for product in DEMO_PRODUCTS:
                initial_stock = int(product.get("initial_stock", 0))
                if initial_stock == 0:
                    continue

                conn.execute(
                    """
                    INSERT INTO stock_ledger
                    (id, product_id, delta, event_type, source_doc, unit_cost, note)
                    VALUES (?, ?, ?, 'seed', 'demo_seed', ?, ?)
                    """,
                    (
                        _new_id(),
                        product["id"],
                        initial_stock,
                        float(product.get("last_unit_cost", 0)),
                        "Initial demo stock",
                    ),
                )


def add_alias(conn: sqlite3.Connection, product_id: str, alias: str) -> None:
    alias_norm = normalize_text(alias)
    if not alias_norm:
        return

    conn.execute(
        """
        INSERT OR IGNORE INTO aliases
        (id, product_id, alias, alias_norm)
        VALUES (?, ?, ?, ?)
        """,
        (_new_id(), product_id, alias, alias_norm),
    )


# =============================================================================
# Reads
# =============================================================================

def get_inventory() -> list[dict[str, Any]]:
    """
    Return inventory rows for the UI.
    """
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                cs.product_id,
                cs.product_name,
                COALESCE(s.name, 'Unknown Supplier') AS supplier,
                cs.current_stock,
                cs.reorder_threshold,
                cs.target_stock,
                cs.unit_type,
                cs.units_per_case,
                cs.last_unit_cost,
                CASE
                    WHEN cs.current_stock <= 0 THEN 'OUT'
                    WHEN cs.current_stock <= cs.reorder_threshold THEN 'LOW'
                    ELSE 'OK'
                END AS status
            FROM current_stock cs
            LEFT JOIN suppliers s ON s.id = cs.supplier_id
            ORDER BY
                CASE
                    WHEN cs.current_stock <= 0 THEN 0
                    WHEN cs.current_stock <= cs.reorder_threshold THEN 1
                    ELSE 2
                END,
                supplier,
                cs.product_name
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_product(product_id: str) -> dict[str, Any] | None:
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT
                p.id,
                p.name,
                p.supplier_id,
                COALESCE(s.name, 'Unknown Supplier') AS supplier,
                p.unit_type,
                p.units_per_case,
                p.reorder_threshold,
                p.target_stock,
                p.last_unit_cost,
                p.active
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.id = ?
            """,
            (product_id,),
        ).fetchone()

    return _row_to_dict(row)


def get_supplier_by_name(name: str) -> dict[str, Any] | None:
    name_norm = normalize_text(name)

    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM suppliers").fetchall()

    for row in rows:
        supplier = dict(row)
        if normalize_text(supplier["name"]) == name_norm:
            return supplier

    return None


def get_current_stock(product_id: str) -> int:
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT current_stock
            FROM current_stock
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

    if row is None:
        return 0

    return int(row["current_stock"])


def get_low_stock() -> list[dict[str, Any]]:
    return [
        row
        for row in get_inventory()
        if int(row["current_stock"]) <= int(row["reorder_threshold"])
    ]


def find_product(query: str) -> dict[str, Any] | None:
    """
    Find a product from:
    - exact alias
    - alias contained in a longer command/receipt row
    - exact product name
    - product name contained in a longer string
    - fuzzy match fallback

    Returns a product dict shaped for parsers:
    {
        id,
        name,
        supplier,
        ...
    }
    """
    query_norm = normalize_text(query)
    if not query_norm:
        return None

    with db_conn() as conn:
        alias_rows = conn.execute(
            """
            SELECT product_id, alias, alias_norm
            FROM aliases
            """
        ).fetchall()

        product_rows = conn.execute(
            """
            SELECT id, name
            FROM products
            WHERE active = 1
            """
        ).fetchall()

    alias_map = {
        row["alias_norm"]: row["product_id"]
        for row in alias_rows
        if row["alias_norm"]
    }

    product_map = {
        normalize_text(row["name"]): row["id"]
        for row in product_rows
        if normalize_text(row["name"])
    }

    # 1. Exact alias.
    if query_norm in alias_map:
        return get_product(alias_map[query_norm])

    # 2. Alias contained in command or receipt text.
    contained_aliases = [
        (alias_norm, product_id)
        for alias_norm, product_id in alias_map.items()
        if alias_norm in query_norm
    ]
    if contained_aliases:
        best_alias, product_id = sorted(
            contained_aliases,
            key=lambda item: len(item[0]),
            reverse=True,
        )[0]
        return get_product(product_id)

    # 3. Exact product name.
    if query_norm in product_map:
        return get_product(product_map[query_norm])

    # 4. Product name contained in command or receipt text.
    contained_products = [
        (product_norm, product_id)
        for product_norm, product_id in product_map.items()
        if product_norm in query_norm
    ]
    if contained_products:
        best_name, product_id = sorted(
            contained_products,
            key=lambda item: len(item[0]),
            reverse=True,
        )[0]
        return get_product(product_id)

    # 5. Fuzzy fallback.
    candidates = {**alias_map, **product_map}
    matches = get_close_matches(
        query_norm,
        list(candidates.keys()),
        n=1,
        cutoff=0.60,
    )

    if matches:
        return get_product(candidates[matches[0]])

    return None


# =============================================================================
# Writes
# =============================================================================

def apply_stock_delta(
    product_id: str,
    delta: int,
    event_type: str,
    source_doc: str = "",
    unit_cost: float | None = None,
    note: str = "",
) -> dict[str, Any]:
    """
    Add a stock ledger event.

    We clamp final stock to zero so bad commands cannot make inventory negative.
    The ledger stores the safe delta actually applied.
    """
    product = get_product(product_id)
    if product is None:
        raise ValueError(f"Unknown product_id: {product_id}")

    previous_stock = get_current_stock(product_id)
    requested_delta = int(delta)
    new_stock = max(previous_stock + requested_delta, 0)
    safe_delta = new_stock - previous_stock

    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO stock_ledger
            (id, product_id, delta, event_type, source_doc, unit_cost, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id(),
                product_id,
                safe_delta,
                event_type,
                source_doc,
                float(unit_cost or 0),
                note,
            ),
        )

        if unit_cost is not None and float(unit_cost) > 0:
            conn.execute(
                """
                UPDATE products
                SET last_unit_cost = ?
                WHERE id = ?
                """,
                (float(unit_cost), product_id),
            )

    return {
        "product_id": product_id,
        "product_name": product["name"],
        "previous_stock": previous_stock,
        "new_stock": new_stock,
        "requested_delta": requested_delta,
        "delta": safe_delta,
        "event_type": event_type,
        "source_doc": source_doc,
        "note": note,
    }


def set_product_stock(
    product_id: str,
    new_stock: int,
    event_type: str,
    source_doc: str = "",
    note: str = "",
) -> dict[str, Any]:
    """
    Set stock to an absolute number by calculating a ledger delta.
    """
    previous_stock = get_current_stock(product_id)
    target_stock = max(int(new_stock), 0)
    delta = target_stock - previous_stock

    return apply_stock_delta(
        product_id=product_id,
        delta=delta,
        event_type=event_type,
        source_doc=source_doc,
        unit_cost=None,
        note=note,
    )


def create_product(
    *,
    product_id: str,
    name: str,
    supplier_id: str | None = None,
    unit_type: str = "unit",
    units_per_case: int = 1,
    reorder_threshold: int = 2,
    target_stock: int = 10,
    last_unit_cost: float = 0,
    aliases: list[str] | None = None,
) -> None:
    """
    Small helper for later when the UI needs to add products.
    Not used heavily in the first MVP, but useful for avoiding permanent hardcoding.
    """
    aliases = aliases or []

    with db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO products
            (
                id,
                name,
                supplier_id,
                unit_type,
                units_per_case,
                reorder_threshold,
                target_stock,
                last_unit_cost,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                product_id,
                name,
                supplier_id,
                unit_type,
                int(units_per_case),
                int(reorder_threshold),
                int(target_stock),
                float(last_unit_cost),
            ),
        )

        add_alias(conn, product_id, name)
        for alias in aliases:
            add_alias(conn, product_id, alias)


def create_supplier(
    *,
    supplier_id: str,
    name: str,
    phone: str = "",
    min_order_value: float = 0,
    avg_lead_days: int = 2,
) -> None:
    """
    Small helper for later when the UI needs to add suppliers.
    """
    with db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO suppliers
            (id, name, phone, min_order_value, avg_lead_days)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                supplier_id,
                name,
                phone,
                float(min_order_value),
                int(avg_lead_days),
            ),
        )
