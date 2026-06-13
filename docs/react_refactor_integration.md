# React Refactor Integration Note

This is the reviewed, updated version of the local `NEW_AGENTS.md` handoff note.
The `react-refactor` branch name is misleading: the branch integrates a local
llama.cpp model stack and a smolagents tool-calling layer; it does not replace
the Gradio UI with React.

## Runtime Shape

- Llama.cpp is the default local model stack.
- Modal remains optional for remote model services, currently receipt image OCR
  and speech transcription.
- The Gradio app must only talk to Modal through thin HTTP clients in
  `dukaan_saathi/integrations/`.
- Model output can propose updates or populate editable receipt rows, but stock
  writes still require owner approval through `dukaan_saathi/services/inventory.py`.

## Agent Layer

- `dukaan_saathi/agent/agent.py` builds the smolagents `ToolCallingAgent`.
- `dukaan_saathi/agent/tools.py` wraps existing parsers and service reads.
- Agent state is reset before each UI agent run so stale tool output does not
  become a pending approval.
- Gradio handlers lazy-load the agent. If llama.cpp or smolagents is unavailable,
  command and receipt text handlers fall back to deterministic parsers.

## Model Services

- Port 8080 serves the Llama-3.2-3B orchestrator.
- Port 8082 serves the receipt parser model.
- Model files live in repo-local `models/`, which is ignored by git.
- Local app entrypoints are staged:
  - `scripts/dev.sh --deterministic` starts the app without model servers.
  - `scripts/dev.sh --llamacpp` downloads/starts llama.cpp servers and then starts the app.
  - `scripts/start_llamacpp.sh` starts only the model servers.
  - `scripts/run_app.sh --backend llamacpp|deterministic` starts only Gradio.
- `RECEIPT_BACKEND=llamacpp` is the default. Set
  `RECEIPT_BACKEND=deterministic` to force the rule-based parser.
- `HF_RECEIPT_MODEL_REPO` should point to the published fine-tuned GGUF repo.
  If unset, startup copies the base model for the receipt parser port.

## Remaining Follow-Ups

- Expand receipt fine-tuning data beyond the initial examples.
- Add mocked llama.cpp tests for successful agent output and malformed model
  responses.
- Decide whether benchmark result files should become tracked reports or stay
  local generated artifacts.
