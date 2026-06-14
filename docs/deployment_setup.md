# Deployment Setup: Modal → HF Space

This guide walks through deploying the three Modal model services and wiring
their endpoint URLs into the public Hugging Face Space as secrets.

---

## What gets deployed

| Service | Model | Env var | App name |
|---------|-------|---------|----------|
| Receipt OCR | MiniCPM-V 4.6 | `MODAL_RECEIPT_ENDPOINT` | `dukaan-saathi-receipt-vlm` |
| Speech ASR | Distil-Whisper small | `MODAL_SPEECH_ENDPOINT` | `dukaan-saathi-speech-asr` |
| Voice NLU | Qwen2.5-1.5B-Instruct | `MODAL_NLU_ENDPOINT` | `dukaan-saathi-command-nlu` |

All three are optional — the app falls back to deterministic parsers when any
endpoint is missing. Deploy whichever you want active on the Space.

---

## Part 1 — Prerequisites

### 1.1 Modal account and CLI

Create a free Modal account at https://modal.com if you do not have one.

Install the Modal CLI and log in:

```bash
uv add modal                  # adds to this project's venv
uv run modal setup            # opens a browser to authenticate
```

After `modal setup` completes, verify you are logged in:

```bash
uv run modal token show
```

You should see your workspace name (e.g., `zappandy`).

### 1.2 Hugging Face account

You need a Hugging Face account with write access to the Space at
`https://huggingface.co/spaces/Zappandy/Kirana_AI`. If this is your Space
you already have access.

---

## Part 2 — Deploy Modal services

Run each deploy command from the project root. Each command:

1. Deploys (or re-deploys) the Modal app
2. Fetches the generated endpoint URL from Modal
3. Writes it to your local `.env` file

### 2.1 Receipt image OCR (MiniCPM-V)

```bash
scripts/modal_deploy.sh modal_apps/receipt_vlm_service.py
```

When done, `.env` will contain:

```text
MODAL_RECEIPT_ENDPOINT=https://<workspace>--dukaan-saathi-receipt-vlm-api.modal.run/extract
```

Verify it is responding (replace with your actual URL from `.env`):

```bash
source scripts/_env.sh
curl "${MODAL_RECEIPT_ENDPOINT%/extract}/health"
```

Expected response:

```json
{"status": "ok", "model": "openbmb/MiniCPM-V-2_6"}
```

First call may take 30–60 seconds while the GPU container starts. Subsequent
calls within the `scaledown_window` are fast.

### 2.2 Speech transcription (Distil-Whisper)

```bash
scripts/modal_deploy.sh modal_apps/speech_asr_service.py
```

When done, `.env` will contain:

```text
MODAL_SPEECH_ENDPOINT=https://<workspace>--speech-transcribe.modal.run
```

Verify:

```bash
source scripts/_env.sh
SPEECH_HEALTH="${MODAL_SPEECH_ENDPOINT/speech-transcribe/speech-health}"
curl "$SPEECH_HEALTH"
```

Expected:

```json
{"status": "ok", "model": "distil-whisper/distil-small.en"}
```

### 2.3 Voice command NLU (Qwen2.5-1.5B-Instruct)

```bash
scripts/modal_deploy.sh modal_apps/command_nlu_service.py
```

When done, `.env` will contain:

```text
MODAL_NLU_ENDPOINT=https://<workspace>--nlu-extract.modal.run
```

Verify:

```bash
source scripts/_env.sh
curl -s -X POST "$MODAL_NLU_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"command": "add Bun 12"}' | python3 -m json.tool
```

Expected:

```json
{
  "intent": "add_stock",
  "product_name": "Bun",
  "quantity": 12,
  "unit": null,
  "confidence": "high",
  "model": "Qwen/Qwen2.5-1.5B-Instruct"
}
```

---

## Part 3 — Add secrets to the HF Space

The HF Space container does not read your local `.env` file. You must add each
endpoint URL as a Space secret through the Hugging Face web UI.

### 3.1 Open Space settings

1. Go to https://huggingface.co/spaces/Zappandy/Kirana_AI
2. Click the **Settings** tab (top of the Space page)
3. Scroll down to **Variables and secrets**

