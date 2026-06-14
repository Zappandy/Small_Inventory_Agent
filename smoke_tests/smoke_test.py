from pathlib import Path

import pandas as pd

from dukaan_saathi.storage import init_db, get_inventory
from dukaan_saathi.parsers.stock_command import parse_stock_command
from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.services.inventory import approve_command_action, approve_receipt_rows
from dukaan_saathi.services.reorder import draft_reorder


def main() -> None:
    init_db()

    print("\n=== Inventory ===")
    print(f"rows: {len(get_inventory())}")

    print("\n=== Stock command ===")
    action, trace = parse_stock_command("add Bun 12")
    print(action)
    for line in trace:
        print("-", line)

    message, trace = approve_command_action(action)
    print(message)
    for line in trace:
        print("-", line)

    print("\n=== Receipt samples ===")
    for path in sorted(Path("samples/receipt_text").glob("*.txt")):
        print(f"\n--- {path.name} ---")
        rows, trace = parse_receipt_text(path.read_text())
        print(f"rows: {len(rows)}")
        for line in trace:
            print("-", line)

    print("\n=== Approve sample receipt ===")
    sample_path = Path("samples/receipt_text/handwritten_mahalakshmi.txt")
    rows, _ = parse_receipt_text(sample_path.read_text())
    message, trace = approve_receipt_rows(pd.DataFrame(rows))
    print(message)
    for line in trace:
        print("-", line)

    print("\n=== Reorder draft ===")
    rows, trace = draft_reorder()
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
