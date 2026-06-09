from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


TEST_DB = Path(tempfile.gettempdir()) / "dukaan_saathi_receipt_parser_test.db"
os.environ["DB_PATH"] = str(TEST_DB)

from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.storage import init_db


class ReceiptParserRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for suffix in ("", "-shm", "-wal"):
            path = Path(f"{TEST_DB}{suffix}")
            if path.exists():
                path.unlink()
        init_db()


    def test_actual_minicpm_receipt_output_populates_owner_review_rows(self) -> None:
        raw_text = Path("smoke_tests/fixtures/minicpm_receipt_raw_text_actual.txt").read_text()
    
        rows, trace = parse_receipt_text(raw_text)
    
        self.assertEqual(len(rows), 2)
    
        self.assertEqual(rows[0]["supplier"], "Mahalakshmi Marketing")
        self.assertEqual(rows[0]["product_raw"], "Port")
        self.assertEqual(rows[0]["quantity"], 1)
        self.assertEqual(rows[0]["unit_price"], 2450.0)
        self.assertEqual(rows[0]["total_price"], 2450.0)
        self.assertFalse(rows[0]["apply"])
        self.assertIn("No catalog match", rows[0]["warning"])
    
        self.assertEqual(rows[1]["product_raw"], "Rs.g c")
        self.assertEqual(rows[1]["quantity"], 4)
        self.assertEqual(rows[1]["unit_price"], 8702.0)
        self.assertEqual(rows[1]["total_price"], 3480.0)
        self.assertFalse(rows[1]["apply"])
        self.assertIn("Check math", rows[1]["warning"])
        self.assertIn("No catalog match", rows[1]["warning"])
    
        self.assertIn("Detected supplier: Mahalakshmi Marketing", trace)
        self.assertIn("Extracted 2 candidate line items", trace)
    
    def test_current_minicpm_receipt_fixture_parse_behavior(self) -> None:
        raw_text = Path("smoke_tests/fixtures/minicpm_receipt_raw_text.txt").read_text()

        rows, trace = parse_receipt_text(raw_text)

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            rows,
            [
                {
                    "apply": True,
                    "document_type": "handwritten supplier bill",
                    "supplier": "Mahalakshmi Marketing",
                    "product_raw": "Parle bulk",
                    "matched_product_id": "parle_bulk",
                    "matched_product_name": "Parle (bulk)",
                    "quantity_raw": "1",
                    "quantity": 1,
                    "unit_price": 2450.0,
                    "total_price": 2450.0,
                    "confidence": 0.9,
                    "warning": "",
                },
                {
                    "apply": True,
                    "document_type": "handwritten supplier bill",
                    "supplier": "Mahalakshmi Marketing",
                    "product_raw": "Bingo(C)",
                    "matched_product_id": "bingo_c",
                    "matched_product_name": "Bingo (C)",
                    "quantity_raw": "4",
                    "quantity": 4,
                    "unit_price": 870.0,
                    "total_price": 3480.0,
                    "confidence": 0.9,
                    "warning": "",
                },
                {
                    "apply": False,
                    "document_type": "handwritten supplier bill",
                    "supplier": "Mahalakshmi Marketing",
                    "product_raw": "Unknown handwritten item",
                    "matched_product_id": "",
                    "matched_product_name": "",
                    "quantity_raw": "1",
                    "quantity": 1,
                    "unit_price": 612.0,
                    "total_price": 612.0,
                    "confidence": 0.55,
                    "warning": "No catalog match; owner must map or skip.",
                },
            ],
        )
        self.assertIn("Detected supplier: Mahalakshmi Marketing", trace)
        self.assertIn("Extracted 3 candidate line items", trace)


if __name__ == "__main__":
    unittest.main()