### 3.2 Add each secret

Click **New secret** for each of the following. Use the exact variable names
below — the app reads these from the environment at runtime.

| Secret name | Value |
|-------------|-------|
| `MODAL_RECEIPT_ENDPOINT` | the URL written to `.env` in step 2.1 |
| `MODAL_SPEECH_ENDPOINT` | the URL written to `.env` in step 2.2 |
| `MODAL_NLU_ENDPOINT` | the URL written to `.env` in step 2.3 |
| `HF_TOKEN` | your HF write token (only needed if `HF_RECEIPT_MODEL_REPO` is private) |
| `HF_RECEIPT_MODEL_REPO` | e.g. `Zappandy/dukaan-saathi-receipt-lora` |

Secrets are encrypted and only visible to the Space runtime — not to other
users or in the Space logs.

**Do not add** `DB_PATH` unless you have enabled persistent storage on the
Space. Without persistent storage, leave it unset and the DB stays
runtime-local (resets on restart).

### 3.3 Restart the Space

After adding secrets, click **Factory reset** or wait for the Space to rebuild
on its own. The new environment variables take effect on the next container
start.

To force an immediate rebuild, push any change to the Space remote:

```bash
git checkout --orphan _hf_tmp
git add -A
git commit -m "trigger rebuild"
git push space HEAD:main --force
git checkout main
git branch -D _hf_tmp
```

---

## Part 4 — Verify end-to-end on the Space

After the Space rebuilds:

1. Open the Space URL and wait for the app to finish loading
2. Go to **Voice** tab → type `add Bun 12` → click **Parse for approval**
   - The agent reasoning panel should show NLU steps if `MODAL_NLU_ENDPOINT` is set
3. Go to **Bill Desk** → upload a receipt photo
   - Cold start message appears while MiniCPM-V loads (~30 s first time)
   - Editable rows appear after extraction
4. Go to **Voice** → click **Transcribe with Modal** and upload a `.wav` file
   - Transcript fills in automatically

If any Modal service times out or returns an error, the app falls back to the
deterministic parser and shows a trace message explaining the fallback.

---

## Part 5 — Managing costs

Modal charges only for GPU time. Each service has a `scaledown_window=300` (5
minutes) — after 5 minutes of inactivity the container stops and you stop being
charged.

To stop all services immediately:

```bash
uv run modal app stop dukaan-saathi-receipt-vlm || true
uv run modal app stop dukaan-saathi-speech-asr  || true
uv run modal app stop dukaan-saathi-command-nlu || true
uv run modal app list
```

Look for `Tasks 0` in the output to confirm containers are stopped.

To redeploy after stopping (same commands as Part 2):

```bash
scripts/modal_deploy.sh modal_apps/receipt_vlm_service.py
scripts/modal_deploy.sh modal_apps/speech_asr_service.py
scripts/modal_deploy.sh modal_apps/command_nlu_service.py
```

The endpoint URLs do not change between deploys, so no HF Space secret update
is needed unless you deploy under a different workspace.

---

## Troubleshooting

**`modal setup` hangs or fails**
Run `uv run modal token show`. If it shows no token, re-run `uv run modal setup`
and complete the browser authentication flow.

**Deploy command fails with "app not found"**
Check you are in the project root (`ls modal_apps/` should list the service
files) and that `uv` has Modal installed (`uv run modal --version`).

**HF Space shows no NLU trace after rebuild**
Confirm the secret name is exactly `MODAL_NLU_ENDPOINT` (no spaces, correct
case). Check the Space logs (Settings → Logs) for any startup errors.

**`curl` health check returns 502 or times out**
The container is cold-starting. Wait 30–60 seconds and retry. Modal T4 GPU
containers take longer on first cold start because the model weights are
downloaded into the container volume.

**Endpoint URL has extra `/extract` suffix**
The `write_modal_endpoint.py` script derives the URL from the deployed function.
If it appends a route that the endpoint doesn't use, edit `.env` and the HF
Space secret to remove the suffix. Test the corrected URL with `curl` before
updating the secret.
