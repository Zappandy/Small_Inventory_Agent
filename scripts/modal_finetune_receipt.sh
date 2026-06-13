#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

DATASET_PATH="data/finetune/receipt_examples.jsonl"
MAX_STEPS="30"
EPOCHS="8"
SYNTHETIC_COUNT="0"
SYNTHETIC_SEED="7"
MODAL_SYNTHETIC_COUNT="0"
MODAL_SYNTHETIC_MODEL_ID="Qwen/Qwen2.5-1.5B-Instruct"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset)
      DATASET_PATH="$2"
      shift 2
      ;;
    --max-steps)
      MAX_STEPS="$2"
      shift 2
      ;;
    --epochs)
      EPOCHS="$2"
      shift 2
      ;;
    --synthetic-count)
      SYNTHETIC_COUNT="$2"
      shift 2
      ;;
    --synthetic-seed)
      SYNTHETIC_SEED="$2"
      shift 2
      ;;
    --modal-synthetic-count)
      MODAL_SYNTHETIC_COUNT="$2"
      shift 2
      ;;
    --modal-synthetic-model-id)
      MODAL_SYNTHETIC_MODEL_ID="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/modal_finetune_receipt.sh [--dataset path] [--modal-synthetic-count 0] [--max-steps 30] [--epochs 8]

Runs receipt LoRA fine-tuning on Modal and stores the adapter in a Modal Volume.
This avoids making Hugging Face Hub the mandatory artifact store.
Use --modal-synthetic-count to generate LLM-augmented examples on Modal before training.
Use --synthetic-count only for deterministic template/debug examples.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$MODAL_SYNTHETIC_COUNT" != "0" ]]; then
  GENERATED_DATASET="$(mktemp -t dukaan-modal-receipt-examples.XXXXXX.jsonl)"
  scripts/modal_generate_receipt_examples.sh \
    --dataset "$DATASET_PATH" \
    --count "$MODAL_SYNTHETIC_COUNT" \
    --model-id "$MODAL_SYNTHETIC_MODEL_ID" \
    --output "$GENERATED_DATASET"
  DATASET_PATH="$GENERATED_DATASET"
fi

if [[ "$SYNTHETIC_COUNT" != "0" ]]; then
  GENERATED_DATASET="$(mktemp -t dukaan-receipt-examples.XXXXXX.jsonl)"
  uv run python scripts/generate_receipt_examples.py \
    --base "$DATASET_PATH" \
    --count "$SYNTHETIC_COUNT" \
    --seed "$SYNTHETIC_SEED" \
    --output "$GENERATED_DATASET"
  DATASET_PATH="$GENERATED_DATASET"
fi

uv run modal run modal_apps/receipt_llm_service.py::train \
  --dataset-path "$DATASET_PATH" \
  --max-steps "$MAX_STEPS" \
  --num-train-epochs "$EPOCHS"
