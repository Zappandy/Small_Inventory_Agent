from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from dukaan_saathi.integrations.vision import (
    VisionBackendName,
    VisionExtractionResult,
    VisionRequest,
    VisionRow,
)
from dukaan_saathi.parsers.receipt_text import parse_receipt_text


BACKEND_NAME: VisionBackendName = "modal"
UNKNOWN_MODEL = "unknown model"


def _payload_text(payload: dict[str, Any]) -> str:
    return str(payload.get("raw_text") or payload.get("text") or "")


def _payload_latency(payload: dict[str, Any]) -> float | None:
    value = payload.get("latency_seconds")
    if isinstance(value, int | float):
        return float(value)
    return None


def _coerce_rows(value: Any) -> list[VisionRow]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _result_from_modal_payload(payload: dict[str, Any], trace: list[str]) -> VisionExtractionResult:
    model_name = str(payload.get("model") or UNKNOWN_MODEL)
    raw_text = _payload_text(payload)
    rows = _coerce_rows(payload.get("rows"))
    latency_seconds = _payload_latency(payload)

    return VisionExtractionResult(
        backend_name=BACKEND_NAME,
        model_name=model_name,
        raw_text=raw_text,
        rows=rows,
        latency_seconds=latency_seconds,
        trace_messages=trace,
    )


def _extract_receipt_result_with_modal(image_path: Any) -> VisionExtractionResult:
    trace: list[str] = ["Starting receipt image extraction via Modal"]

    endpoint = os.getenv("MODAL_RECEIPT_ENDPOINT", "").strip()
    if not endpoint:
        return VisionExtractionResult(
            backend_name=BACKEND_NAME,
            model_name=UNKNOWN_MODEL,
            trace_messages=[
                "MODAL_RECEIPT_ENDPOINT is not set.",
                "Model endpoint is not connected yet.",
                "Use pasted/sample receipt text for the MVP path.",
            ],
        )

    if not image_path:
        return VisionExtractionResult(
            backend_name=BACKEND_NAME,
            model_name=UNKNOWN_MODEL,
            trace_messages=["No receipt image provided."],
        )

    request = VisionRequest(image_path=Path(str(image_path)))
    if not request.image_path.exists():
        return VisionExtractionResult(
            backend_name=BACKEND_NAME,
            model_name=UNKNOWN_MODEL,
            trace_messages=[f"Receipt image path does not exist: {request.image_path}"],
        )

    try:
        with request.image_path.open("rb") as f:
            response = requests.post(
                endpoint,
                files={"image": (request.image_path.name, f, "image/jpeg")},
                timeout=180,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        return VisionExtractionResult(
            backend_name=BACKEND_NAME,
            model_name=UNKNOWN_MODEL,
            trace_messages=[f"Modal request failed: {exc}"],
        )

    try:
        payload = response.json()
    except ValueError:
        return VisionExtractionResult(
            backend_name=BACKEND_NAME,
            model_name=UNKNOWN_MODEL,
            trace_messages=["Modal endpoint did not return valid JSON."],
        )

    if not isinstance(payload, dict):
        return VisionExtractionResult(
            backend_name=BACKEND_NAME,
            model_name=UNKNOWN_MODEL,
            trace_messages=["Modal endpoint JSON was not an object."],
        )

    return _result_from_modal_payload(payload, trace)


def extract_receipt_with_modal(image_path: Any) -> tuple[list[dict], list[str]]:
    result = _extract_receipt_result_with_modal(image_path)
    trace = list(result.trace_messages)

    if result.raw_text.strip():
        latency = (
            f" in {result.latency_seconds:.2f}s"
            if result.latency_seconds is not None
            else ""
        )
        trace.append(f"Modal returned raw text using {result.model_name}{latency}")
        rows, parser_trace = parse_receipt_text(result.raw_text)
        trace.extend(parser_trace)
        return rows, trace

    if result.rows:
        trace.append(f"Modal returned {len(result.rows)} structured rows")
        return result.rows, trace

    return [], trace + [
        "Modal endpoint returned no raw_text or rows.",
    ]
