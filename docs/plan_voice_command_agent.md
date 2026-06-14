# Plan: Voice Command Agent

## Current state (as of 2026-06-14)

The voice pipeline has two stages:
1. **Speech → text**: `POST /api/speech` → Modal ASR → transcript shown in voice tab
2. **Text → inventory action**: text box submit → `_h_voice_command` → `run_command_parse` → `parse_stock_command`

### Bugs fixed in this session
- **Field name mismatch**: `parse_stock_command` returned `{type, product_name, delta}` but `_h_voice_command` read `{action, product, quantity}`. Every parsed command showed "action: unknown". Fixed in `frontend_backend.run_command_parse` by normalising to the expected shape.
- **`set_stock` not handled**: handler only applied `add_stock`. Fixed to also apply `set_stock`.
- **`find_by_name` fuzzy match**: handler re-matched by name instead of using `product_id` already returned by parser. Fixed to use `product_id` directly.

### Remaining gaps

| Gap | Impact |
|-----|--------|
| Keyword-only intent detection | Only triggers on exact keywords (`add`, `received`, `khatam`, etc.). "Tomato stock lo 5 petti" won't parse — only "add tomato 5" would |
| No fuzzy product name matching in parser | `find_product` in storage.py does substring match; "tomatoe" or "Tamatar" won't resolve |
| Telugu / code-mix commands | Parser has a few Telugu markers (`అయిపోయింది`, `తక్కువ`) but no general Telugu NLU |
| Confirmation step | Parsed actions auto-apply without user confirmation. The "applied" line appears after the fact — user has no chance to review before write |
| Modal cold start | First ASR call after idle takes 10–30 s. No spinner or progress indicator makes it feel broken |

## Proposed agent: `VoiceCommandAgent`

### Option A — LLM-backed NLU (recommended)

Replace `parse_stock_command` with an LLM call to `Zappandy/dukaan-saathi-receipt-lora` (already on HF Hub) or a small instruct model.

**Prompt template:**
```
You are an inventory assistant for a kirana store.
Extract the inventory action from the owner's command.
Known products: {product_list}

Command: "{command}"

Reply with JSON only:
{"action": "add_stock"|"set_stock"|"mark_out_of_stock"|"unknown",
 "product_name": string or null,
 "quantity": number or null,
 "unit": string or null}
```

**Integration point**: `frontend_backend.run_command_parse` → call HF Inference API → parse JSON response → same normalised output shape.

**Fallback**: if LLM returns malformed JSON or confidence is low, fall back to current keyword parser.

**Files to change**:
- `frontend_backend.py` — add `_llm_command_parse(text, products)` using `requests.post` to HF Inference
- `dukaan_saathi/integrations/hf_inference_receipt.py` — reuse `parse_receipt_via_hf_inference` pattern
- `dukaan_saathi/config.py` — add `VOICE_LLM_BACKEND = os.getenv("VOICE_LLM_BACKEND", "keyword")` env var

### Option B — Fuzzy keyword + product name matching (no LLM)

Keep keyword parser but improve `find_product` to use:
- Levenshtein distance ≤ 2 for typos
- Language-agnostic stem matching ("tamatar" → "Tomato" via a small static mapping table)
- Fallback to category search

**Files to change**:
- `dukaan_saathi/storage.py` — improve `find_product` with fuzzy match (use `difflib.get_close_matches`)
- `dukaan_saathi/parsers/stock_command.py` — expand `ADD_STOCK_MARKERS` with Telugu variants

### Confirmation UX (applies to both options)

Currently, parsed commands auto-apply. A safer flow:

1. Parse → show "Parsed" card with action/product/quantity
2. Show **Confirm** button that dispatches `{action: "voice_apply", parsed: {...}}`
3. New handler `_h_voice_apply` writes inventory only on confirm

Add to `app.py`:
```python
def _h_voice_apply(state, params):
    pid = params.get("product_id")
    qty = params.get("quantity")
    action = params.get("action")
    ...
```

Add to `templates/add.html` in the `voice_result` block:
```html
{% if voice_result.action != "unknown" and not voice_result.applied %}
  <button onclick="kirana.quickAction('voice_apply', {
      action: '{{ voice_result.action }}',
      product_id: '{{ voice_result.product_id }}',
      quantity: {{ voice_result.quantity or 0 }}
  })">Apply to inventory</button>
{% endif %}
```

## Modal latency

See `docs/plan_modal_latency.md` for keep-warm strategies. Specific to voice:
- Ping `/api/status` on page load to warm the Modal ASR container
- Show a spinner while `POST /api/speech` is in-flight (currently the button disables but no spinner)

## Priority order

1. ✅ Fix field mismatch (done)
2. Add confirmation UX (medium effort, high safety value)
3. Fuzzy product name matching (low effort, handles most real-world misses)
4. LLM-backed NLU (high effort, needed for Telugu/code-mix)
5. Modal warm-up ping (low effort, improves perceived latency)
