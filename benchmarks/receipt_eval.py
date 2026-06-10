from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from statistics import mean
from typing import Any


# Keep benchmark isolated from the normal local app DB unless DB_PATH is explicitly set.
if not os.getenv("DB_PATH"):
    os.environ["DB_PATH"] = str(Path(tempfile.gettempdir()) / "dukaan_saathi_receipt_eval.db")

from dukaan_saathi.parsers.receipt_correction import apply_receipt_correction_command
from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.storage import init_db


DEFAULT_INPUT_GLOBS = [
    "samples/receipt_text/*.txt",
    "smoke_tests/fixtures/*receipt*.txt",
]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none"}

    return bool(value)


def _row_is_matched(row: dict[str, Any]) -> bool:
    return bool(str(row.get("matched_product_id") or "").strip())


def _row_needs_review(row: dict[str, Any]) -> bool:
    if not _as_bool(row.get("apply")):
        return True

    if not _row_is_matched(row):
        return True

    warning = str(row.get("warning") or "").strip()
    if "No catalog match" in warning:
        return True

    return False


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_receipt(path: Path, correction_command: str | None = None) -> dict[str, Any]:
    raw_text = path.read_text()
    rows, trace = parse_receipt_text(raw_text)

    rows_extracted = len(rows)
    auto_matched_rows = sum(1 for row in rows if _row_is_matched(row))
    rows_needing_review = sum(1 for row in rows if _row_needs_review(row))
    warnings_count = sum(1 for row in rows if str(row.get("warning") or "").strip())

    confidences = [
        value
        for row in rows
        if (value := _safe_float(row.get("confidence"))) is not None
    ]

    result: dict[str, Any] = {
        "receipt_file": str(path),
        "rows_extracted": rows_extracted,
        "auto_matched_rows": auto_matched_rows,
        "rows_needing_review": rows_needing_review,
        "correction_burden_pct": round(
            100.0 * rows_needing_review / rows_extracted,
            1,
        )
        if rows_extracted
        else 0.0,
        "avg_confidence": round(mean(confidences), 2) if confidences else None,
        "warnings_count": warnings_count,
        "products_raw": "; ".join(str(row.get("product_raw") or "") for row in rows),
        "matched_names": "; ".join(str(row.get("matched_product_name") or "") for row in rows),
        "warnings": " || ".join(
            str(row.get("warning") or "")
            for row in rows
            if str(row.get("warning") or "").strip()
        ),
        "trace_summary": " | ".join(trace[-3:]),
    }

    if correction_command:
        corrected_rows, correction_trace = apply_receipt_correction_command(rows, correction_command)
        corrected_matched_rows = sum(1 for row in corrected_rows if _row_is_matched(row))
        corrected_rows_needing_review = sum(1 for row in corrected_rows if _row_needs_review(row))

        result.update(
            {
                "correction_command": correction_command,
                "matched_rows_after_correction": corrected_matched_rows,
                "rows_needing_review_after_correction": corrected_rows_needing_review,
                "correction_burden_after_correction_pct": round(
                    100.0 * corrected_rows_needing_review / rows_extracted,
                    1,
                )
                if rows_extracted
                else 0.0,
                "correction_trace": " | ".join(correction_trace),
            }
        )

    return result


def collect_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []

    for item in inputs:
        matches = sorted(Path().glob(item))

        if matches:
            paths.extend(path for path in matches if path.is_file())
            continue

        path = Path(item)
        if path.is_file():
            paths.append(path)

    unique_paths: list[Path] = []
    seen = set()

    for path in paths:
        resolved = str(path)
        if resolved not in seen:
            unique_paths.append(path)
            seen.add(resolved)

    return unique_paths


def parse_corrections(values: list[str]) -> dict[str, str]:
    corrections: dict[str, str] = {}

    for value in values:
        if "::" not in value:
            raise ValueError(
                "Corrections must use FILE::COMMAND format, "
                "for example smoke_tests/fixtures/minicpm_receipt_raw_text_actual.txt::first one Parle bulk, second one Bingo"
            )

        file_name, command = value.split("::", 1)
        corrections[file_name.strip()] = command.strip()

    return corrections


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with output_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


def markdown_table(rows: list[dict[str, Any]]) -> str:
    columns = [
        "receipt_file",
        "rows_extracted",
        "auto_matched_rows",
        "rows_needing_review",
        "correction_burden_pct",
        "avg_confidence",
        "warnings_count",
    ]

    optional_columns = [
        "matched_rows_after_correction",
        "rows_needing_review_after_correction",
        "correction_burden_after_correction_pct",
    ]

    for column in optional_columns:
        if any(column in row for row in rows):
            columns.append(column)

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]

    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")

    return "\n".join(lines)


def print_summary(rows: list[dict[str, Any]]) -> None:
    total_receipts = len(rows)
    total_rows = sum(int(row["rows_extracted"]) for row in rows)
    total_matched = sum(int(row["auto_matched_rows"]) for row in rows)
    total_review = sum(int(row["rows_needing_review"]) for row in rows)

    print("\n=== Receipt correction-burden benchmark ===")
    print(f"Receipts evaluated: {total_receipts}")
    print(f"Rows extracted: {total_rows}")
    print(f"Auto-matched rows: {total_matched}")
    print(f"Rows needing owner review: {total_review}")

    if total_rows:
        print(f"Overall correction burden: {100.0 * total_review / total_rows:.1f}%")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate receipt parsing by correction burden, not OCR character accuracy."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Receipt text files or glob patterns. Defaults to sample and smoke-test receipt fixtures.",
    )
    parser.add_argument(
        "--correction",
        action="append",
        default=[],
        help="Optional FILE::COMMAND correction to evaluate after owner correction.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "csv", "json"],
        default="markdown",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional output path. If omitted, prints markdown/json or summary to stdout.",
    )

    args = parser.parse_args()

    init_db()

    inputs = args.inputs or DEFAULT_INPUT_GLOBS
    paths = collect_paths(inputs)

    if not paths:
        raise SystemExit(f"No receipt files found for inputs: {inputs}")

    corrections = parse_corrections(args.correction)

    results = []
    for path in paths:
        correction = corrections.get(str(path)) or corrections.get(path.name)
        results.append(evaluate_receipt(path, correction))

    print_summary(results)

    if args.format == "markdown":
        output = markdown_table(results)
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output + "\n")
            print(f"Wrote markdown benchmark to {out_path}")
        else:
            print(output)

    elif args.format == "json":
        if args.out:
            write_json(results, Path(args.out))
            print(f"Wrote JSON benchmark to {args.out}")
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.format == "csv":
        if not args.out:
            raise SystemExit("--out is required for CSV output")
        write_csv(results, Path(args.out))
        print(f"Wrote CSV benchmark to {args.out}")


if __name__ == "__main__":
    main()
