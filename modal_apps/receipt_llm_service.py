from __future__ import annotations

import json
import time
from pathlib import Path

import modal


APP_NAME = "dukaan-saathi-receipt-llm"
BASE_MODEL = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
ADAPTER_DIR = Path("/adapters/receipt-lora")

SYSTEM_PROMPT = (
    "You are a receipt parser for an Indian convenience store. "
    "Extract all line items from the receipt text. "
    "Return ONLY valid JSON with this structure: "
    '{"supplier": "...", "invoice_no": "...", "date": "YYYY-MM-DD", '
    '"items": [{"product_raw": "...", "qty_cases": 0, "qty_units": 0, '
    '"unit_cost": 0.0, "total": 0.0}], '
    '"subtotal": 0.0, "discount": 0.0, "gst": 0.0, "net_total": 0.0}. '
    "No markdown, no explanation."
)

INSTRUCTION_TEMPLATE = """### Instruction:
{system}

### Input:
{input}

### Response:
{output}"""

app = modal.App(APP_NAME)

model_cache = modal.Volume.from_name(
    "dukaan-saathi-receipt-llm-cache",
    create_if_missing=True,
)
adapter_volume = modal.Volume.from_name(
    "dukaan-saathi-receipt-lora",
    create_if_missing=True,
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "fastapi[standard]",
        "accelerate>=0.34.0",
        "datasets>=3.0.0",
        "huggingface_hub>=0.25.0",
        "peft>=0.12.0",
        "torch",
        "transformers>=4.45.0",
        "unsloth>=2024.12",
        "bitsandbytes",
    )
    .env({"HF_HOME": "/model_cache"})
)


def _load_examples(examples_jsonl: str) -> list[dict]:
    return [
        json.loads(line)
        for line in examples_jsonl.splitlines()
        if line.strip()
    ]


def _build_dataset(examples_jsonl: str):
    from datasets import Dataset

    examples = _load_examples(examples_jsonl)
    records = [
        {
            "text": INSTRUCTION_TEMPLATE.format(
                system=SYSTEM_PROMPT,
                input=example["input"],
                output=example["output"],
            )
        }
        for example in examples
    ]
    return Dataset.from_list(records)


@app.function(
    image=image,
    gpu="T4",
    timeout=60 * 60,
    volumes={
        "/model_cache": model_cache,
        "/adapters": adapter_volume,
    },
)
def finetune_receipt_lora(
    examples_jsonl: str,
    max_steps: int = 30,
    num_train_epochs: int = 8,
    learning_rate: float = 2e-4,
) -> dict:
    import torch
    from transformers import Trainer, TrainingArguments
    from unsloth import FastLanguageModel

    print(f"Loading base model: {BASE_MODEL}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing=True,
    )

    dataset = _build_dataset(examples_jsonl)
    print(f"Training examples: {len(dataset)}")
    print(
        "Warning: this is a tiny dataset. Expect overfitting and use this as "
        "a structured-output demo, not a robust receipt parser."
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.config.use_cache = False

    # Split each example at "### Response:\n" and mask the prefix tokens so
    # loss is computed only on the JSON output, not on the instruction/input.
    response_marker = "### Response:\n"

    def tokenize(batch):
        all_input_ids, all_labels, all_attention_mask = [], [], []
        for text in batch["text"]:
            split = text.find(response_marker)
            full = tokenizer(text, max_length=2048, truncation=True, padding=False)
            input_ids = full["input_ids"]
            if split != -1:
                prefix_ids = tokenizer(
                    text[: split + len(response_marker)],
                    max_length=2048,
                    truncation=True,
                    padding=False,
                )["input_ids"]
                mask_len = min(len(prefix_ids), len(input_ids))
            else:
                mask_len = len(input_ids)
            labels = [-100] * mask_len + list(input_ids[mask_len:])
            all_input_ids.append(input_ids)
            all_labels.append(labels)
            all_attention_mask.append(full["attention_mask"])
        return {
            "input_ids": all_input_ids,
            "labels": all_labels,
            "attention_mask": all_attention_mask,
        }

    tokenized_dataset = dataset.map(
        tokenize,
        batched=True,
        remove_columns=dataset.column_names,
    )

    class _ResponseOnlyCollator:
        def __init__(self, pad_id: int):
            self._pad = pad_id

        def __call__(self, features):
            max_len = max(len(f["input_ids"]) for f in features)
            batch = {"input_ids": [], "attention_mask": [], "labels": []}
            for f in features:
                pad = max_len - len(f["input_ids"])
                batch["input_ids"].append(list(f["input_ids"]) + [self._pad] * pad)
                batch["attention_mask"].append(list(f["attention_mask"]) + [0] * pad)
                batch["labels"].append(list(f["labels"]) + [-100] * pad)
            return {k: torch.tensor(v) for k, v in batch.items()}

    data_collator = _ResponseOnlyCollator(pad_id=tokenizer.pad_token_id)

    trainer = Trainer(
        model=model,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=num_train_epochs,
            max_steps=max_steps,
            learning_rate=learning_rate,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            output_dir=str(ADAPTER_DIR / "checkpoints"),
            save_strategy="no",
            warmup_ratio=0.05,
            optim="adamw_8bit",
            report_to="none",
        ),
    )

    trainer.train()
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(ADAPTER_DIR))
    tokenizer.save_pretrained(str(ADAPTER_DIR))
    adapter_volume.commit()

    return {
        "ok": True,
        "adapter_dir": str(ADAPTER_DIR),
        "examples": len(dataset),
        "max_steps": max_steps,
        "num_train_epochs": num_train_epochs,
    }


