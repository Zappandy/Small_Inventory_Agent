Here's a handoff note summarizing everything on the react-refactor branch:

Handoff Note: react-refactor branch
Note: The branch name is misleading — this is a backend refactor, not a React/frontend change.

What changed (1 commit: 7df4742)
TL;DR
Replaced the LangGraph/Mistral-7B stack with smolagents + local Llama-3.2-3B via llama.cpp. The Gradio UI is unchanged visually, but every parsing handler now routes through a ToolCallingAgent first, with fallback to the original deterministic parsers.

Dependency overhaul (requirements.txt, pyproject.toml)
Removed: langgraph, langchain-core, chromadb, openai-whisper, sentencepiece, sacremoses, torch, torchaudio

Added: smolagents>=1.0, huggingface_hub>=0.25.0, llama-cpp-python[server]>=0.3.0, unsloth>=2024.12, trl>=0.12.0, datasets>=3.0.0

New: Agent layer (dukaan_saathi/agent/)
agent.py — A smolagents ToolCallingAgent backed by Llama-3.2-3B-Instruct running on port 8080 (OpenAI-compatible). Max 6 steps. The system prompt hard-bans direct DB writes — the agent can only call propose_inventory_update, and the owner must click Approve in the UI.

tools.py — @tool-decorated wrappers around existing parsers/services. A module-level _state dict (last_action, last_receipt_rows, last_raw_text) lets Gradio handlers retrieve structured results after agent.run() returns a plain string. Tools: get_inventory_snapshot, parse_stock_command_tool, extract_text_from_receipt_image, parse_receipt_text_tool, apply_correction_to_receipt, transcribe_audio_tool, draft_reorder_tool, propose_inventory_update.

New: LLM/llama.cpp integrations
llamacpp_llm.py — Low-level HTTP client for two model servers:

Port 8080 → base llama-3.2-3b (orchestrator)
Port 8082 → llama-3.2-3b-receipt (fine-tuned receipt parser)
Includes a stateful Session class (keeps inventory in system prompt, sliding 3-turn history) and a stateless call_llm(). Auto-retries on port 8080 if the receipt model's port is down.

llamacpp_receipt.py — Calls the fine-tuned model on port 8082 to parse OCR text into structured line items. Returns the same (rows, trace) signature as parsers.receipt_text.parse_receipt_text, so it's a drop-in backend. Falls back to the deterministic parser on any failure.

Config additions (dukaan_saathi/config.py)
Three new env vars:

RECEIPT_BACKEND — "llamacpp" (default) or "deterministic"
LLAMACPP_HOST — base URL for llama.cpp servers (default http://localhost)
HF_RECEIPT_MODEL_REPO — HF Hub repo ID for the fine-tuned GGUF (e.g. your-org/llama-3.2-3b-receipt-lora)
Gradio handlers updated (dukaan_saathi/ui/gradio_app.py)
handle_parse_command, handle_parse_receipt, and handle_extract_receipt_image all follow the same pattern:

Try the smolagents agent
Read structured output from agent_tools._state
On any exception, silently fall back to the original deterministic parser
Infrastructure changes (startup.sh)
Dropped: Mistral-7B (both base on port 8081 and receipt fine-tuned on port 8082)

Now starts two Llama-3.2-3B servers:

Port 8080 — llama-3.2-3b-instruct.Q4_K_M.gguf (orchestrator)
Port 8082 — llama-3.2-3b-receipt.Q4_K_M.gguf (fine-tuned parser; falls back to base model copy if HF_RECEIPT_MODEL_REPO is unset)
Install detection changed from checking for a binary path to python -c "import llama_cpp".

Fine-tuning pipeline (new)
scripts/finetune_receipt.py — Unsloth + TRL SFTTrainer LoRA fine-tune of Llama-3.2-3B-Instruct on receipt parsing examples. Exports a merged Q4_K_M GGUF and pushes both the adapter and GGUF to summerdevlin46/llama-3.2-3b-receipt-lora on HF Hub. Needs HF_TOKEN env var.

scripts/download_models.py — Idempotent downloader called by startup.sh. Downloads orchestrator from bartowski/Llama-3.2-3B-Instruct-GGUF; downloads fine-tuned receipt GGUF from HF_RECEIPT_MODEL_REPO (copies base if unset).

data/finetune/receipt_examples.jsonl — 6 training examples covering handwritten bills, printed tax invoices, and sales notes.

What's still needed before merge
HF_RECEIPT_MODEL_REPO must be set in the HF Space secrets for the fine-tuned model to load (otherwise the base model is used as a fallback for both ports, which degrades receipt parsing quality)
The fine-tuning script has only 6 examples — more data would improve accuracy
No tests cover the agent layer yet
