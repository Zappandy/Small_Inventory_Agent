# Plan: Modal Latency

## Current behaviour

Both Modal endpoints have 10–30 s cold-start on first request after idle:
- **OCR**: `POST /api/photo` → `MODAL_RECEIPT_ENDPOINT` (MiniCPM-V on T4)
- **ASR**: `POST /api/speech` → `MODAL_SPEECH_ENDPOINT` (Whisper on T4)

After warm, subsequent requests are 2–5 s. HF Spaces containers are always-on so the FastAPI side never cold-starts, but Modal containers scale to zero after ~5 min idle.

## Options

### Option A — Keep containers warm (recommended, low cost)

Add a lightweight `/ping` endpoint to each Modal service, then call it periodically from the Space.

**Modal side** (`modal_apps/receipt_vlm_service.py`, `modal_apps/speech_asr_service.py`):
```python
@app.function(...)
@modal.web_endpoint(method="GET")
def ping():
    return {"ok": True}
```

**Space side** — on dashboard page load, fire-and-forget warm-up requests:
```javascript
// static/app.js — after DOMContentLoaded
fetch(MODAL_RECEIPT_ENDPOINT.replace('/extract', '/ping'), {method:'GET'}).catch(() => {});
fetch(MODAL_SPEECH_ENDPOINT + '/ping', {method:'GET'}).catch(() => {});
```

But the Space frontend can't directly reach Modal endpoints (CORS + secrets exposure). Instead:
- Add `GET /api/warm` to `app.py` that pings both Modal endpoints server-side
- Call `/api/warm` from the page-load JS (fire-and-forget)

```python
@server.get("/api/warm")
async def api_warm():
    import threading, requests, os
    def _ping(url):
        try: requests.get(url, timeout=5)
        except Exception: pass
    for ep in [os.getenv("MODAL_RECEIPT_ENDPOINT",""), os.getenv("MODAL_SPEECH_ENDPOINT","")]:
        if ep:
            threading.Thread(target=_ping, args=(ep.rstrip("/")+"/ping",), daemon=True).start()
    return {"ok": True}
```

**JS** (static/app.js init):
```javascript
fetch("/api/warm").catch(() => {});
```

**Cost**: near zero — ping containers are ~50ms T4 compute.

### Option B — Minimum container count = 1

In Modal service definitions, set `min_containers=1`:
```python
@app.function(
    image=image,
    gpu="T4",
    min_containers=1,   # keeps one warm at all times
    ...
)
```

**Cost**: ~$0.50/day per endpoint to keep T4 warm 24/7. Acceptable for a demo but expensive long-term.

### Option C — Local fallback for speech (no Modal)

For speech specifically, `openai-whisper` can run CPU-only in the HF Space container (slower but no cold start).

```python
# dukaan_saathi/integrations/speech.py
def transcribe_audio(path: str):
    if os.getenv("MODAL_SPEECH_ENDPOINT"):
        return _transcribe_via_modal(path)
    return _transcribe_local(path)   # new: uses whisper CPU

def _transcribe_local(path: str):
    import whisper
    model = whisper.load_model("tiny")   # ~39 MB, ~5 s CPU
    result = model.transcribe(path)
    return result["text"], ["[asr] local whisper tiny"]
```

Add `openai-whisper` to `requirements.txt`. First call loads the model (~5 s), subsequent calls ~2–3 s CPU.

**Tradeoff**: adds ~200 MB to Docker image, slower than Modal GPU but zero cold start.

### Option D — Streaming / progress feedback (UX fix, not latency fix)

Don't reduce latency — make it feel faster. Show a progress indicator while waiting.

**Current state**: the Photo button disables on click, the voice button shows "Recording…". No indication of server-side processing time.

**Fix**:
- After file upload, show a spinner card: "Analysing receipt… this takes ~15 s first time"
- After ASR submit, show: "Transcribing… (~10 s first time)"
- Implemented in JS `applyResponse` — check for a `processing: true` field in response and render a skeleton card

**Files**: `static/app.js`, `templates/add.html`

## Recommended approach

1. **Short term**: Option D (spinner/progress) — 1 hour effort, immediate UX improvement
2. **Medium term**: Option A (warm-up ping via `/api/warm`) — 2 hour effort, reduces cold-start frequency
3. **Long term**: Option C (local Whisper fallback) for speech — makes ASR reliable without Modal dependency

## Priority

1. Add loading spinner to photo + voice upload (Option D) — do first, no Modal changes needed
2. Add `/api/warm` endpoint + JS fire-and-forget (Option A)
3. Evaluate `min_containers=1` cost vs. demo usage patterns (Option B)