@app.function(
    image=image,
    gpu="T4",
    timeout=600,
    scaledown_window=300,
    volumes={
        "/model_cache": model_cache,
        "/adapters": adapter_volume,
    },
)
@modal.asgi_app()
def api():
    from fastapi import Body, FastAPI, HTTPException
    from unsloth import FastLanguageModel

    web_app = FastAPI(title="Dukaan Saathi Receipt LLM")

    adapter_loaded = (ADAPTER_DIR / "adapter_config.json").exists()
    model_path = str(ADAPTER_DIR if adapter_loaded else BASE_MODEL)
    print(f"Loading receipt parser model: {model_path}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_path,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    @web_app.get("/health")
    def health():
        return {
            "ok": True,
            "app": APP_NAME,
            "base_model": BASE_MODEL,
            "adapter_loaded": adapter_loaded,
            "adapter_dir": str(ADAPTER_DIR),
        }

    @web_app.post("/parse")
    async def parse(payload: dict = Body(...)):
        start = time.perf_counter()
        raw_text = str(payload.get("raw_text") or "").strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="Missing raw_text")
        if not adapter_loaded:
            raise HTTPException(
                status_code=503,
                detail="Receipt LoRA adapter is not trained yet. Run scripts/modal_finetune_receipt.sh first.",
            )

        prompt = INSTRUCTION_TEMPLATE.format(
            system=SYSTEM_PROMPT,
            input=raw_text,
            output="",
        )
        inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
        output_ids = model.generate(
            **inputs,
            max_new_tokens=768,
            temperature=0.1,
            do_sample=False,
        )
        generated = tokenizer.decode(
            output_ids[0][inputs.input_ids.shape[-1]:],
            skip_special_tokens=True,
        ).strip()

        return {
            "model": model_path,
            "raw_json": generated,
            "latency_seconds": round(time.perf_counter() - start, 2),
        }

    return web_app


MODEL_CARD = """---
language:
- en
- te
license: mit
base_model: unsloth/Llama-3.2-3B-Instruct-bnb-4bit
tags:
- receipt-parsing
- kirana
- inventory
- fine-tuned
- lora
- indian-retail
pipeline_tag: text-generation
---

# Dukaan Saathi — Receipt Parser (Llama-3.2-3B fine-tune)

Fine-tuned **Llama-3.2-3B-Instruct** for structured receipt parsing in Indian kirana (convenience) store workflows.

Part of the [Dukaan Saathi](https://huggingface.co/spaces/summerdevlin46/dukaan-saathi) inventory copilot demo.

## What it does

Takes noisy supplier receipt OCR text and returns a structured JSON object with line items, quantities, prices, and supplier info. Designed for messy real-world receipts: handwritten bills, printed tax invoices, informal tally notes.

## Training data

- 6 hand-authored examples from real kirana receipt formats
- 22 Modal LLM-generated synthetic examples augmenting edge cases
- Total: 28 examples; training focuses on format consistency over broad generalisation

## Example

**Input:**
```
MAHALAKSHMI MARKETING
No. 2816  Date: 27/5/26
Parle  1 X 2450 = 2450
Bingo(C)  4 X 870 = 3480
Subtotal 5930  Discount 612  Total 6542
```

**Output:**
```json
{
  "supplier": "Mahalakshmi Marketing",
  "invoice_no": "2816",
  "date": "2026-05-27",
  "items": [
    {"product_raw": "Parle", "qty_cases": 1, "qty_units": 1, "unit_cost": 2450.0, "total": 2450.0},
    {"product_raw": "Bingo(C)", "qty_cases": 4, "qty_units": 4, "unit_cost": 870.0, "total": 3480.0}
  ],
  "subtotal": 5930.0,
  "discount": 612.0,
  "gst": 0.0,
  "net_total": 6542.0
}
```

## Inference

```python
from huggingface_hub import InferenceClient

client = InferenceClient()
prompt = \"\"\"### Instruction:
You are a receipt parser for an Indian convenience store. Extract all line items. Return ONLY valid JSON, no markdown.

### Input:
<paste receipt text here>

### Response:
\"\"\"
result = client.text_generation(prompt, model="summerdevlin46/dukaan-saathi-receipt-lora", max_new_tokens=768)
```

## Limitations

- Small training set; overfits to known receipt styles (Mahalakshmi Marketing, Sri Venkateshwara Marketing, Brundavan Buns)
- Owner approval gate always required before any inventory write
- Not a general-purpose receipt parser
"""


