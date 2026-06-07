from __future__ import annotations

import re
from typing import Any

from dukaan_saathi.storage import find_product


SKIP_WORDS = {
    "invoice",
    "bill no",
    "date",
    "gstin",
    "gst ",
    "gross sales",
    "cgst",
    "sgst",
    "net amount",
    "total:",
    "document type",
    "phone",
    "address",
}

def _looks_like_item_row(line: str) -> bool:
    lower = line.lower()

    # Pipe-separated invoice row:
    # Product | 5/0 | MRP 10.00 | RATE 8.625 | GST 5% | NET 3105.000
    if "|" in line and any(token in lower for token in ["rate", "net", "mrp"]):
        return True

    # Handwritten row:
    # Bingo(C) 4 X 870 = 3480
    if re.search(r"\d+(?:\.\d+)?\s*[xX*]\s*\d+(?:\.\d+)?", line):
        return True

    return False


def _should_skip_line(line: str) -> bool:
    lower = line.lower()

    if _looks_like_item_row(line):
        return False

    return any(word in lower for word in SKIP_WORDS)


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None

    cleaned = (
        value.replace(",", "")
        .replace("₹", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace("%", "")
        .strip()
    )

    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_product_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 .&()'-]", " ", value)
    return re.sub(r"\s+", " ", value).strip(" -:.")


def _parse_quantity(value: str | None) -> tuple[int | None, str]:
    if not value:
        return None, ""

    raw = value.strip()

    # Printed invoice style: 5/0, 10/0
    slash_match = re.match(r"^(\d+)\s*/\s*(\d+)$", raw)
    if slash_match:
        return int(slash_match.group(1)), raw

    number_match = re.search(r"\d+(?:\.\d+)?", raw)
    if number_match:
        return int(float(number_match.group(0))), raw

    return None, raw


def detect_supplier(raw_text: str) -> str:
    text = raw_text.lower()

    if "mahalakshmi marketing" in text:
        return "Mahalakshmi Marketing"

    if "venkateshwara" in text or "venkatesh" in text:
        return "Sri Venkateshwara Marketing"

    if "brundavan" in text or "bundavan" in text or "buns" in text:
        return "Brundavan Buns"

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for line in lines:
        match = re.search(r"(supplier|vendor|from)\s*[:\-]\s*(.+)", line, re.I)
        if match:
            return match.group(2).strip()

    for line in lines:
        lower = line.lower()
        if not any(word in lower for word in SKIP_WORDS) and not re.search(r"\d+\s*[xX*]\s*\d+", line):
            return line[:80]

    return "Unknown Supplier"


def detect_document_type(raw_text: str) -> str:
    text = raw_text.lower()

    explicit = re.search(r"document type\s*:\s*(.+)", raw_text, re.I)
    if explicit:
        return explicit.group(1).strip()

    if "tax invoice" in text or "cash bill" in text or "gst" in text:
        return "printed tax invoice"

    if "tally" in text or "buns" in text:
        return "handwritten tally note"

    return "handwritten supplier bill"


def _build_row(
    *,
    document_type: str,
    supplier: str,
    product_raw: str,
    quantity_raw: str,
    quantity: int,
    unit_price: float | None,
    total_price: float | None,
    confidence: float,
    warning: str,
) -> dict[str, Any]:
    product_raw = _clean_product_name(product_raw)
    matched = find_product(product_raw)

    matched_product_id = matched["id"] if matched else ""
    matched_product_name = matched["name"] if matched else ""

    if not matched:
        confidence = min(confidence, 0.55)
        warning = (warning + " | " if warning else "") + "No catalog match; owner must map or skip."

    return {
        "apply": True if matched else False,
        "document_type": document_type,
        "supplier": supplier,
        "product_raw": product_raw,
        "matched_product_id": matched_product_id,
        "matched_product_name": matched_product_name,
        "quantity_raw": quantity_raw,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "confidence": round(confidence, 2),
        "warning": warning,
    }


def _validate_math(quantity: int, unit_price: float | None, total_price: float | None) -> tuple[float, str]:
    if unit_price is None and total_price is None:
        return 0.6, "Missing price; stock quantity only."

    if unit_price is not None and total_price is None:
        return 0.75, "Total inferred from quantity × unit price."

    if unit_price is None and total_price is not None:
        return 0.65, "Missing unit price; keeping receipt total."

    expected = quantity * float(unit_price)
    actual = float(total_price)

    # Printed invoices often show per-piece rate but quantity is in cases,
    # so we warn instead of failing when math does not match.
    if abs(expected - actual) > max(1.0, 0.03 * max(expected, actual)):
        return 0.62, f"Check math: qty × rate = {expected:.2f}, receipt says {actual:.2f}."

    return 0.9, ""


def _parse_pipe_row(line: str, document_type: str, supplier: str) -> dict[str, Any] | None:
    if "|" not in line:
        return None

    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 2:
        return None

    product_raw = parts[0]
    quantity, quantity_raw = _parse_quantity(parts[1])
    if quantity is None:
        return None

    unit_price = None
    total_price = None

    for part in parts[2:]:
        lower = part.lower()

        if "rate" in lower:
            unit_price = _to_float(part.split()[-1])
        elif "net" in lower or "amount" in lower:
            total_price = _to_float(part.split()[-1])
        elif unit_price is None:
            # fallback: first plain number after quantity
            maybe = _to_float(part.split()[-1])
            if maybe is not None:
                unit_price = maybe

    confidence, warning = _validate_math(quantity, unit_price, total_price)

    return _build_row(
        document_type=document_type,
        supplier=supplier,
        product_raw=product_raw,
        quantity_raw=quantity_raw,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
        confidence=confidence,
        warning=warning,
    )


def _parse_multiply_row(line: str, document_type: str, supplier: str) -> dict[str, Any] | None:
    pattern = re.compile(
        r"^(?P<product>.+?)\s+"
        r"(?P<quantity>\d+(?:\.\d+)?)\s*[xX*]\s*"
        r"(?P<unit_price>\d+(?:\.\d+)?)"
        r"(?:\s*(?:=|rs\.?|inr)?\s*(?P<total_price>\d+(?:\.\d+)?))?\s*$",
        re.I,
    )

    match = pattern.match(line)
    if not match:
        return None

    product_raw = match.group("product")
    quantity, quantity_raw = _parse_quantity(match.group("quantity"))
    unit_price = _to_float(match.group("unit_price"))
    total_price = _to_float(match.group("total_price"))

    if quantity is None:
        return None

    if unit_price is not None and total_price is None:
        total_price = quantity * unit_price

    confidence, warning = _validate_math(quantity, unit_price, total_price)

    return _build_row(
        document_type=document_type,
        supplier=supplier,
        product_raw=product_raw,
        quantity_raw=quantity_raw,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
        confidence=confidence,
        warning=warning,
    )


def parse_receipt_text(raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    raw_text = raw_text or ""

    supplier = detect_supplier(raw_text)
    document_type = detect_document_type(raw_text)

    trace: list[str] = [
        f"Detected supplier: {supplier}",
        f"Detected document type: {document_type}",
    ]

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    trace.append(f"Read {len(lines)} non-empty lines")

    rows: list[dict[str, Any]] = []

    for line in lines:
        if _should_skip_line(line):
            continue

        parsed = (
            _parse_pipe_row(line, document_type, supplier)
            or _parse_multiply_row(line, document_type, supplier)
        )

        if parsed is None:
            trace.append(f"Skipped unparsed line: {line}")
            continue

        rows.append(parsed)

        if parsed["matched_product_name"]:
            trace.append(f"Matched '{parsed['product_raw']}' → {parsed['matched_product_name']}")
        else:
            trace.append(f"Needs owner review: '{parsed['product_raw']}'")

        if parsed["warning"]:
            trace.append(f"Warning for '{parsed['product_raw']}': {parsed['warning']}")

    trace.append(f"Extracted {len(rows)} candidate line items")
    return rows, trace
