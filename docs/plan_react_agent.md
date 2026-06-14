# Plan: Wire the ReAct Agent into the Live Frontend

## Why this matters

The ReAct agent layer already exists and is complete. It has:
- `dukaan_saathi/agent/react_agent.py` — `ReceiptReActAgent`, a hand-rolled Thought/Action/Observation router
- `dukaan_saathi/agent/tools.py` — 7 `@tool`-decorated functions wrapping every existing parser and integration
- `dukaan_saathi/agent/agent.py` — a heavier `ToolCallingAgent` backed by an LLM (currently wired to local llama.cpp, unused)

**None of it is called from the live app.** `app.py` bypasses the agent and calls parsers directly. This means:
- No Thought/Action/Observation trace is shown to the user for photo or voice flows
- The tools layer is dead weight in `requirements.txt` (`smolagents` is installed but never invoked)
- The orchestration logic lives scattered across `app.py`, `frontend_backend.py`, and individual integrations rather than in one composable place

Wiring the agent gives us visible AI reasoning in the UI for free — the trace already renders in `templates/add.html` for photo results.

---

## Current state of each file

### `react_agent.py` — deterministic ReAct router (no LLM required)

Three methods, each generating a `Thought/Action/Observation` string:

| Method | Tools called | Returns |
|--------|-------------|---------|
| `extract_receipt_image(path)` | `extract_text_from_receipt_image` → `parse_receipt_text_tool` | `ReactResult(trace, receipt_rows, raw_text)` |
| `parse_receipt_text(raw_text)` | `parse_receipt_text_tool` | `ReactResult(trace, receipt_rows)` |
| `parse_stock_command(command)` | `parse_stock_command_tool` | `ReactResult(trace, action)` |

The trace is a newline-joined string. The frontend expects `trace` as a `list[str]`. This needs one small fix.

### `tools.py` — the tool definitions

All tools are implemented and call real backend functions:
- `extract_text_from_receipt_image` → `modal_receipt._extract_receipt_result_with_modal`
- `parse_receipt_text_tool` → `hf_inference_receipt` / `receipt_text` / `modal_receipt_llm` (respects `RECEIPT_BACKEND`)
- `parse_stock_command_tool` → `stock_command.parse_stock_command`
- `transcribe_audio_tool` → `speech.transcribe_audio`
- `get_inventory_snapshot` → `storage.get_inventory`
- `draft_reorder_tool` → `services.reorder.draft_reorder`
- `propose_inventory_update` → formats proposal, stores in `_state` (no DB write)

### `agent.py` — `ToolCallingAgent` (LLM-backed)

Wired to `OpenAIServerModel` pointing at local llama.cpp port 8080. Not usable on HF Spaces. Needs to be re-pointed to HF Inference API.

---

## Integration plan

### Phase 1 — Wire `ReceiptReActAgent` to photo path (no LLM, immediate)

**Target**: `app.py:api_photo`

**Current flow**:
```python
ocr_result = _extract_receipt_result_with_modal(tmp_path)
rows, parser_trace = _parse_receipt_with_configured_backend(ocr_result.raw_text)
```

**New flow**:
```python
from dukaan_saathi.agent.react_agent import get_react_agent
result = get_react_agent().extract_receipt_image(tmp_path)
rows = result.receipt_rows or []
trace = result.trace.splitlines()   # convert string → list for template
```

The photo result `trace` list is already rendered in `templates/add.html` — the user will immediately see Thought/Action/Observation steps below the receipt rows. Zero template changes needed.

**Fix needed in `react_agent.py`**: Return `trace` as `list[str]` instead of a joined string, so it integrates cleanly with the existing `photo_result["trace"]` format.

```python
# react_agent.py — change _trace() and all methods
def _trace(self) -> list[str]:
    tools.reset_state()
    return ["Thought: Identify the user workflow and select the smallest safe tool chain."]

# In extract_receipt_image:
return ReactResult(trace=trace, raw_text=raw_text, receipt_rows=rows)
# where trace is now a list
```

Then in `ReactResult`:
```python
@dataclass
class ReactResult:
    trace: list[str]   # was: str
    action: dict[str, Any] | None = None
    receipt_rows: list[dict[str, Any]] | None = None
    raw_text: str | None = None
```

**Files changed**: `dukaan_saathi/agent/react_agent.py`, `app.py` (api_photo only)

---

### Phase 2 — Wire `ReceiptReActAgent` to voice path

**Target**: `app.py:_h_voice_command`

**Current flow** (after the field-name fix we just made):
```python
parsed = run_command_parse(text)   # calls parse_stock_command directly
```

**New flow**:
```python
result = get_react_agent().parse_stock_command(text)
# result.action = {type, product_id, product_name, delta/new_stock, ...}
# result.trace = list of Thought/Action/Observation strings
```