@app.function(
    image=image,
    gpu="T4",
    timeout=60 * 45,
    secrets=[modal.Secret.from_dotenv()],
    volumes={
        "/model_cache": model_cache,
        "/adapters": adapter_volume,
    },
)
def push_adapter_to_hub() -> dict:
    """
    Merge the LoRA adapter into the base model and push the full model to HF Hub.
    Reads HF_TOKEN and HF_RECEIPT_MODEL_REPO from environment (set in .env).
    Run once after fine-tuning to make the model available for HF Inference API.

    Usage:
        modal run modal_apps/receipt_llm_service.py::push
    """
    import os
    from huggingface_hub import create_repo, HfApi
    from unsloth import FastLanguageModel

    hf_token = os.environ["HF_TOKEN"]
    hf_repo_id = os.environ["HF_RECEIPT_MODEL_REPO"]

    if not (ADAPTER_DIR / "adapter_config.json").exists():
        return {"ok": False, "error": "Adapter not found in volume. Run fine-tuning first."}

    # Load adapter path directly — unsloth resolves base model + adapter together.
    # fp16 (load_in_4bit=False) is required for a clean merge; 4-bit quantized
    # weights can't be merged into a standalone HF Hub model.
    print(f"Loading base model + LoRA adapter (fp16) from {ADAPTER_DIR}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(ADAPTER_DIR),
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=False,
    )

    print(f"Pushing merged fp16 model to Hub: {hf_repo_id}")
    create_repo(hf_repo_id, repo_type="model", exist_ok=True, token=hf_token)
    model.push_to_hub_merged(
        hf_repo_id,
        tokenizer,
        save_method="merged_16bit",
        token=hf_token,
    )

    # Export Q4_K_M GGUF for CPU inference via llama.cpp.
    # The filename must match what scripts/download_models.py fetches.
    gguf_local = "/tmp/receipt-gguf"
    gguf_filename = "llama-3.2-3b-receipt-unsloth.Q4_K_M.gguf"
    print(f"Exporting GGUF Q4_K_M to {gguf_local}")
    model.save_pretrained_gguf(gguf_local, tokenizer, quantization_method="q4_k_m")
    gguf_files = list(Path(gguf_local).glob("*.gguf"))
    if gguf_files:
        gguf_src = gguf_files[0]
        print(f"Uploading {gguf_src.name} → {hf_repo_id}/{gguf_filename}")
        HfApi(token=hf_token).upload_file(
            path_or_fileobj=str(gguf_src),
            path_in_repo=gguf_filename,
            repo_id=hf_repo_id,
            repo_type="model",
        )
    else:
        print("Warning: no GGUF file found after export; skipping GGUF upload")

    HfApi(token=hf_token).upload_file(
        path_or_fileobj=MODEL_CARD.encode(),
        path_in_repo="README.md",
        repo_id=hf_repo_id,
        repo_type="model",
    )

    model_url = f"https://huggingface.co/{hf_repo_id}"
    print(f"Done: {model_url}")
    return {"ok": True, "hf_repo_id": hf_repo_id, "url": model_url, "gguf": gguf_filename}


@app.local_entrypoint()
def train(
    dataset_path: str = "data/finetune/receipt_examples.jsonl",
    max_steps: int = 200,
    num_train_epochs: int = 30,
):
    examples_jsonl = Path(dataset_path).read_text()
    result = finetune_receipt_lora.remote(
        examples_jsonl=examples_jsonl,
        max_steps=max_steps,
        num_train_epochs=num_train_epochs,
    )
    print(json.dumps(result, indent=2))


@app.local_entrypoint()
def push():
    """Push the trained adapter to HF Hub. Reads HF_TOKEN and HF_RECEIPT_MODEL_REPO from .env."""
    result = push_adapter_to_hub.remote()
    print(json.dumps(result, indent=2))
