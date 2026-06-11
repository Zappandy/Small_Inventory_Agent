import torch
from datasets import load_dataset
from transformers import (
    AutoProcessor,
    AutoModelForImageTextToText,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
)
from PIL import Image

MODEL_NAME = "openbmb/MiniCPM-V-4.6"

# --------------------------------------------------
# Load model in 4-bit
# --------------------------------------------------

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

processor = AutoProcessor.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
)

model = AutoModelForImageTextToText.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)

model = prepare_model_for_kbit_training(model)

# --------------------------------------------------
# QLoRA
# --------------------------------------------------

peft_config = LoraConfig(
    r=32,
    lora_alpha=64,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
)

model = get_peft_model(model, peft_config)
model.print_trainable_parameters()

# --------------------------------------------------
# Dataset
# --------------------------------------------------

dataset = load_dataset(
) # TODO

# Example JSONL row:
#
# {
#   "image": "images/example.jpg",
#   "question": "What is in this image?",
#   "answer": "A red sports car."
# }

def process_example(example):
    image = Image.open(example["image"]).convert("RGB")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": example["question"]},
            ],
        },
        {
            "role": "assistant",
            "content": example["answer"],
        },
    ]

    prompt = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )

    model_inputs = processor(
        text=prompt,
        images=image,
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=4096,
    )

    labels = model_inputs["input_ids"].clone()

    return {
        "input_ids": model_inputs["input_ids"][0],
        "attention_mask": model_inputs["attention_mask"][0],
        "pixel_values": model_inputs["pixel_values"][0],
        "labels": labels[0],
    }

train_ds = dataset["train"].map(
    process_example,
    remove_columns=dataset["train"].column_names,
)

# --------------------------------------------------
# Trainer
# --------------------------------------------------

training_args = TrainingArguments(
    output_dir="./outputs",
    num_train_epochs=6,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=2,
    learning_rate=2e-4,
    bf16=True,
    logging_steps=10,
    save_steps=200,
    save_total_limit=2,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    gradient_checkpointing=True,
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_ds,
)

trainer.train()

model.save_pretrained("./minicpm-v46-lora")
processor.save_pretrained("./minicpm-v46-lora")