"""Telugu ASR using Whisper — models/asr.py"""
import logging
logger = logging.getLogger(__name__)

_whisper_model = None

def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        # "small" is ~244M params, good Telugu accuracy, fast on CPU
        _whisper_model = whisper.load_model("small")
        logger.info("Whisper small loaded")
    return _whisper_model

def transcribe_telugu(audio_path: str) -> str:
    """Transcribe Telugu audio file → Telugu text string."""
    try:
        model = _load_whisper()
        result = model.transcribe(audio_path, language="te", task="transcribe")
        text = result.get("text", "").strip()
        logger.info(f"ASR: {text[:80]}")
        return text
    except Exception as e:
        logger.error(f"ASR failed: {e}")
        return ""
