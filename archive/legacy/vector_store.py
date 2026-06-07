"""
ChromaDB vector store.

Collections:
  product_aliases  — embed product names/aliases; query to resolve fuzzy OCR text
  receipt_chunks   — embed raw receipt text for price history RAG
  order_patterns   — embed (product_id, month) → typical order qty
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"

_client = None
_alias_col = None
_pattern_col = None


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def _get_alias_collection():
    global _alias_col
    if _alias_col is None:
        client = _get_client()
        _alias_col = client.get_or_create_collection(
            name="product_aliases",
            metadata={"hnsw:space": "cosine"},
        )
        _seed_aliases()
    return _alias_col


def _seed_aliases():
    """Seed alias collection from SQLite aliases table on first run."""
    col = _alias_col
    if col.count() > 0:
        return
    try:
        from db.database import _conn
        with _conn() as conn:
            rows = conn.execute("SELECT alias, product_id FROM aliases").fetchall()
        if rows:
            col.upsert(
                documents=[r["alias"] for r in rows],
                ids=[f"alias_{i}" for i in range(len(rows))],
                metadatas=[{"product_id": r["product_id"]} for r in rows],
            )
            logger.info(f"Seeded {len(rows)} aliases into ChromaDB")
    except Exception as e:
        logger.warning(f"Alias seed failed: {e}")


def resolve_aliases(raw_names: list[str], threshold: float = 0.75) -> dict:
    """
    Given a list of raw product name strings (from OCR or voice),
    return a dict mapping each raw name → canonical product_id.

    Uses cosine similarity; returns None for names below threshold.
    """
    if not raw_names:
        return {}

    col = _get_alias_collection()
    result = {}

    for name in raw_names:
        if not name.strip():
            continue
        try:
            query_result = col.query(
                query_texts=[name],
                n_results=1,
                include=["metadatas", "distances"],
            )
            distance = query_result["distances"][0][0] if query_result["distances"] else 1.0
            similarity = 1 - distance   # cosine distance → similarity

            if similarity >= threshold:
                product_id = query_result["metadatas"][0][0].get("product_id")
                result[name] = product_id
                logger.debug(f"Alias resolved: '{name}' → {product_id} (sim={similarity:.2f})")
            else:
                result[name] = None
                logger.debug(f"No alias match for '{name}' (best sim={similarity:.2f})")
        except Exception as e:
            logger.warning(f"Alias lookup failed for '{name}': {e}")
            result[name] = None

    return result


def upsert_alias(alias: str, product_id: str):
    """Add a new alias mapping (called when owner confirms an unresolved name)."""
    col = _get_alias_collection()
    col.upsert(
        documents=[alias],
        ids=[f"alias_{alias.lower().replace(' ', '_')}"],
        metadatas=[{"product_id": product_id}],
    )


def get_order_pattern(product_id: str) -> dict:
    """
    Retrieve historical order pattern for a product.
    Returns avg_qty_cases and seasonality hints.
    Falls back to default if no history found.
    """
    try:
        client = _get_client()
        col = client.get_or_create_collection("order_patterns")
        result = col.query(
            query_texts=[product_id],
            n_results=3,
            include=["metadatas", "documents"],
        )
        if result["metadatas"] and result["metadatas"][0]:
            meta = result["metadatas"][0][0]
            return {
                "avg_qty_cases": meta.get("avg_qty_cases", 2),
                "last_qty_cases": meta.get("last_qty_cases", 2),
            }
    except Exception as e:
        logger.warning(f"Order pattern lookup failed for {product_id}: {e}")

    return {"avg_qty_cases": 2, "last_qty_cases": 2}


def store_order_pattern(product_id: str, qty_cases: int):
    """Update order pattern after a PO is approved."""
    try:
        client = _get_client()
        col = client.get_or_create_collection("order_patterns")
        from datetime import datetime
        col.upsert(
            documents=[f"{product_id} ordered {qty_cases} cases"],
            ids=[f"pattern_{product_id}_{datetime.now().strftime('%Y%m')}"],
            metadatas=[{
                "product_id": product_id,
                "avg_qty_cases": qty_cases,
                "last_qty_cases": qty_cases,
                "month": datetime.now().strftime("%Y-%m"),
            }],
        )
    except Exception as e:
        logger.warning(f"Failed to store order pattern: {e}")


def embed_receipt_chunk(text: str, metadata: dict):
    """Store a receipt text chunk for price history RAG."""
    try:
        client = _get_client()
        col = client.get_or_create_collection("receipt_chunks")
        import hashlib
        chunk_id = hashlib.md5(text.encode()).hexdigest()
        col.upsert(documents=[text], ids=[chunk_id], metadatas=[metadata])
    except Exception as e:
        logger.warning(f"Failed to embed receipt chunk: {e}")
