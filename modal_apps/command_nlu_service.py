from __future__ import annotations

import json

import modal
from fastapi import Request


APP_NAME = "dukaan-saathi-command-nlu"
MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

SYSTEM_PROMPT = """\
You are a kirana store inventory assistant. Extract the inventory action from the owner's command.
The owner manages a small Indian grocery store and may speak in English, Telugu, or mixed language.

Return ONLY valid JSON — no markdown, no explanation:
{
  "intent": "add_stock" | "set_stock" | "mark_low" | "mark_out" | "unknown",
  "product_name": "<product name in English, title-cased>" | null,
  "quantity": <number> | null,
  "unit": "kg" | "g" | "ml" | "l" | "piece" | "pack" | "unit" | null,
  "confidence": "high" | "medium" | "low"
}

Intent meanings:
- add_stock: owner received new stock, should increase quantity
- set_stock: owner is setting an exact stock level
- mark_low: product is running low (treat as set_stock to 1)
- mark_out: product is out / finished / khatam (treat as set_stock to 0)
- unknown: cannot determine intent

Examples:
Command: "add Bun 12"
{"intent": "add_stock", "product_name": "Bun", "quantity": 12, "unit": null, "confidence": "high"}

Command: "set OBM stock 5"
{"intent": "set_stock", "product_name": "OBM", "quantity": 5, "unit": null, "confidence": "high"}

Command: "Happy Happy low"
{"intent": "mark_low", "product_name": "Happy Happy", "quantity": null, "unit": null, "confidence": "high"}

Command: "biscuits khatam"
{"intent": "mark_out", "product_name": "Biscuits", "quantity": null, "unit": null, "confidence": "high"}

Command: "received 20 soap bars"
{"intent": "add_stock", "product_name": "Soap Bars", "quantity": 20, "unit": null, "confidence": "high"}

Command: "Add 10 oranges."
{"intent": "add_stock", "product_name": "Oranges", "quantity": 10, "unit": null, "confidence": "high"}

Command: "toor dal 2 bags received from Ramesh"
{"intent": "add_stock", "product_name": "Toor Dal", "quantity": 2, "unit": "pack", "confidence": "high"}

Command: "ఈ రోజు 20 kg బంగాళదుంపలు వచ్చాయి"
{"intent": "add_stock", "product_name": "Bangaladumpa", "quantity": 20, "unit": "kg", "confidence": "high"}

Command: "parle tiffin out of stock"
{"intent": "mark_out", "product_name": "Parle Tiffin", "quantity": null, "unit": null, "confidence": "high"}
"""

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]",
        "torch",
        "transformers>=4.45.0",
        "accelerate",
    )
)

app = modal.App(APP_NAME, image=image)

_MODEL = None
_TOKENIZER = None
_DEVICE = "unknown"


def _load_model():
    global _MODEL, _TOKENIZER, _DEVICE

    if _MODEL is not None:
        return _MODEL, _TOKENIZER

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if _DEVICE == "cuda" else torch.float32

    _TOKENIZER = AutoTokenizer.from_pretrained(MODEL_ID)
    _MODEL = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=dtype,
        device_map="auto",
    )
    _MODEL.eval()
    return _MODEL, _TOKENIZER


def _extract_slots(command: str) -> dict:
    import torch

    model, tokenizer = _load_model()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Command: {command}"},
    ]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = output_ids[0][inputs["input_ids"].shape[1]:]
    raw = tokenizer.decode(generated, skip_special_tokens=True).strip()

    # Strip markdown fences if the model adds them despite the prompt
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        slots = json.loads(raw)
    except ValueError:
        slots = {
            "intent": "unknown",
            "product_name": None,
            "quantity": None,
            "unit": None,
            "confidence": "low",
            "parse_error": raw[:200],
        }

    slots.setdefault("intent", "unknown")
    slots.setdefault("product_name", None)
    slots.setdefault("quantity", None)
    slots.setdefault("unit", None)
    slots.setdefault("confidence", "low")
    return slots


@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    scaledown_window=300,
)
@modal.fastapi_endpoint(method="GET", label="nlu-health")
def health():
    _load_model()
    return {"status": "ok", "app": APP_NAME, "model": MODEL_ID, "device": _DEVICE}


@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    scaledown_window=300,
)
@modal.fastapi_endpoint(method="POST", label="nlu-extract")
async def extract(request: Request):
    body = await request.json()
    command = str(body.get("command") or "").strip()

    if not command:
        return {
            "intent": "unknown",
            "product_name": None,
            "quantity": None,
            "unit": None,
            "confidence": "low",
            "model": MODEL_ID,
            "error": "No command provided.",
        }

    slots = _extract_slots(command)
    slots["model"] = MODEL_ID
    return slots