The voice result panel in `add.html` currently shows `action/product/quantity/applied` but not the trace. Add trace display to the voice result card (same pattern as photo result).

**Template change** (`templates/add.html`):
```html
{% if voice_result.trace %}
  <div class="trace-log">
    {% for line in voice_result.trace %}
      <div class="trace-line {% if line.startswith('Thought') %}trace-thought{% elif line.startswith('Action') %}trace-action{% else %}trace-obs{% endif %}">
        {{ line }}
      </div>
    {% endfor %}
  </div>
{% endif %}
```

**State change** in `_h_voice_command`:
```python
state["voice_result"] = {
    ...existing fields...,
    "trace": result.trace,  # now exposed to template
}
```

**Files changed**: `dukaan_saathi/agent/react_agent.py`, `app.py`, `templates/add.html`

---

### Phase 3 — Upgrade to `ToolCallingAgent` with HF Inference (LLM-backed)

Replace the llama.cpp `OpenAIServerModel` in `agent.py` with an HF Inference model so the `ToolCallingAgent` works on HF Spaces without local servers.

**Change in `agent.py`**:
```python
from smolagents import HfApiModel

def _build_agent() -> ToolCallingAgent:
    model = HfApiModel(
        model_id="Qwen/Qwen2.5-1.5B-Instruct",  # or dukaan-saathi-receipt-lora
        token=os.getenv("HF_TOKEN"),
    )
    return ToolCallingAgent(
        tools=[...all existing tools...],
        model=model,
        system_prompt=SYSTEM_PROMPT,
        max_steps=6,
    )
```

Using `Qwen/Qwen2.5-1.5B-Instruct` (1.5B, fast, free HF Inference tier) as the orchestrator. The receipt-specific parsing still goes through the fine-tuned `parse_receipt_text_tool` (which calls `hf_inference_receipt` with `dukaan-saathi-receipt-lora`). The LLM only drives tool selection.

**What this unlocks**:
- Voice commands in free-form Telugu/English ("yeh tamatar ka stock khatam ho gaya") without keyword matching
- Multi-step flows: "Add 5 kg of tomatoes and check if we need to reorder" — agent calls `parse_stock_command_tool` then `draft_reorder_tool` in sequence
- The full `agent.logs` trace is rendered in the UI

**API entry point change** — add a new handler for agent-mode commands:
```python
@server.post("/api/agent")
async def api_agent(payload: dict) -> dict:
    query = payload.get("query", "")
    agent = get_agent()   # from agent.py
    response = agent.run(query)
    trace = format_agent_trace(agent)
    # parse proposal from tools._state["last_proposal"]
    ...
```

Or route through the existing dispatch system with a new action `"agent_query"`.

---

### Phase 4 — Dashboard reorder insights via agent

Replace the static `"Inventory looks okay"` string in `run_analysis()` with a `ToolCallingAgent` call:

```python
agent.run("Check current inventory and draft reorder suggestions. Be concise.")
# agent calls get_inventory_snapshot → draft_reorder_tool → propose_inventory_update
# trace shows the reasoning chain
```

The reorder rows come from `tools._state["last_proposal"]` after the run. The narrative text comes from the agent's final answer string.

---

## Sequencing

| Phase | Effort | Unblocked by | Ships |
|-------|--------|-------------|-------|
| 1 — Photo path | 2 hrs | Nothing — no LLM | Immediately |
| 2 — Voice trace display | 1 hr | Phase 1 (trace list type) | Immediately after Phase 1 |
| 3 — ToolCallingAgent on HF | 4 hrs | Phase 1+2 done | After HF_TOKEN set in Space secrets |
| 4 — Dashboard insights | 2 hrs | Phase 3 | After Phase 3 stable |

**Start with Phase 1+2** — they require no new model, no new secrets, and no new dependencies. The deterministic `ReceiptReActAgent` already does the right thing; we just need to swap the call site and fix the trace type.

---

## Files touched in total

| File | Change |
|------|--------|
| `dukaan_saathi/agent/react_agent.py` | `trace: str` → `trace: list[str]`; minor return type fix |
| `app.py` | `api_photo`: replace direct calls with `agent.extract_receipt_image`; `_h_voice_command`: replace `run_command_parse` with `agent.parse_stock_command`; expose trace in voice_result |
| `dukaan_saathi/agent/agent.py` | Replace `OpenAIServerModel` with `HfApiModel` (Phase 3) |
| `templates/add.html` | Add trace display block inside voice result card |
| `frontend_backend.py` | `run_command_parse` can be removed once Phase 2 is done |

No new dependencies. `smolagents` and `huggingface_hub` are already in `requirements.txt`.
