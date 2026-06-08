from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.storage import init_db


RECEIPT_IMAGES = [
    Path("samples/receipts/printed_out_receipt.jpeg"),
    Path("samples/receipts/receipt.jpeg"),
    Path("samples/receipts/tally.jpeg"),
]


def post_image(endpoint: str, image_path: Path) -> dict:
    start = time.perf_counter()

    with image_path.open("rb") as f:
        response = requests.post(
            endpoint,
            files={"image": (image_path.name, f, "image/jpeg")},
            timeout=240,
        )

    elapsed = time.perf_counter() - start
    response.raise_for_status()

    payload = response.json()
    payload["_client_latency_seconds"] = round(elapsed, 2)
    return payload


def score_payload(payload: dict) -> dict:
    raw_text = payload.get("raw_text") or payload.get("text") or ""

    rows, trace = parse_receipt_text(raw_text)

    matched = [row for row in rows if row.get("matched_product_id")]
    needs_review = [row for row in rows if not row.get("matched_product_id")]

    return {
        "model": payload.get("model", "unknown"),
        "raw_text_chars": len(raw_text),
        "parsed_row_count": len(rows),
        "matched_row_count": len(matched),
        "needs_review_count": len(needs_review),
        "client_latency_seconds": payload.get("_client_latency_seconds"),
        "server_latency_seconds": payload.get("latency_seconds"),
        "trace": trace,
        "raw_text": raw_text,
        "rows": rows,
    }


def main() -> None:
    init_db()

    endpoints = {
        "minicpm": os.getenv("MINICPM_RECEIPT_ENDPOINT", "").strip(),
        "molmo": os.getenv("MOLMO_RECEIPT_ENDPOINT", "").strip(),
    }

    endpoints = {name: url for name, url in endpoints.items() if url}
    if not endpoints:
        raise SystemExit(
            "Set at least one endpoint: MINICPM_RECEIPT_ENDPOINT or MOLMO_RECEIPT_ENDPOINT"
        )

    results = []

    for model_name, endpoint in endpoints.items():
        for image_path in RECEIPT_IMAGES:
            print(f"\n=== {model_name} :: {image_path.name} ===")

            try:
                payload = post_image(endpoint, image_path)
                score = score_payload(payload)
                score["endpoint_name"] = model_name
                score["image"] = image_path.name
                results.append(score)

                print(
                    json.dumps(
                        {
                            "model": score["model"],
                            "image": score["image"],
                            "raw_text_chars": score["raw_text_chars"],
                            "parsed_row_count": score["parsed_row_count"],
                            "matched_row_count": score["matched_row_count"],
                            "needs_review_count": score["needs_review_count"],
                            "client_latency_seconds": score["client_latency_seconds"],
                            "server_latency_seconds": score["server_latency_seconds"],
                        },
                        indent=2,
                    )
                )

            except Exception as exc:
                print(f"FAILED: {exc}")
                results.append(
                    {
                        "endpoint_name": model_name,
                        "image": image_path.name,
                        "error": str(exc),
                    }
                )

    out_dir = Path("benchmarks")
    out_dir.mkdir(exist_ok=True)

    out_path = out_dir / "receipt_model_benchmark.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
