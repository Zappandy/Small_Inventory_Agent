# Audit: Half-baked Features & Backend Gaps

Audit date: 2026-06-14. Covers all pages and action handlers.

---

## ✅ Working end-to-end

| Feature | Path |
|---------|------|
| Add product (manual form) | `add_product` → `kirana_db.add_product` → DB |
| Inventory list + filters | `filter_inventory` / `navigate:inventory` → `db.get_all_products` |
| Update stock (after PID fix) | `update_stock` → `db.adjust_stock` → stock_ledger |
| Record sale | `record_sale` → `db.record_sale` → stock_ledger + sales table |
| Delete product | `delete_product` → `db.delete_product` |
| Analytics — category mix | `_ctx_analytics` → `_build_categories()` from DB |
| Analytics — top sellers | `_ctx_analytics` → `db.get_top_sellers()` from sales table |
| Seasonal forecast | `_ctx_seasonal` → `seasonal_calendar.py` (deterministic) |
| Settings save | `save_settings` → `db.set_setting` |
| Dashboard KPIs | `_ctx_dashboard` → `db.get_summary()` |
| Dashboard pulse chart | `_ctx_dashboard` → sales ledger revenue aggregation |
| Photo OCR → rows | `POST /api/photo` → Modal MiniCPM-V → receipt parser → rows |
| Apply receipt row | `apply_receipt_row` → `db.adjust_stock` or `db.add_product` |
| Speech ASR | `POST /api/speech` → Modal Whisper → transcript |
| Voice command (after fix) | `voice_command` → `parse_stock_command` → `db.adjust_stock` |
| Orders list | `filter_orders` → `db.get_all_orders` |
| Orders approve/reject | `approve_order` / `reject_order` → `db.update_order_status` |

---

## ⚠️ Half-baked — handler exists but has no real backend

### 1. Dashboard "Add to order" button

**File**: `app.py:_h_add_to_order`
**Current**: Shows toast "Queued N kg of Tomato for the next order." No DB write, no order row created.
**Expected**: Create a `pending` order row in `orders` table via `db.insert_orders`.

**Fix**:
```python
def _h_add_to_order(state, params):
    pid = params.get("pid")
    try:
        qty = float(params.get("qty"))
    except (TypeError, ValueError):
        return state, "danger|Could not queue this reorder"
    p = db.get_product(pid)
    if not p:
        return state, "danger|Product not found"
    db.insert_orders([{
        "product_id": pid,
        "product_name": p["name"],
        "qty_needed": qty,
        "unit": p["unit"],
        "reason": "Manual reorder from dashboard",
        "ai_confidence": 0.95,
    }])
    state["page"] = "orders"
    state["orders_filter"] = "pending"
    return state, f"success|Reorder queued for {p['name']}"
```

---

### 2. Dashboard "Offer to route" button

**File**: `app.py:_h_offer_to_route`
**Current**: Shows toast "Liquidation offer drafted for {name}." No backend action.
**Expected**: Either (a) create a draft order of type "liquidation" in orders table, or (b) stub route to a future Liquidation Agent.

**Interim fix** (phase 1 — record intent):
```python
def _h_offer_to_route(state, params):
    pid = params.get("pid")
    p = db.get_product(pid)
    if not p:
        return state, "danger|Product not found"
    db.insert_orders([{
        "product_id": pid,
        "product_name": p["name"],
        "qty_needed": p["quantity"],
        "unit": p["unit"],
        "reason": "Liquidation route offer — near expiry or overstock",
        "ai_confidence": 0.7,
    }])
    state["page"] = "orders"
    state["orders_filter"] = "pending"
    return state, f"success|Liquidation offer logged for {p['name']}"
```

**Phase 2**: `docs/plan_liquidation_agent.md` — route offer via WhatsApp/SMS to supplier contact.

---

### 3. Dashboard AI insights text

**File**: `frontend_backend.run_analysis`
**Current**: Returns static strings regardless of actual inventory state:
- `"Inventory looks okay against current reorder thresholds."` (even if 5 items are critically low)
- `"Seasonal recommendations are available in the Seasonal page."`
- `"Review expiring-stock cards for near-expiry items."`

The dashboard template renders these in an AI insights panel (`.ai-card`). Users see the same text every time.

**Why it's static**: `run_analysis` calls `draft_reorder()` for the order suggestions, but the narrative text is hardcoded. There's no LLM call for the insights prose.

**Fix options**:
- **Option A (no LLM)**: Generate deterministic prose from DB state.
  ```python
  low = db.get_low_stock()
  expiring = db.get_expiring_soon(7)
  inventory_msg = (
      f"{len(low)} item(s) critically low: {', '.join(p['name'] for p in low[:3])}"
      if low else "All items above minimum stock."
  )
  ```
- **Option B (LLM)**: Pass inventory summary to HF Inference model, get a 2–3 sentence summary.

See `docs/plan_dashboard_insights_agent.md`.

---

### 4. Float quantity truncation

