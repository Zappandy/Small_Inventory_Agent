# Voice Command Status For Hugging Face Spaces

This document tracks the current voice command pipeline and the remaining work
that matters for a public Hugging Face Space.

## Current Pipeline

Voice has two separate stages:

```text
audio
-> POST /api/speech
-> dukaan_saathi/integrations/speech.py
-> MODAL_SPEECH_ENDPOINT or SPEECH_ASR_ENDPOINT
-> transcript
-> owner reviews/edits text
-> _h_voice_command
-> ReAct stock command tool
-> pending stock action
-> owner approves
-> _h_voice_apply
-> inventory write
```

The Modal ASR endpoint does speech-to-text only. ReAct starts after text exists.

## Completed

- Field names are normalized to the UI shape:
  - `action`
  - `product`
  - `product_id`
  - `quantity`
  - `unit`
  - `confidence`
  - `trace`
- `add_stock` and `set_stock` are both handled.
- The parser uses the returned `product_id`; it does not re-match blindly.
- Parsed commands no longer auto-apply.
- The UI shows a pending parsed action and requires **Approve stock change**.
- `_h_voice_apply` is the only custom FastAPI voice handler that writes stock.
- Modal cold-start copy is visible and `/api/warm` runs best-effort on page load.
- Safety tests cover parse-without-write and apply-with-write.

## Current Limitations

| Gap | Impact on HF Space |
|-----|--------------------|
| Deterministic command parser | Reliable for seeded/demo examples, weaker for natural Telugu/code-mix. |
| Limited product aliases | Commands such as "tamatar" need aliases or NLU to map to seeded products. |
| Modal ASR cold start | First request may take 10-30 seconds unless endpoint is warm. |
| Ephemeral SQLite | Approved stock changes may reset on Space rebuild unless persistent storage is enabled. |

## Recommended Next Steps

### 1. Keep deterministic parser as the default

For the hackathon/public Space, deterministic parsing is safer and easier to
debug. Continue using seeded examples that map to inventory:

```text
add Bun 12
set OBM stock 5
add Bingo 4
Happy Happy low
```

Do not bypass owner approval to make voice feel more automatic.

### 2. Add optional HF Inference voice NLU

If Telugu/code-mixed commands are important for the Space demo, add an optional
HF Inference path behind a feature flag:

```text
VOICE_LLM_BACKEND=keyword | hf_inference
HF_VOICE_NLU_MODEL_REPO=...
```

The output contract should stay the same:

```json
{
  "action": "add_stock|set_stock|mark_out_of_stock|unknown",
  "product_name": "string or null",
  "product_id": "string or null",
  "quantity": "number or null",
  "unit": "string or null",
  "confidence": "low|medium|high"
}
```

Fallback to the deterministic parser on malformed JSON, low confidence, missing
product match, timeout, or missing env vars.

### 3. Improve aliases before adding broad NLU

For a constrained demo, aliases often beat another model call:

- Add common transliterations for seeded products.
- Keep examples aligned to seeded inventory.
- Add parser tests for each new alias.

### 4. Preserve the approval gate

Any voice NLU path must still produce only a pending action:

```text
model/parser output -> pending action -> owner approval -> inventory write
```

No model, parser, or ReAct step may write inventory directly.

## Tests To Keep

- Voice parse does not change stock.
- Voice apply changes stock.
- Unknown/low-confidence commands do not expose an approval button.
- Malformed model output falls back or returns `unknown`.
- Missing Modal ASR endpoint produces a useful UI error, not a crash.
