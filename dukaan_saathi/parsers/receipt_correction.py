from __future__ import annotations

import re
from typing import Any

from dukaan_saathi.storage import find_product


NO_MATCH_WARNING = "No catalog match; owner must map or skip."
OWNER_SKIP_WARNING = "Skipped by owner."

ORDINAL_TO_INDEX = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
}


def _rows_to_records(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []

    if hasattr(rows, "to_dict"):
        return [dict(row) for row in rows.to_dict(orient="records")]

    if isinstance(rows, dict) and "headers" in rows and "data" in rows:
        headers = rows.get("headers") or []
        return [dict(zip(headers, values)) for values in rows.get("data") or []]

    return [dict(row) for row in rows]


def _split_commands(command_text: str) -> list[str]:
    text = command_text or ""

    # Supports: "first one Parle bulk and second one Bingo"
    text = re.sub(
        r"\s+(?:and|then)\s+(?=(?:first|1st|second|2nd|third|3rd|row\s*\d+|skip|quantity|qty)\b)",
        ", ",
        text,
        flags=re.I,
    )

    return [part.strip() for part in re.split(r"[,;\n]+", text) if part.strip()]


def _parse_row_index(command: str) -> int | None:
    lower = command.lower()

    row_match = re.search(r"\brow\s*(\d+)\b", lower)
    if row_match:
        return int(row_match.group(1)) - 1

    for word, index in ORDINAL_TO_INDEX.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return index

    return None


def _warning_parts(warning: Any) -> list[str]:
    return [
        part.strip()
        for part in str(warning or "").split("|")
        if part and part.strip()
    ]


def _set_warning_parts(row: dict[str, Any], parts: list[str]) -> None:
    row["warning"] = " | ".join(dict.fromkeys(parts))


def _append_warning(row: dict[str, Any], warning: str) -> None:
    parts = _warning_parts(row.get("warning"))
    if warning not in parts:
        parts.append(warning)
    _set_warning_parts(row, parts)


def _remove_owner_resolution_warnings(row: dict[str, Any]) -> None:
    parts = [
        part
        for part in _warning_parts(row.get("warning"))
        if part not in {NO_MATCH_WARNING, OWNER_SKIP_WARNING}
    ]
    _set_warning_parts(row, parts)


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _row_number(index: int) -> int:
    return index + 1


def _extract_product_text(command: str) -> str:
    match = re.match(
        r"^\s*(?:row\s*\d+|first|1st|second|2nd|third|3rd)(?:\s+one)?\s+(?P<product>.+?)\s*$",
        command,
        flags=re.I,
    )
    if not match:
        return ""

    product = match.group("product").strip()
    product = re.sub(r"^(?:is|as|to|product|item|name)\s+", "", product, flags=re.I)
    return product.strip(" .:-")


def _apply_product_update(row: dict[str, Any], product_text: str) -> str:
    row["product_raw"] = product_text

    matched = find_product(product_text)

    if matched:
        row["matched_product_id"] = matched["id"]
        row["matched_product_name"] = matched["name"]
        row["apply"] = True
        _remove_owner_resolution_warnings(row)

        current_confidence = float(row.get("confidence") or 0)
        row["confidence"] = round(max(current_confidence, 0.75), 2)

        return f"matched {matched['name']}"

    row["matched_product_id"] = ""
    row["matched_product_name"] = ""
    row["apply"] = False

    current_confidence = float(row.get("confidence") or 0.55)
    row["confidence"] = round(min(current_confidence, 0.55), 2)
    _append_warning(row, NO_MATCH_WARNING)

    return "no catalog match; apply=False"


def _apply_skip(row: dict[str, Any]) -> None:
    row["apply"] = False
    _append_warning(row, OWNER_SKIP_WARNING)


def _apply_quantity_update(row: dict[str, Any], quantity: int) -> None:
    row["quantity"] = quantity
    row["quantity_raw"] = str(quantity)


def _parse_quantity_value(command: str, row_index: int | None) -> int | None:
    numbers = re.findall(r"\d+(?:\.\d+)?", command)

    if not numbers:
        return None

    # For "quantity row 1 is 4", the last number is the desired quantity.
    if row_index is not None and len(numbers) == 1:
        only_number = _as_int(numbers[0])
        if only_number == _row_number(row_index):
            return None

    return _as_int(numbers[-1])


def apply_receipt_correction_command(
    rows: Any,
    command_text: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Apply phone-friendly owner corrections to parsed receipt rows.

    Supported examples:
    - first one Parle bulk
    - second one Bingo
    - row 1 Parle bulk
    - row 2 Bingo
    - skip row 2
    - quantity row 1 is 4
    """

    records = _rows_to_records(rows)
    trace: list[str] = []

    if not records:
        return records, ["No receipt rows to correct."]

    commands = _split_commands(command_text)

    if not commands:
        return records, ["No correction command provided."]

    for command in commands:
        row_index = _parse_row_index(command)

        if row_index is None:
            trace.append(f"Could not identify row in correction: {command}")
            continue

        if row_index < 0 or row_index >= len(records):
            trace.append(f"Row {_row_number(row_index)} is out of range: {command}")
            continue

        row = records[row_index]
        lower = command.lower()

        if re.search(r"\bskip\b", lower):
            _apply_skip(row)
            trace.append(f"Skipped row {_row_number(row_index)} by owner command.")
            continue

        if re.search(r"\b(?:quantity|qty)\b", lower):
            quantity = _parse_quantity_value(command, row_index)
            if quantity is None or quantity <= 0:
                trace.append(f"Could not parse positive quantity for row {_row_number(row_index)}: {command}")
                continue

            _apply_quantity_update(row, quantity)
            trace.append(f"Updated row {_row_number(row_index)} quantity to {quantity}.")
            continue

        product_text = _extract_product_text(command)

        if not product_text:
            trace.append(f"Could not parse product correction for row {_row_number(row_index)}: {command}")
            continue

        result = _apply_product_update(row, product_text)
        trace.append(f"Updated row {_row_number(row_index)} product to '{product_text}'; {result}.")

    return records, trace
