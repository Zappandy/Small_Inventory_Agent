# React Refactor Integration Note

This is the reviewed, updated version of the local `NEW_AGENTS.md` handoff note.
The `react-refactor` branch name is misleading: the branch integrates a local
llama.cpp model stack and a lean ReAct-style tool router; it does not replace
the Gradio UI with React.

## Runtime Shape

- `hf_inference` is the default app backend for the public Hugging Face Space.
  It calls the fine-tuned model after that model is trained on Modal, merged,
  and pushed to Hugging Face Hub.
- Modal remains optional for remote model services: receipt image OCR, speech
  transcription, and an alternate hosted receipt parser endpoint.
- Llama.cpp is an optional fully local model stack.
- The Gradio app must only talk to Modal through thin HTTP clients in
  `dukaan_saathi/integrations/`.
- Model output can propose updates or populate editable receipt rows, but stock
  writes still require owner approval through `dukaan_saathi/services/inventory.py`.

## Agent Layer

- `dukaan_saathi/agent/react_agent.py` is the active Gradio agent path.
- It is a lean ReAct-style router with explicit `Thought`, `Action`, and
  `Observation` traces.
- `dukaan_saathi/agent/tools.py` wraps existing parsers and service reads.
- Tool state is reset before each ReAct run so stale tool output does not become
  a pending approval.
- `dukaan_saathi/agent/agent.py` still contains the heavier smolagents
  `ToolCallingAgent`, but it is no longer the primary Gradio path.

## Model Services

- Local app entrypoints are staged:
  - `scripts/dev.sh --hf-inference` starts the app against HF Inference API.
  - `scripts/dev.sh --modal-llm` starts the app against the Modal receipt parser endpoint.
  - `scripts/dev.sh --deterministic` starts the app without model servers.
  - `scripts/dev.sh --llamacpp` downloads/starts llama.cpp servers and then starts the app.
  - `scripts/start_llamacpp.sh` starts only the model servers.
  - `scripts/run_app.sh --backend hf_inference|modal_llm|llamacpp|deterministic`
    starts only Gradio.
- `RECEIPT_BACKEND=hf_inference` is the default. Set
  `RECEIPT_BACKEND=modal_llm` to use the Modal-hosted parser,
  `RECEIPT_BACKEND=llamacpp` for local model servers, or
  `RECEIPT_BACKEND=deterministic` to force the rule-based parser.
- `HF_RECEIPT_MODEL_REPO` should point to the published fine-tuned HF Hub model
  repo used by the HF Inference API.
- For llama.cpp only, port 8080 serves the Llama-3.2-3B orchestrator and port
  8082 serves the receipt parser model. Model files live in repo-local
  `models/`, which is ignored by git.
- `scripts/modal_finetune_receipt.sh` trains a LoRA adapter on Modal and stores
  it in a Modal Volume.
- `uv run modal run modal_apps/receipt_llm_service.py::push` merges that adapter
  and pushes the model to Hugging Face Hub for `hf_inference`.
- `scripts/modal_generate_receipt_examples.sh` uses a small instruct model on
  Modal to generate LLM-augmented receipt JSONL examples for fine-tuning.
- `scripts/generate_receipt_examples.py` remains a deterministic template
  generator for debugging/schema coverage only; prefer Modal LLM augmentation
  for training data expansion.

## Remaining Follow-Ups

- Expand receipt fine-tuning data beyond the initial examples.
- Add mocked llama.cpp tests for successful agent output and malformed model
  responses.
- Add mocked Modal parser tests for endpoint success and malformed JSON fallback.
- Decide whether benchmark result files should become tracked reports or stay
  local generated artifacts.
