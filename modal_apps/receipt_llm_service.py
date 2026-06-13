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
        "trl>=0.12.0",
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
    from transformers import TrainingArguments
    from trl import SFTTrainer
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
        lora_alpha=16,
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

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
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
            warmup_steps=2,
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
    from fastapi import FastAPI, HTTPException, Request
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
    async def parse(request: Request):
        start = time.perf_counter()
        payload = await request.json()
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


@app.local_entrypoint()
def train(
    dataset_path: str = "data/finetune/receipt_examples.jsonl",
    max_steps: int = 30,
    num_train_epochs: int = 8,
):
    examples_jsonl = Path(dataset_path).read_text()
    result = finetune_receipt_lora.remote(
        examples_jsonl=examples_jsonl,
        max_steps=max_steps,
        num_train_epochs=num_train_epochs,
    )
    print(json.dumps(result, indent=2))
