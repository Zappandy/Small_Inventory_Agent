"""
finetune_receipt.py — LoRA fine-tune Llama-3.2-3B-Instruct on receipt line-item extraction.

Training data: data/finetune/receipt_examples.jsonl
Format: {"input": "<ocr_text>", "output": "<json_string>"}

Preferred path:
    scripts/modal_finetune_receipt.sh --synthetic-count 48

Optional local/HF path:
    uv run python scripts/finetune_receipt.py --hf-repo-id your-org/receipt-lora

Output:
    ./llama-3.2-3b-receipt-lora/   (LoRA adapter, push this to HF Hub)
    llama-3.2-3b-receipt-unsloth.Q4_K_M.gguf  (for llama.cpp on port 8082)

Uses Unsloth for 2x faster training with 60% less VRAM.
"""

import json
import os
import argparse
from pathlib import Path

DATASET_PATH = Path("data/finetune/receipt_examples.jsonl")
BASE_MODEL = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
OUTPUT_DIR = "./llama-3.2-3b-receipt-lora"
GGUF_NAME = "llama-3.2-3b-receipt"

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


def load_dataset(dataset_path: Path) -> list[dict]:
    examples = [
        json.loads(line)
        for line in dataset_path.read_text().splitlines()
        if line.strip()
    ]
    print(f"Loaded {len(examples)} training examples from {dataset_path}")
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


def push_to_hub(model, tokenizer, gguf_path: Path, hf_repo_id: str | None) -> None:
    if not hf_repo_id:
        print("No --hf-repo-id provided; skipping Hub push.")
        print(f"  Local adapter: {gguf_path.parent}")
        print(f"  Local GGUF:    {gguf_path}")
        return

    token = os.getenv("HF_TOKEN")
    if not token:
        print("HF_TOKEN not set — skipping Hub push. Run: huggingface-cli login")
        print(f"  Then: huggingface-cli upload {hf_repo_id} {gguf_path}")
        return

    from huggingface_hub import HfApi, create_repo

    print(f"Pushing to HF Hub: {hf_repo_id}")
    create_repo(hf_repo_id, repo_type="model", exist_ok=True, token=token)

    # Push LoRA adapter (config + weights)
    model.push_to_hub(hf_repo_id, token=token)
    tokenizer.push_to_hub(hf_repo_id, token=token)
    print(f"  Adapter pushed → {hf_repo_id}")

    # Upload GGUF for llama.cpp
    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(gguf_path),
        path_in_repo=gguf_path.name,
        repo_id=hf_repo_id,
        repo_type="model",
    )
    print(f"  GGUF uploaded  → {hf_repo_id}/{gguf_path.name}")
    print(f"\nSet in your .env:  HF_RECEIPT_MODEL_REPO={hf_repo_id}")


def finetune(
    dataset_path: Path,
    output_dir: str,
    gguf_name: str,
    hf_repo_id: str | None,
    num_train_epochs: int,
    max_steps: int,
) -> None:
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

    examples = load_dataset(dataset_path)
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
            num_train_epochs=num_train_epochs,
            max_steps=max_steps,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=1,
            output_dir=output_dir,
            save_strategy="epoch",
            warmup_steps=5,
            optim="adamw_8bit",
        ),
    )

    trainer.train()
    print("Training done. Saving LoRA adapter...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("Exporting merged GGUF (Q4_K_M) for llama.cpp...")
    model.save_pretrained_gguf(
        gguf_name,
        tokenizer,
        quantization_method="q4_k_m",
    )
    gguf_path = Path(f"{gguf_name}-unsloth.Q4_K_M.gguf")
    print(f"  Adapter: {output_dir}/")
    print(f"  GGUF:    {gguf_path}")

    push_to_hub(model, tokenizer, gguf_path, hf_repo_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local/HF receipt LoRA fine-tuning.")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--gguf-name", default=GGUF_NAME)
    parser.add_argument("--hf-repo-id", default=os.getenv("HF_RECEIPT_MODEL_REPO", ""))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=-1)
    args = parser.parse_args()

    finetune(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        gguf_name=args.gguf_name,
        hf_repo_id=args.hf_repo_id or None,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()
