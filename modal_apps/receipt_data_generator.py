from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import modal


APP_NAME = "dukaan-saathi-receipt-data-generator"
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

app = modal.App(APP_NAME)

model_cache = modal.Volume.from_name(
    "dukaan-saathi-receipt-data-generator-cache",
    create_if_missing=True,
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "accelerate>=0.34.0",
        "torch",
        "transformers>=4.45.0",
    )
    .env({"HF_HOME": "/model_cache"})
)


SYSTEM_PROMPT = """You generate high-quality synthetic OCR receipt training examples for an Indian kirana (corner store) inventory parser.

Return ONLY a JSON array. No markdown. No prose. Arithmetic must be correct: every item total = qty * unit_cost, subtotal = sum of totals, net_total = subtotal - discount + gst.

Each array item must have:
- "input": noisy receipt text as one string (use \\n for newlines)
- "output": a JSON object

The output object must have this shape:
{
  "supplier": string,
  "invoice_no": string or null,
  "date": "YYYY-MM-DD",
  "items": [
    {
      "product_raw": string,
      "qty_cases": integer,
      "qty_units": integer,
      "unit_cost": number,
      "total": number
    }
  ],
  "subtotal": number,
  "discount": number,
  "gst": number,
  "net_total": number
}

Receipt format variety (use ALL of these across examples):
1. Handwritten supplier bill: "SUPPLIER\\nNo. 1234  Date: 5/6/26\\nProduct  QTY X RATE = TOTAL\\nSubtotal NNN\\nDiscount NNN\\nTotal NNN"
2. Printed GST invoice: "SUPPLIER\\nGSTIN: 36XXXXX\\nBill Date: DD/MM/YYYY\\n1 PRODUCT  QTY: N/0  RATE: N.NN  NET: N.NN\\nGROSS SALES: NNN\\nSCHEMES: NNN\\nCGST: NNN  SGST: NNN\\nNET AMOUNT: NNN"
3. Handwritten tally note (messy, abbreviated): "Supplier - DD/MM\\nabbrev  QTYxRATE  TOTAL\\nTotal NNN"
4. Tabular format: "SUPPLIER\\nInvoice: INV-001\\n1  Product  QTY N  RATE N  AMT N\\nGross: NNN  Disc: NNN  Net: NNN"
5. Retail purchase note: "SUPPLIER\\nBill: NNN\\nProduct  N pkt  @RATE  TOTAL\\nSub Total: NNN  Disc @ N%: NNN  Net: NNN"

Indian product names to use: Parle-G, Bingo(C), Bingo Mad Angles, Lays Classic, Happy Happy 27.5G, Kurkure, OBM, Bourbon Biscuit, Monaco Salted, Krack Jack, Hide & Seek Choco, Sunfeast Dark Fantasy, Haldiram Bhujia, Lijjat Papad, pav, brd (bread), milk bread, cake slice, Parle Monaco.

For qty_cases/qty_units: handwritten bills use qty_cases=qty_units=N (same). Printed invoices use qty_cases=N, qty_units=N*pack_size (e.g. 5 cases of 24 = 120 units). Tally notes use qty_cases=0, qty_units=N.

Keep discount=0 for tally notes. Use discount 5-15% for handwritten bills and tabular/retail formats. Use gst=5% of subtotal only for printed GST invoices (others gst=0).
"""


def _load_examples(examples_jsonl: str) -> list[dict[str, str]]:
    return [
        json.loads(line)
        for line in examples_jsonl.splitlines()
        if line.strip()
    ]


def _seed_block(seed_examples: list[dict[str, str]], limit: int = 4) -> str:
    selected = seed_examples[:limit]
    return "\n\n".join(json.dumps(example, ensure_ascii=False) for example in selected)


