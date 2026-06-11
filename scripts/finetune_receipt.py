"""
finetune_receipt.py — LoRA fine-tune Llama-3.2-3B-Instruct on receipt line-item extraction.

Training data: data/finetune/receipt_examples.jsonl
Format: {"input": "<ocr_text>", "output": "<json_string>"}

Run on HF free GPU (T4) or locally:
    python scripts/finetune_receipt.py

Output:
    ./llama-3.2-3b-receipt-lora/   (LoRA adapter, push this to HF Hub)
    llama-3.2-3b-receipt-unsloth.Q4_K_M.gguf  (for llama.cpp on port 8082)

Uses Unsloth for 2x faster training with 60% less VRAM.
"""

import json
import os
from pathlib import Path

DATASET_PATH = Path("data/finetune/receipt_examples.jsonl")
BASE_MODEL = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
OUTPUT_DIR = "./llama-3.2-3b-receipt-lora"
GGUF_NAME = "llama-3.2-3b-receipt"
HF_REPO_ID = "summerdevlin46/llama-3.2-3b-receipt-lora"

SYSTEM_PROMPT = (
    "You are a receipt parser for an Indian convenience store. "
    "Extract all line items from the receipt text. "
    "Return ONLY valid JSON, no markdown, no explanation."
)

INSTRUCTION_TEMPLATE = """### Instruction:
{system}

### Input:
{input}

### Response:
{output}"""


def load_dataset() -> list[dict]:
    examples = [
        json.loads(line)
        for line in DATASET_PATH.read_text().splitlines()
        if line.strip()
    ]
    print(f"Loaded {len(examples)} training examples from {DATASET_PATH}")
    return examples


def build_hf_dataset(examples: list[dict]):
    from datasets import Dataset

    records = [
        {
            "text": INSTRUCTION_TEMPLATE.format(
                system=SYSTEM_PROMPT,
                input=ex["input"],
                output=ex["output"],
            )
        }
        for ex in examples
    ]
    return Dataset.from_list(records)


def push_to_hub(model, tokenizer, gguf_path: Path) -> None:
    token = os.getenv("HF_TOKEN")
    if not token:
        print("HF_TOKEN not set — skipping Hub push. Run: huggingface-cli login")
        print(f"  Then: huggingface-cli upload {HF_REPO_ID} {gguf_path}")
        return

    from huggingface_hub import HfApi, create_repo

    print(f"Pushing to HF Hub: {HF_REPO_ID}")
    create_repo(HF_REPO_ID, repo_type="model", exist_ok=True, token=token)

    # Push LoRA adapter (config + weights)
    model.push_to_hub(HF_REPO_ID, token=token)
    tokenizer.push_to_hub(HF_REPO_ID, token=token)
    print(f"  Adapter pushed → {HF_REPO_ID}")

    # Upload GGUF for llama.cpp
    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(gguf_path),
        path_in_repo=gguf_path.name,
        repo_id=HF_REPO_ID,
        repo_type="model",
    )
    print(f"  GGUF uploaded  → {HF_REPO_ID}/{gguf_path.name}")
    print(f"\nSet in your .env:  HF_RECEIPT_MODEL_REPO={HF_REPO_ID}")


def finetune() -> None:
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments

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
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                         "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing=True,
    )

    examples = load_dataset()
    dataset = build_hf_dataset(examples)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=10,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=1,
            output_dir=OUTPUT_DIR,
            save_strategy="epoch",
            warmup_steps=5,
            optim="adamw_8bit",
        ),
    )

    trainer.train()
    print("Training done. Saving LoRA adapter...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print("Exporting merged GGUF (Q4_K_M) for llama.cpp...")
    model.save_pretrained_gguf(
        GGUF_NAME,
        tokenizer,
        quantization_method="q4_k_m",
    )
    gguf_path = Path(f"{GGUF_NAME}-unsloth.Q4_K_M.gguf")
    print(f"  Adapter: {OUTPUT_DIR}/")
    print(f"  GGUF:    {gguf_path}")

    push_to_hub(model, tokenizer, gguf_path)


if __name__ == "__main__":
    finetune()
