# Dukaan Saathi agent instructions

Use uv for all Python commands.

Do not commit secrets or local runtime files:
- .env
- Modal tokens
- Hugging Face tokens
- data/*.db
- __pycache__/
- .venv/

Run checks before finishing:
- scripts/smoke_test.sh

Architecture rules:
- Gradio UI lives in dukaan_saathi/ui/.
- Inventory writes must go through dukaan_saathi/services/inventory.py.
- Receipt model output must never update inventory directly.
- Receipt extraction must populate an editable table first.
- Owner approval is required before stock changes.
- Modal model services live in modal_apps/.
- Keep the app-side Modal integration as a thin HTTP client.
- Do not remove Modal scripts, benchmark scripts, AGENTS.md, or .env.example.

Review guidelines:
- Flag any code path that bypasses owner approval before stock changes.
- Flag secrets, tokens, or local DB files being committed.
- Flag model inference added directly to the Gradio app runtime.
- Prefer small, reviewable changes over broad rewrites.
