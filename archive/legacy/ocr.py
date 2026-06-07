"""
Receipt image OCR using Qwen2.5-VL-7B-Instruct.
Converts a photo of a receipt (handwritten or printed) into structured text,
which is then passed to the receipt_parser LLM node.
"""

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_vl_model = None
_vl_processor = None

OCR_PROMPT = """Look at this receipt image from an Indian convenience store supplier.
Extract ALL text you can see, preserving:
- Supplier name and GST number
- Invoice/receipt number and date
- Each line item: product name, quantity, rate/price, and amount
- Any totals, discounts, GST amounts

Write out the full text exactly as it appears. Product names will be in English.
Numbers may be written as multiplications like '4×870=3480'."""


def _load_vl_model():
    global _vl_model, _vl_processor
    if _vl_model is None:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        name = "Qwen/Qwen2.5-VL-7B-Instruct"
        _vl_processor = AutoProcessor.from_pretrained(name)
        _vl_model = Qwen2VLForConditionalGeneration.from_pretrained(
            name,
            torch_dtype="auto",
            device_map="auto",
        )
        logger.info("Qwen2.5-VL-7B loaded")
    return _vl_processor, _vl_model


def parse_receipt_image(image_path: str) -> dict:
    """
    Run vision model on receipt photo.
    Returns dict with 'raw_text' (OCR output) and basic structured fields.
    The receipt_parser LLM node does the full structured extraction from raw_text.
    """
    if not image_path or not Path(image_path).exists():
        return {"raw_text": "", "error": "No image provided"}

    try:
        processor, model = _load_vl_model()

        # Encode image as base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        # Detect mime type
        suffix = Path(image_path).suffix.lower()
        mime = {"jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": f"data:{mime};base64,{img_b64}"},
                    {"type": "text",  "text": OCR_PROMPT},
                ],
            }
        ]

        text_input = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = processor(text=[text_input], return_tensors="pt").to(model.device)
        output_ids = model.generate(**inputs, max_new_tokens=1024)
        generated = output_ids[:, inputs["input_ids"].shape[1]:]
        raw_text = processor.batch_decode(generated, skip_special_tokens=True)[0]

        logger.info(f"OCR completed: {len(raw_text)} chars extracted")
        return {"raw_text": raw_text, "source_image": image_path}

    except Exception as e:
        logger.error(f"Vision OCR failed: {e}")
        return {"raw_text": "", "error": str(e)}
