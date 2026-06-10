from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


TEST_DB = Path(tempfile.gettempdir()) / "dukaan_saathi_receipt_parser_test.db"
os.environ["DB_PATH"] = str(TEST_DB)

from dukaan_saathi.parsers.receipt_correction import apply_receipt_correction_command
from dukaan_saathi.parsers.receipt_text import parse_receipt_text
from dukaan_saathi.storage import init_db


class ReceiptCorrectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for suffix in ("", "-shm", "-wal"):
            path = Path(f"{TEST_DB}{suffix}")
            if path.exists():
                path.unlink()
        init_db()

    def _actual_minicpm_rows(self):
        raw_text = Path("smoke_tests/fixtures/minicpm_receipt_raw_text_actual.txt").read_text()
        rows, _ = parse_receipt_text(raw_text)
        self.assertEqual(len(rows), 2)
        return rows

    def test_correct_first_second_products(self) -> None:
        rows = self._actual_minicpm_rows()

        corrected, trace = apply_receipt_correction_command(
            rows,
            "first one Parle bulk, second one Bingo",
        )

        self.assertTrue(corrected[0]["apply"])
        self.assertEqual(corrected[0]["product_raw"], "Parle bulk")
        self.assertEqual(corrected[0]["matched_product_id"], "parle_bulk")
        self.assertEqual(corrected[0]["matched_product_name"], "Parle (bulk)")

        self.assertTrue(corrected[1]["apply"])
        self.assertEqual(corrected[1]["product_raw"], "Bingo")
        self.assertEqual(corrected[1]["matched_product_id"], "bingo_c")
        self.assertEqual(corrected[1]["matched_product_name"], "Bingo (C)")

        self.assertIn("Updated row 1 product to 'Parle bulk'; matched Parle (bulk).", trace)
        self.assertIn("Updated row 2 product to 'Bingo'; matched Bingo (C).", trace)

    def test_correct_row_number_products(self) -> None:
        rows = self._actual_minicpm_rows()

        corrected, _ = apply_receipt_correction_command(
            rows,
            "row 1 Parle bulk, row 2 Bingo",
        )

        self.assertTrue(corrected[0]["apply"])
        self.assertEqual(corrected[0]["matched_product_name"], "Parle (bulk)")
        self.assertTrue(corrected[1]["apply"])
        self.assertEqual(corrected[1]["matched_product_name"], "Bingo (C)")

    def test_skip_row(self) -> None:
        rows = self._actual_minicpm_rows()

        corrected, trace = apply_receipt_correction_command(rows, "skip row 2")

        self.assertFalse(corrected[1]["apply"])
        self.assertIn("Skipped by owner.", corrected[1]["warning"])
        self.assertIn("Skipped row 2 by owner command.", trace)

    def test_quantity_update(self) -> None:
        rows = self._actual_minicpm_rows()

        corrected, trace = apply_receipt_correction_command(rows, "quantity row 1 is 4")

        self.assertEqual(corrected[0]["quantity"], 4)
        self.assertEqual(corrected[0]["quantity_raw"], "4")
        self.assertIn("Updated row 1 quantity to 4.", trace)

    def test_unmatched_product_keeps_apply_false(self) -> None:
        rows = self._actual_minicpm_rows()

        corrected, trace = apply_receipt_correction_command(rows, "row 1 Totally Unknown Item")

        self.assertFalse(corrected[0]["apply"])
        self.assertEqual(corrected[0]["product_raw"], "Totally Unknown Item")
        self.assertEqual(corrected[0]["matched_product_id"], "")
        self.assertEqual(corrected[0]["matched_product_name"], "")
        self.assertIn("No catalog match", corrected[0]["warning"])
        self.assertIn("Updated row 1 product to 'Totally Unknown Item'; no catalog match; apply=False.", trace)


if __name__ == "__main__":
    unittest.main()
