"""
Telugu ↔ English translation using IndicTrans2 (ai4bharat).
Runs fully locally — no API calls.

Model: ai4bharat/indictrans2-indic-en-1B  (~1GB, CPU-friendly)
       ai4bharat/indictrans2-en-indic-1B  for English → Telugu
"""

import logging
logger = logging.getLogger(__name__)

_te_en_model = None
_te_en_tokenizer = None
_en_te_model = None
_en_te_tokenizer = None


def _load_te_en():
    global _te_en_model, _te_en_tokenizer
    if _te_en_model is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        name = "ai4bharat/indictrans2-indic-en-1B"
        _te_en_tokenizer = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
        _te_en_model = AutoModelForSeq2SeqLM.from_pretrained(name, trust_remote_code=True)
        logger.info("IndicTrans2 te→en loaded")
    return _te_en_tokenizer, _te_en_model


def _load_en_te():
    global _en_te_model, _en_te_tokenizer
    if _en_te_model is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        name = "ai4bharat/indictrans2-en-indic-1B"
        _en_te_tokenizer = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
        _en_te_model = AutoModelForSeq2SeqLM.from_pretrained(name, trust_remote_code=True)
        logger.info("IndicTrans2 en→te loaded")
    return _en_te_tokenizer, _en_te_model


def te_to_en(text: str) -> str:
    """Translate Telugu → English. Product names in English stay unchanged."""
    if not text or not text.strip():
        return text
    # If text has no Telugu chars, return as-is
    if not any("\u0C00" <= c <= "\u0C7F" for c in text):
        return text
    try:
        tokenizer, model = _load_te_en()
        # IndicTrans2 expects source language tag
        tagged = f"<2en> {text}"
        inputs = tokenizer(tagged, return_tensors="pt", padding=True)
        outputs = model.generate(**inputs, max_new_tokens=256, num_beams=4)
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        logger.debug(f"te→en: '{text[:40]}' → '{result[:40]}'")
        return result
    except Exception as e:
        logger.error(f"te_to_en failed: {e}")
        return text


def en_to_te(text: str) -> str:
    """Translate English → Telugu. Numbers and product names kept in English."""
    if not text or not text.strip():
        return text
    try:
        tokenizer, model = _load_en_te()
        tagged = f"<2te> {text}"
        inputs = tokenizer(tagged, return_tensors="pt", padding=True)
        outputs = model.generate(**inputs, max_new_tokens=256, num_beams=4)
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        logger.debug(f"en→te: '{text[:40]}' → '{result[:40]}'")
        return result
    except Exception as e:
        logger.error(f"en_to_te failed: {e}")
        return text
