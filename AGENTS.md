# Dukaan Saathi agent instructions

Use uv for all commands.

Run checks before finishing:
- scripts/smoke_test.sh
- uv run python app.py only when UI changes need manual testing

Do not commit secrets.
Do not modify .env.
Keep model runtime code in modal_apps/.
Keep Gradio app logic in dukaan_saathi/ui/.
Inventory writes must go through approval services.
Receipt model output must never update inventory directly.
