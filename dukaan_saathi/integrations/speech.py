from __future__ import annotations

import os
from pathlib import Path

import requests


def transcribe_audio(audio_path: str | None) -> tuple[str, list[str]]:
    """
    Speech-to-text client for correction commands.

    Contract:
    - input: audio file path from Gradio
    - output: transcript string + trace

    Safety boundary:
    - This only returns text.
    - It does not apply corrections.
    - It does not approve inventory updates.
    """

    trace: list[str] = []

    if not audio_path:
        return "", ["No audio provided."]

    path = Path(audio_path)

    if not path.exists():
        return "", [f"Audio file not found: {audio_path}"]

    endpoint = (
        os.getenv("MODAL_SPEECH_ENDPOINT")
        or os.getenv("SPEECH_ASR_ENDPOINT")
        or ""
    ).strip()

    if not endpoint:
        return "", [
            "Speech ASR endpoint is not configured.",
            "Run scripts/modal_deploy.sh modal_apps/speech_asr_service.py to generate it.",
            "Typed correction still works.",
        ]

    trace.append(f"Sending audio to ASR endpoint: {endpoint}")
    trace.append(f"Audio file: {path.name}")

    try:
        with path.open("rb") as audio_file:
            response = requests.post(
                endpoint,
                files={
                    "audio": (
                        path.name,
                        audio_file,
                        "application/octet-stream",
                    )
                },
                timeout=180,
            )

        if response.status_code >= 400:
            return "", [
                *trace,
                f"ASR request failed with HTTP {response.status_code}.",
                response.text[:500],
            ]

        payload = response.json()
        transcript = str(payload.get("text") or "").strip()

        if not transcript:
            error = payload.get("error")
            if error:
                trace.append(f"ASR returned no transcript: {error}")
            else:
                trace.append("ASR returned no transcript.")
            return "", trace

        trace.append(f"ASR model: {payload.get('model', 'unknown')}")
        trace.append(f"Transcript: {transcript}")

        return transcript, trace

    except requests.RequestException as exc:
        return "", [
            *trace,
            f"ASR request error: {exc}",
            "Typed correction still works.",
        ]
    except ValueError as exc:
        return "", [
            *trace,
            f"Could not parse ASR response JSON: {exc}",
            "Typed correction still works.",
        ]
