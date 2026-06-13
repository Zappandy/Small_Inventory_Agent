from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any


SUPPLIERS = [
    {
        "name": "Mahalakshmi Marketing",
        "document_type": "handwritten supplier bill",
        "products": [
            ("Parle bulk", 2450.0),
            ("Bingo(C)", 870.0),
            ("Lays Classic", 480.0),
            ("Parle-G", 50.0),
        ],
    },
    {
        "name": "Sri Venkateshwara Marketing",
        "document_type": "printed tax invoice",
        "products": [
            ("PARLE-G 60GM RS.72P", 8.625),
            ("HAPPY HAPPY 27.5G(24P)*13", 4.464),
            ("LAYS CLASSIC 52G", 12.5),
            ("BINGO MAD ANGLES", 9.75),
        ],
    },
    {
        "name": "Brundavan Buns",
        "document_type": "handwritten tally note",
        "products": [
            ("Bun", 10.0),
            ("OBM", 9.5),
            ("Item one", 28.0),
            ("Milk bread", 32.0),
        ],
    },
]


def _money(value: float) -> float:
    return round(float(value), 2)


def _receipt_date(rng: random.Random) -> date:
    return date(2026, 5, 20) + timedelta(days=rng.randint(0, 20))


def _sample_items(rng: random.Random, supplier: dict[str, Any]) -> list[dict[str, Any]]:
    product_count = rng.randint(2, min(4, len(supplier["products"])))
    selected = rng.sample(supplier["products"], product_count)
    items: list[dict[str, Any]] = []

    for product_raw, unit_cost in selected:
        qty = rng.choice([1, 2, 3, 4, 5, 8, 10, 12, 24])
        if supplier["document_type"] == "printed tax invoice":
            qty_cases = rng.choice([0, qty])
            qty_units = 0 if qty_cases else qty
        else:
            qty_cases = 0 if supplier["document_type"] == "handwritten tally note" else qty
            qty_units = qty

        total = _money(qty * unit_cost)
        items.append(
            {
                "product_raw": product_raw,
                "qty_cases": int(qty_cases),
                "qty_units": int(qty_units),
                "unit_cost": _money(unit_cost),
                "total": total,
            }
        )

    return items


def _render_handwritten(
    supplier: dict[str, Any],
    invoice_no: str,
    bill_date: date,
    items: list[dict[str, Any]],
    rng: random.Random,
) -> str:
    lines = [
        supplier["name"],
        f"No. {invoice_no}  Date: {bill_date:%d/%m/%y}",
        "M/s. Veerabhadra Stores",
        "",
    ]
    for item in items:
        qty = item["qty_units"] or item["qty_cases"]
        separator = rng.choice([" X ", " x ", "X"])
        lines.append(
            f"{item['product_raw']}  {qty}{separator}{item['unit_cost']} = {item['total']}"
        )
    lines.append("")
    lines.append(f"Total {_money(sum(item['total'] for item in items))}")
    return "\n".join(lines)


def _render_printed(
    supplier: dict[str, Any],
    invoice_no: str,
    bill_date: date,
    items: list[dict[str, Any]],
    rng: random.Random,
) -> str:
    lines = [
        supplier["name"],
        "GSTIN: 36AZLIPV6442K12M",
        "CUSTOMER: VEERA BHADRA WS",
        f"Invoice No: {invoice_no}",
        f"Bill Date: {bill_date:%d/%m/%Y}",
        "",
    ]
    for index, item in enumerate(items, start=1):
        qty = item["qty_cases"] or item["qty_units"]
        qty_text = rng.choice([f"{qty}/0", str(qty)])
        lines.append(
            f"{index} {item['product_raw']} | QTY {qty_text} | RATE {item['unit_cost']} | NET {item['total']}"
        )
    subtotal = _money(sum(item["total"] for item in items))
    gst = _money(subtotal * 0.05)
    lines.extend(
        [
            "",
            f"GROSS SALES: {subtotal}",
            f"GST: {gst}",
            f"NET AMOUNT: {_money(subtotal + gst)}",
        ]
    )
    return "\n".join(lines)


def _render_tally(
    supplier: dict[str, Any],
    invoice_no: str,
    bill_date: date,
    items: list[dict[str, Any]],
    rng: random.Random,
) -> str:
    lines = [
        supplier["name"],
        f"Date: {bill_date:%d/%m}",
        "",
    ]
    for item in items:
        qty = item["qty_units"] or item["qty_cases"]
        lines.append(f"{item['product_raw']} {qty}X{item['unit_cost']} {item['total']}")
    lines.append("")
    lines.append(f"Total: {_money(sum(item['total'] for item in items))}")
    return "\n".join(lines)


def _render_input(
    supplier: dict[str, Any],
    invoice_no: str,
    bill_date: date,
    items: list[dict[str, Any]],
    rng: random.Random,
) -> str:
    doc_type = supplier["document_type"]
    if doc_type == "printed tax invoice":
        return _render_printed(supplier, invoice_no, bill_date, items, rng)
    if doc_type == "handwritten tally note":
        return _render_tally(supplier, invoice_no, bill_date, items, rng)
    return _render_handwritten(supplier, invoice_no, bill_date, items, rng)


def generate_examples(count: int, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)
    examples: list[dict[str, str]] = []

    for index in range(count):
        supplier = rng.choice(SUPPLIERS)
        bill_date = _receipt_date(rng)
        invoice_no = str(3000 + index + rng.randint(0, 500))
        items = _sample_items(rng, supplier)
        subtotal = _money(sum(item["total"] for item in items))
        gst = _money(subtotal * 0.05) if supplier["document_type"] == "printed tax invoice" else 0.0
        parsed = {
            "supplier": supplier["name"],
            "invoice_no": invoice_no if supplier["document_type"] != "handwritten tally note" else None,
            "date": bill_date.isoformat(),
            "items": items,
            "subtotal": subtotal,
            "discount": 0.0,
            "gst": gst,
            "net_total": _money(subtotal + gst),
        }
        examples.append(
            {
                "input": _render_input(supplier, invoice_no, bill_date, items, rng),
                "output": json.dumps(parsed, ensure_ascii=False),
            }
        )

    return examples


def _load_base_examples(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def _validate_example(example: dict[str, str]) -> None:
    if not isinstance(example.get("input"), str) or not example["input"].strip():
        raise ValueError("Example input must be non-empty text")
    output = json.loads(example["output"])
    if not isinstance(output.get("items"), list) or not output["items"]:
        raise ValueError("Example output must contain at least one item")
    for item in output["items"]:
        for field in ("product_raw", "qty_cases", "qty_units", "unit_cost", "total"):
            if field not in item:
                raise ValueError(f"Example item missing field: {field}")


def write_examples(examples: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for example in examples:
        _validate_example(example)
    output_path.write_text(
        "\n".join(json.dumps(example, ensure_ascii=False) for example in examples) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic receipt fine-tuning examples.")
    parser.add_argument("--count", type=int, default=48)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--base", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/finetune/generated/receipt_examples_synthetic.jsonl"),
    )
    args = parser.parse_args()

    examples = _load_base_examples(args.base) + generate_examples(args.count, args.seed)
    write_examples(examples, args.output)
    print(f"Wrote {len(examples)} examples to {args.output}")


if __name__ == "__main__":
    main()
