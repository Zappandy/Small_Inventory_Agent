# Codex Fine-tuning Handoff

This handoff captures the Modal fine-tuning run completed with Codex assistance
for the hackathon demo.

## What Codex Changed

Codex added traceability for the receipt model lifecycle:

- Static DAG documentation in `docs/pipeline_traceability.md`
- JSON run manifest helpers in `dukaan_saathi/traceability.py`
- Fine-tune and synthetic generation manifest recording in the Modal scripts
- Receipt inference manifests from the Modal receipt LLM client
- Inventory approval manifests after owner-approved stock changes
- Smoke coverage for manifest writing

Codex also patched two runtime issues found during the actual Modal run:

- Modal synthetic generation now asks for an output JSON object instead of a
  JSON string embedded inside JSON, which reduced malformed escaping.
- Modal receipt LLM training now uses `transformers.Trainer` directly instead
  of relying on the moving `trl.SFTTrainer` API.
- The deployed `/parse` endpoint now accepts a JSON body directly with
  FastAPI `Body(...)`.

## Fine-tuned Artifact

The fine-tuned receipt parser is a LoRA adapter stored in Modal:

```text
Modal app: dukaan-saathi-receipt-llm
Modal Volume: dukaan-saathi-receipt-lora
Adapter path inside Modal: /adapters/receipt-lora
Base model: unsloth/Llama-3.2-3B-Instruct-bnb-4bit
```

This is not a local GGUF artifact. Run inference through the Modal endpoint.

## Inference Endpoint

`scripts/modal_deploy.sh modal_apps/receipt_llm_service.py` deployed the parser
and wrote these values to `.env`:

```text
MODAL_RECEIPT_LLM_ENDPOINT=https://summerdevlin46--dukaan-saathi-receipt-llm-api.modal.run/parse
MODAL_RECEIPT_PARSER_ENDPOINT=https://summerdevlin46--dukaan-saathi-receipt-llm-api.modal.run/parse
```

Run the app against the fine-tuned parser with:

```bash
scripts/dev.sh --modal-llm
```

## Training Data

The successful run trained on:

```text
data/finetune/generated/receipt_examples_modal_synthetic.jsonl
records: 22
sha256: cd399ecec76ad301d47ed802c1ea42fc1a54cdcc4b95c4fb2d62f055a307b892
```

The generated dataset is ignored as a local runtime artifact. The manifest
records its path, count, and hash.

## Run Manifests

Successful synthetic generation:

```text
data/runs/modal-synthetic-20260613T150115Z.json
```

Successful fine-tune:

```text
data/runs/modal-finetune-20260613T151357Z.json
```

The fine-tune manifest reports:

```text
status: succeeded
adapter_volume: dukaan-saathi-receipt-lora
adapter_dir: /adapters/receipt-lora
max_steps: 60
epochs: 8
examples: 22
```

`data/runs/` is ignored because manifests are local runtime evidence.

## Verification

Health check confirmed the deployed endpoint loaded the adapter:

```json
{
  "ok": true,
  "app": "dukaan-saathi-receipt-llm",
  "base_model": "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
  "adapter_loaded": true,
  "adapter_dir": "/adapters/receipt-lora"
}
```

Direct parse verification returned:

```text
model: /adapters/receipt-lora
```

Required project check passed:

```text
uv run scripts/smoke_test.sh
Ran 23 tests
OK
```

## Demo Caveat

The adapter is demo-oriented and trained on a tiny dataset. It improves format
following for known receipt styles, but extracted fields can still be wrong.
The app must keep using the editable table plus owner approval before inventory
changes.

