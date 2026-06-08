from __future__ import annotations

import modal


APP_NAME = "dukaan-saathi-receipt-vlm"
MODEL_ID = "openbmb/MiniCPM-V-4.6"

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install(
        "fastapi[standard]",
        "pillow",
        "torch",
        "torchvision",
        "accelerate",
        "transformers[torch]>=5.7.0",
        "av",
        "huggingface_hub",
    )
)

model_volume = modal.Volume.from_name(
    "dukaan-saathi-minicpm-v-cache",
    create_if_missing=True,
)


PROMPT = """You are reading an Indian convenience-store supplier receipt.

Extract the visible receipt text faithfully.

Rules:
- Preserve product names exactly as written.
- Preserve quantities like "5/0", "4 X 870 = 3480", "10 X 9.5 = 95".
- Preserve supplier name, date, invoice/bill number, totals, GST fields if visible.
- Do not guess missing text.
- If handwriting is unclear, write [unclear].
- Return plain text only.
"""


@app.cls(
    image=image,
    gpu="T4",
    timeout=600,
    volumes={"/cache": model_volume},
    scaledown_window=300,
)
class ReceiptVLM:
    @modal.enter()
    def load_model(self):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(
            MODEL_ID,
            cache_dir="/cache",
        )
        self.model = AutoModelForImageTextToText.from_pretrained(
            MODEL_ID,
            torch_dtype="auto",
            device_map="auto",
            cache_dir="/cache",
        )
        self.model.eval()

    def run_model(self, image_path: str) -> str:
        from pathlib import Path

        import torch

        # MiniCPM-V 4.6 Transformers usage supports messages with image URLs.
        # Local file paths are usually accepted by the processor's chat template.
        # If this fails, convert to a file:// URI or serve bytes through PIL in
        # the next iteration.
        image_url = Path(image_path).resolve().as_uri()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "url": image_url},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ]

        downsample_mode = "4x"  # better detail for receipts than 16x
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
            downsample_mode=downsample_mode,
            max_slice_nums=36,
        ).to(self.model.device)

        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                downsample_mode=downsample_mode,
                max_new_tokens=768,
            )

        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]

        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )

        return output_text[0].strip()


@app.function(
    image=image,
    timeout=600,
)
@modal.asgi_app()
def api():
    from fastapi import FastAPI, File, HTTPException, UploadFile
    import tempfile

    web_app = FastAPI(title="Dukaan Saathi Receipt VLM")

    @web_app.get("/health")
    def health():
        return {
            "ok": True,
            "model": MODEL_ID,
            "mode": "image_to_raw_text",
        }

    @web_app.post("/extract")
    async def extract(image: UploadFile = File(...)):
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"Expected image upload, got {image.content_type}",
            )

        suffix = ".jpg"
        if image.filename and "." in image.filename:
            suffix = "." + image.filename.rsplit(".", 1)[-1]

        contents = await image.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty image upload.")

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            raw_text = ReceiptVLM().run_model.remote(tmp_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Model failed: {exc}") from exc

        return {
            "raw_text": raw_text,
            "model": MODEL_ID,
        }

    return web_app
