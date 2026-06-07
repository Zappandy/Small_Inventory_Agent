from __future__ import annotations


def transcribe_audio(audio_path: str | None) -> tuple[str, list[str]]:
    """
    Placeholder for speech-to-text.

    Contract:
    - input: audio file path from Gradio
    - output: transcript string + trace
    """
    if not audio_path:
        return "", ["No audio provided."]

    return "", [
        "Speech transcription is not connected yet.",
        "Current MVP uses typed Telugu/code-mixed commands.",
        "Next step: transcribe audio, then pass transcript into parse_stock_command().",
    ]
