"""
finetune_receipt.py — LoRA finetune Mistral-7B on receipt line-item extraction.

Training data: photos/OCR text from Mahalakshmi Marketing and Sri Venkateshwara
receipts, paired with correct structured JSON output.

Run on HF free GPU (T4) or locally:
    python finetune_receipt.py

Output: ./mistral-7b-receipt-lora/  (merged GGUF exported at the end)

Uses Unsloth for 2x faster training with 60% less VRAM.
"""

import json
from pathlib import Path

# ── Training dataset ─────────────────────────────────────────────────────────
# Format: list of {"input": "<ocr_text>", "output": "<json_string>"}
# Expand this with more receipts as you photograph them.

TRAINING_EXAMPLES = [
    {
        "input": """MAHALAKSHMI MARKETING
No. 2816  Date: 27/5/26
M/s. Veerabala (Mulal)
Parle  1 X 2450 = 2450
Bingo(C)  4 X 870 = 3480
Subtotal 5930
Discount 612
Total 6542""",
        "output": json.dumps({
            "supplier": "Mahalakshmi Marketing",
            "invoice_no": "2816",
            "date": "2026-05-27",
            "items": [
                {"product_raw": "Parle", "qty_cases": 1, "qty_units": 1,
                 "unit_cost": 2450.0, "total": 2450.0},
                {"product_raw": "Bingo(C)", "qty_cases": 4, "qty_units": 4,
                 "unit_cost": 870.0, "total": 3480.0},
            ],
            "subtotal": 5930.0, "discount": 612.0, "gst": 0.0, "net_total": 6542.0,
        }),
    },
    {
        "input": """SRI VENKATESHWARA MARKETING
GSTIN: 36AZLIPV6442K12M
CUSTOMER: VEERA BHADRA WS
Bill Date: 28/05/2026
1 PARLE-G 100G  QTY: 5/0  MRP: 10  SALE RATE: 8.625
2 HAPPY 2 (24P)*13  QTY: 10/0  MRP: 9  SALE RATE: 4.464
GROSS SALES: 8569.032
SCHEMES: 168.352
CASH DISC: 420.034
GST: 210.017  SGST: 210.017
NET AMOUNT: 8821.00""",
        "output": json.dumps({
            "supplier": "Sri Venkateshwara Marketing",
            "invoice_no": "SVM/26-27/2598",
            "date": "2026-05-28",
            "items": [
                {"product_raw": "PARLE-G 100G", "qty_cases": 5, "qty_units": 120,
                 "unit_cost": 8.625, "total": 1035.0},
                {"product_raw": "HAPPY 2 (24P)", "qty_cases": 10, "qty_units": 240,
                 "unit_cost": 4.464, "total": 1071.36},
            ],
            "subtotal": 8569.032, "discount": 588.386, "gst": 420.034, "net_total": 8821.0,
        }),
    },
    {
        "input": """Brundhna Boys - 28/05
hne  30X28 = 840
oam  50X9.5  450
Bm   10X9.5  95
Bm   5X12    50
Total        1435""",
        "output": json.dumps({
            "supplier": "sales_note",
            "invoice_no": None,
            "date": "2026-05-28",
            "items": [
                {"product_raw": "hne",  "qty_cases": 0, "qty_units": 30, "unit_cost": 28.0, "total": 840.0},
                {"product_raw": "oam",  "qty_cases": 0, "qty_units": 50, "unit_cost": 9.5,  "total": 450.0},
                {"product_raw": "Bm",   "qty_cases": 0, "qty_units": 10, "unit_cost": 9.5,  "total": 95.0},
                {"product_raw": "Bm",   "qty_cases": 0, "qty_units": 5,  "unit_cost": 12.0, "total": 50.0},
            ],
            "subtotal": 1435.0, "discount": 0.0, "gst": 0.0, "net_total": 1435.0,
        }),
    },
]

SYSTEM_PROMPT = """You are a receipt parser for an Indian convenience store.
Extract all line items from the receipt text. Return ONLY valid JSON, no markdown."""

INSTRUCTION_TEMPLATE = """### Instruction:
{system}

### Input:
{input}

### Response:
{output}"""


def build_dataset():
    """Convert examples to Unsloth instruction format."""
    return [
        {
            "text": INSTRUCTION_TEMPLATE.format(
                system=SYSTEM_PROMPT,
                input=ex["input"],
                output=ex["output"],
            )
        }
        for ex in TRAINING_EXAMPLES
    ]


def finetune():
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import Dataset

    print("Loading base model with Unsloth...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/mistral-7b-instruct-v0.2-bnb-4bit",
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    # Apply LoRA
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

    dataset = Dataset.from_list(build_dataset())
    print(f"Training on {len(dataset)} examples")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=10,        # small dataset → more epochs
            learning_rate=2e-4,
            fp16=True,
            logging_steps=1,
            output_dir="./mistral-7b-receipt-lora",
            save_strategy="epoch",
            warmup_steps=5,
            optim="adamw_8bit",
        ),
    )

    trainer.train()
    print("Training done. Saving LoRA weights...")
    model.save_pretrained("./mistral-7b-receipt-lora")
    tokenizer.save_pretrained("./mistral-7b-receipt-lora")

    # Export merged GGUF for llama.cpp
    print("Exporting merged GGUF (Q4_K_M)...")
    model.save_pretrained_gguf(
        "mistral-7b-receipt",
        tokenizer,
        quantization_method="q4_k_m",
    )
    print("Done! Upload mistral-7b-receipt-unsloth.Q4_K_M.gguf to your HF Space model dir.")


if __name__ == "__main__":
    finetune()