def _extract_json_array(text: str) -> list[Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("[")
    end = stripped.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found in model output")

    return json.loads(stripped[start:end + 1])


def _validate_training_example(example: Any) -> dict[str, str]:
    if not isinstance(example, dict):
        raise ValueError("Example must be an object")

    receipt_input = example.get("input")
    output_value = example.get("output")
    if not isinstance(receipt_input, str) or not receipt_input.strip():
        raise ValueError("Example input must be non-empty text")

    if isinstance(output_value, dict):
        output_text = json.dumps(output_value, ensure_ascii=False)
    elif isinstance(output_value, str):
        output_text = output_value
    else:
        raise ValueError("Example output must be a JSON string or object")

    parsed = json.loads(output_text)
    if not isinstance(parsed.get("items"), list) or not parsed["items"]:
        raise ValueError("Example output must include at least one item")

    for item in parsed["items"]:
        for field in ("product_raw", "qty_cases", "qty_units", "unit_cost", "total"):
            if field not in item:
                raise ValueError(f"Item missing field: {field}")

    return {
        "input": receipt_input.strip(),
        "output": json.dumps(parsed, ensure_ascii=False),
    }


def _dedupe_examples(examples: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for example in examples:
        key = example["input"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(example)
    return unique


def _prompt(seed_examples: list[dict[str, str]], count: int, variation_seed: int) -> str:
    return f"""Generate {count} new synthetic training examples.

Do not copy the seed examples. Use them only to learn the task shape.
Variation seed: {variation_seed}

Seed examples:
{_seed_block(seed_examples)}
"""


@app.function(
    image=image,
    gpu="T4",
    timeout=30 * 60,
    secrets=[modal.Secret.from_dotenv()],
    volumes={"/model_cache": model_cache},
)
def generate_receipt_examples_with_model(
    seed_examples_jsonl: str,
    count: int = 48,
    model_id: str = DEFAULT_MODEL_ID,
    batch_size: int = 4,
) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    seed_examples = _load_examples(seed_examples_jsonl)
    tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir="/model_cache")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype="auto",
        device_map="auto",
        cache_dir="/model_cache",
    )
    model.eval()

    generated: list[dict[str, str]] = []
    attempts = 0
    max_attempts = max(4, (count // max(batch_size, 1)) * 4)

    while len(generated) < count and attempts < max_attempts:
        attempts += 1
        remaining = count - len(generated)
        this_batch = min(batch_size, remaining)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(seed_examples, this_batch, attempts)},
        ]
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=5120,
                do_sample=True,
                temperature=0.8,
                top_p=0.92,
            )
        text = tokenizer.decode(
            output_ids[0][inputs.input_ids.shape[-1]:],
            skip_special_tokens=True,
        )

        try:
            raw_examples = _extract_json_array(text)
            before = len(generated)
            for raw_example in raw_examples:
                try:
                    generated.append(_validate_training_example(raw_example))
                except Exception as exc:
                    print(f"Skipping invalid example: {exc}")
            generated = _dedupe_examples(generated)
            added = len(generated) - before
            print(f"Attempt {attempts}: +{added} valid examples → {len(generated)}/{count} total")
        except Exception as exc:
            print(f"Generation attempt {attempts} failed: {exc}")

    if len(generated) < count:
        raise RuntimeError(f"Generated {len(generated)} valid examples; requested {count}")

    return {
        "model": model_id,
        "requested": count,
        "generated": generated[:count],
        "attempts": attempts,
    }


@app.local_entrypoint()
def generate(
    dataset_path: str = "data/finetune/receipt_examples.jsonl",
    output_path: str = "data/finetune/generated/receipt_examples_modal_synthetic.jsonl",
    count: int = 48,
    model_id: str = DEFAULT_MODEL_ID,
    batch_size: int = 8,
    include_base: bool = True,
):
    base_text = Path(dataset_path).read_text()
    result = generate_receipt_examples_with_model.remote(
        seed_examples_jsonl=base_text,
        count=count,
        model_id=model_id,
        batch_size=batch_size,
    )

    generated = result["generated"]
    examples = (_load_examples(base_text) if include_base else []) + generated
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(example, ensure_ascii=False) for example in examples) + "\n"
    )
    print(f"Wrote {len(examples)} examples to {output}")
    print(json.dumps({k: v for k, v in result.items() if k != "generated"}, indent=2))
