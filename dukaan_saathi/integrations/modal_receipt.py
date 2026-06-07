from __future__ import annotations

from typing import Any


def extract_receipt_with_modal(image: Any) -> tuple[list[dict], list[str]]:
    """
    Placeholder for Modal-hosted VLM/OCR receipt extraction.

    Contract:
    - input: uploaded receipt image
    - output: rows shaped like the receipt table columns
    """
    return [], [
        "Modal receipt extraction is not connected yet.",
        "Current MVP uses pasted receipt text.",
        "Next step: call a Modal endpoint here and return receipt rows.",
    ]
