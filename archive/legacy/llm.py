"""
LLM wrapper — calls the llama.cpp HTTP server running on localhost.

llama.cpp is started as a background process in the HF Space via startup.sh.
Each model is loaded as a separate server instance on different ports:

  Port 8080 — llama-3.2-3b-instruct.Q4_K_M.gguf   (orchestrator)
  Port 8081 — mistral-7b-instruct.Q4_K_M.gguf      (inventory, reorder, report)
  Port 8082 — mistral-7b-receipt-lora.Q4_K_M.gguf  (finetuned receipt parser)

All models are served via the OpenAI-compatible /v1/chat/completions endpoint.
"""

import json
import logging
from typing import Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

MODEL_PORTS = {
    "llama-3.2-3b":       8080,
    "mistral-7b":         8081,
    "mistral-7b-receipt": 8082,   # LoRA-merged GGUF
}

DEFAULT_MODEL = "mistral-7b"


class Session:
    """
    Stateful conversation session.

    Keeps the full inventory dict in the system prompt so the model always
    sees current stock.  Only the last `history_turns` exchanges are sent as
    message history — enough for follow-up questions without unbounded growth.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        system: str = "",
        inventory: Optional[dict] = None,
        history_turns: int = 3,
        **llm_kwargs,
    ):
        self.model = model
        self._base_system = system
        self.inventory: dict = inventory or {}
        self.history_turns = history_turns
        self.llm_kwargs = llm_kwargs
        self._recent: list[dict] = []

    # ------------------------------------------------------------------
    # Inventory management
    # ------------------------------------------------------------------

    def set_inventory(self, inventory: dict) -> None:
        """Replace the full inventory state."""
        self.inventory = inventory

    def update_inventory(self, updates: dict) -> None:
        """Merge updates into the inventory (shallow merge by SKU key)."""
        self.inventory.update(updates)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat(self, user: str) -> str:
        self._recent.append({"role": "user", "content": user})
        history = self._recent[-(self.history_turns * 2):]
        reply = _call_with_history(
            self.model, self._system_prompt(), history, **self.llm_kwargs
        )
        self._recent.append({"role": "assistant", "content": reply})
        return reply

    def reset_history(self) -> None:
        """Clear conversation history without touching the inventory."""
        self._recent.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        inventory_block = json.dumps(self.inventory, indent=2) if self.inventory else "empty"
        parts = [self._base_system] if self._base_system else []
        parts.append(f"Current inventory:\n{inventory_block}")
        return "\n\n".join(parts)


def _call_with_history(
    model: str,
    system: str,
    history: list[dict],
    max_tokens: int = 512,
    json_mode: bool = False,
    temperature: float = 0.1,
) -> str:
    port = MODEL_PORTS.get(model, MODEL_PORTS[DEFAULT_MODEL])
    url = f"http://localhost:{port}/v1/chat/completions"

    messages = ([{"role": "system", "content": system}] if system else []) + history

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]

    except urllib.error.URLError as e:
        logger.error(f"llama.cpp unreachable at port {port}: {e}")
        if port != MODEL_PORTS[DEFAULT_MODEL]:
            logger.warning(f"Retrying with default model on port {MODEL_PORTS[DEFAULT_MODEL]}")
            return _call_with_history(DEFAULT_MODEL, system, history, max_tokens, json_mode, temperature)
        return '{"error": "llama.cpp server unavailable"}'

    except (KeyError, json.JSONDecodeError) as e:
        logger.error(f"Unexpected response from llama.cpp: {e}")
        return '{"error": "malformed response"}'


def call_llm(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 512,
    json_mode: bool = False,
    temperature: float = 0.1,
) -> str:
    """
    Call llama.cpp HTTP server (single-turn, stateless).
    Returns the assistant message content string.
    Falls back to DEFAULT_MODEL if the requested model port is unavailable.
    """
    return _call_with_history(
        model, system,
        [{"role": "user", "content": user}],
        max_tokens=max_tokens,
        json_mode=json_mode,
        temperature=temperature,
    )