**File**: `kirana_db.py:adjust_stock` and `add_product`; `dukaan_saathi/storage.py:apply_stock_delta`
**Current**: `delta=int(delta)` — 0.5 kg becomes 0, 1.7 kg becomes 1.
**Root cause**: `stock_ledger.delta` column is `INTEGER NOT NULL`.

**Fix options**:
- **Option A (schema change)**: Alter `stock_ledger.delta` to `REAL`. Requires a migration.
- **Option B (scale factor)**: Store `delta * 1000` as integer, display as `/ 1000`. Lossy but no migration.
- **Option C (round instead of truncate)**: `round(delta)` instead of `int(delta)` — at least 0.5 → 1 instead of 0.

**Recommended**: Option C as immediate fix (1 line in `kirana_db.py`), Option A as proper fix when a migration is warranted.

**Files**: `kirana_db.py` lines 338, 409; `dukaan_saathi/storage.py` line 624.

---

### 5. Receipt row `matched_product_id` always None

**File**: `dukaan_saathi/parsers/receipt_text.py` and `dukaan_saathi/integrations/modal_receipt.py`
**Current**: The receipt parser returns rows with `matched_product_id: None` — no attempt to match raw product names against existing inventory.
**Impact**: Clicking "Apply" on every receipt row always creates a NEW product instead of adding stock to an existing one (if Tomato already exists, applying a Tomato receipt row creates a duplicate "Tomato").

**Fix**: After parsing receipt rows, run `db.find_by_name(row["product_raw"])` and populate `matched_product_id` if a confident match is found. Show as a suggestion in the receipt row UI.

**Files**: `app.py:api_photo` (add a matching pass after parsing), `templates/add.html` (show match badge per row).

---

### 6. Orders page — no "Reorder" action

**File**: `templates/orders.html`
**Current**: Orders can be Approved or Rejected. Approved orders have no further action (no email, no WhatsApp, no inventory write).
**Expected**: Approving an order should at minimum update the product's `target_stock` or add to stock when goods arrive.

**Fix**: Add a "Mark Received" button on approved orders that dispatches `apply_receipt_row` or `update_stock` for the ordered quantity.

---

### 7. Analytics — no date range selector

**Current**: Analytics shows "Top sellers · last 30 days" hardcoded. `get_top_sellers(n=10, days=30)` is hardcoded.
**Fix**: Add a filter to the analytics page (`7d`, `30d`, `90d`) and pass `days` param through the state.

---

---

### 8. Modal cold-start latency (UX gap, not a bug)

Both Modal endpoints have 10–30 s cold start after ~5 min idle:
- OCR: `POST /api/photo` → `MODAL_RECEIPT_ENDPOINT`
- ASR: `POST /api/speech` → `MODAL_SPEECH_ENDPOINT`

**Short-term fix (1 hr)**: Add a loading spinner/progress hint to the photo and voice buttons so the wait feels intentional rather than broken. Currently the button disables but there is no server-side progress indication.

**Medium-term fix (2 hrs)**: Add `GET /api/warm` to `app.py` that fire-and-forgets a HEAD request to both Modal endpoints, and call it on page load from JS. This keeps containers warm without user interaction.

```python
@server.get("/api/warm")
async def api_warm():
    import threading, requests, os
    def _ping(url):
        try: requests.head(url, timeout=5)
        except Exception: pass
    for ep in [os.getenv("MODAL_RECEIPT_ENDPOINT",""), os.getenv("MODAL_SPEECH_ENDPOINT","")]:
        if ep:
            threading.Thread(target=_ping, args=(ep,), daemon=True).start()
    return {"ok": True}
```

JS in `static/app.js` init: `fetch("/api/warm").catch(() => {});`

**Long-term**: `min_containers=1` on Modal functions keeps a T4 always warm (~$0.50/day per endpoint).

---

## Priority matrix

| Issue | Effort | Impact | Priority |
|-------|--------|--------|----------|
| ReAct agent wired to photo+voice | Medium | Very High | P0 — see plan_react_agent.md |
| "Add to order" writes to DB | Low | High | P1 |
| Float quantity (round fix) | Trivial | Medium | P1 |
| Receipt row product matching | Medium | High | P1 |
| Modal loading spinner | Low | Medium | P1 |
| AI insights deterministic prose | Low | Medium | P2 |
| "Offer to route" → orders table | Low | Medium | P2 |
| Orders "Mark Received" flow | Medium | High | P2 |
| `/api/warm` keep-warm endpoint | Low | Medium | P2 |
| Analytics date range filter | Low | Low | P3 |
| AI insights LLM prose | High | Medium | P3 |

## Related plans

- ReAct agent integration (P0): `docs/plan_react_agent.md`
- Voice command NLU: `docs/plan_voice_command_agent.md`
- Dashboard LLM insights: `docs/plan_dashboard_insights_agent.md` (TBD)
- Liquidation agent: `docs/plan_liquidation_agent.md` (TBD)
