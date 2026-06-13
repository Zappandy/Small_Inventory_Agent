#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

DATASET_PATH="data/finetune/receipt_examples.jsonl"
OUTPUT_PATH="data/finetune/generated/receipt_examples_modal_synthetic.jsonl"
COUNT="48"
MODEL_ID="Qwen/Qwen2.5-1.5B-Instruct"
BATCH_SIZE="8"
INCLUDE_BASE="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset)
      DATASET_PATH="$2"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --count)
      COUNT="$2"
      shift 2
      ;;
    --model-id)
      MODEL_ID="$2"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="$2"
      shift 2
      ;;
    --generated-only)
      INCLUDE_BASE="false"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/modal_generate_receipt_examples.sh [--dataset path] [--output path] [--count 48]

Uses a small instruct model on Modal to generate synthetic receipt training JSONL.
By default, the output includes the base examples followed by generated examples.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

uv run modal run modal_apps/receipt_data_generator.py::generate \
  --dataset-path "$DATASET_PATH" \
  --output-path "$OUTPUT_PATH" \
  --count "$COUNT" \
  --model-id "$MODEL_ID" \
  --batch-size "$BATCH_SIZE" \
  --include-base "$INCLUDE_BASE"
