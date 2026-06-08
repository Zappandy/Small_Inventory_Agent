import time

import modal


APP_NAME = "dukaan-saathi-receipt-vlm"
MODEL_ID = "openbmb/MiniCPM-V-4.6"

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

app = modal.App(APP_NAME)

model_cache = modal.Volume.from_name(
    "dukaan-saathi-minicpm-cache",
    create_if_missing=True,
)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install(
        "fastapi[standard]",
        "pillow",
        "torch",
        "torchvision",
        "accelerate",
        "huggingface_hub",
        "transformers[torch]>=5.7.0",
    )
)


@app.function(
    image=image,
    gpu=["L4", "T4"],
    timeout=600,
    scaledown_window=300,
    volumes={"/cache": model_cache},
)
@modal.asgi_app()
def api():
    from pathlib import Path
    import tempfile

    from fastapi import FastAPI, File, HTTPException, Request
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    web_app = FastAPI(title="Dukaan Saathi Receipt VLM")

    print(f"Loading model: {MODEL_ID}")
    processor = AutoProcessor.from_pretrained(
        MODEL_ID,
        cache_dir="/cache",
    )
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        torch_dtype="auto",
        device_map="auto",
        cache_dir="/cache",
    )
    model.eval()
    print("Model loaded.")

    @web_app.get("/health")
    def health():
        return {
            "ok": True,
            "model": MODEL_ID,
            "mode": "image_to_raw_text",
        }


    @web_app.post("/extract")
    async def extract(request: Request):
        start = time.perf_counter()
    
        form = await request.form()
        upload = form.get("image")
    
        if upload is None:
            raise HTTPException(
                status_code=400,
                detail="Missing multipart form field named 'image'.",
            )
    
        content_type = getattr(upload, "content_type", "") or ""
        filename = getattr(upload, "filename", "") or "receipt.jpg"
    
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"Expected image upload, got {content_type}",
            )
    
        suffix = ".jpg"
        if filename and "." in filename:
            suffix = "." + filename.rsplit(".", 1)[-1]
    
        contents = await upload.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty image upload.")
    
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            image_path = tmp.name
    
        try:
            image_url = str(Path(image_path).resolve())
    
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "url": image_url},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ]
    
            downsample_mode = "4x"
    
            inputs = processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
                downsample_mode=downsample_mode,
                processor_kwargs={
                    "max_slice_nums": 36,
                },
            ).to(model.device)
    
            with torch.no_grad():
                generated_ids = model.generate(
                    **inputs,
                    downsample_mode=downsample_mode,
                    max_new_tokens=768,
                )
    
            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
    
            output_text = processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
    
            raw_text = output_text[0].strip()
            elapsed = round(time.perf_counter() - start, 2)
    
            return {
                "model": MODEL_ID,
                "raw_text": raw_text,
                "latency_seconds": elapsed,
            }
    
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Model extraction failed: {exc}",
            ) from exc
    

    return web_app
