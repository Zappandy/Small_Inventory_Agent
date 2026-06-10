from __future__ import annotations

import os
import tempfile
from pathlib import Path

import modal


APP_NAME = "dukaan-saathi-speech-asr"
MODEL_ID = "distil-whisper/distil-small.en"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi[standard]",
        "python-multipart",
        "torch",
        "transformers",
        "accelerate",
        "soundfile",
    )
)

app = modal.App(APP_NAME, image=image)

_PIPE = None
_DEVICE = "unknown"


def _get_pipe():
    global _PIPE, _DEVICE

    if _PIPE is not None:
        return _PIPE

    import torch
    from transformers import pipeline

    device = 0 if torch.cuda.is_available() else -1
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    _PIPE = pipeline(
        task="automatic-speech-recognition",
        model=MODEL_ID,
        torch_dtype=torch_dtype,
        device=device,
    )
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    return _PIPE


@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    scaledown_window=300,
)
@modal.fastapi_endpoint(method="GET", label="speech-health")
def health():
    _get_pipe()
    return {
        "status": "ok",
        "app": APP_NAME,
        "model": MODEL_ID,
        "device": _DEVICE,
    }


@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    scaledown_window=300,
)
@modal.fastapi_endpoint(method="POST", label="speech-transcribe")
async def transcribe(request):
    pipe = _get_pipe()

    form = await request.form()
    upload = form.get("audio")

    if upload is None:
        return {
            "text": "",
            "error": "Missing multipart file field named 'audio'.",
            "model": MODEL_ID,
        }

    filename = getattr(upload, "filename", "") or "audio.wav"
    suffix = Path(filename).suffix or ".wav"
    audio_bytes = await upload.read()

    if not audio_bytes:
        return {
            "text": "",
            "error": "Uploaded audio file is empty.",
            "model": MODEL_ID,
        }

    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        result = pipe(tmp_path)
        text = str(result.get("text", "")).strip()

        return {
            "text": text,
            "model": MODEL_ID,
            "device": _DEVICE,
            "filename": filename,
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
