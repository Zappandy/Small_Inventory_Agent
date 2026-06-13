from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DB = Path(tempfile.gettempdir()) / "dukaan_saathi_modal_receipt_llm_test.db"
os.environ["DB_PATH"] = str(TEST_DB)

from dukaan_saathi.integrations.modal_receipt_llm import parse_receipt_with_modal_llm
from dukaan_saathi.storage import init_db


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class ModalReceiptLlmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for suffix in ("", "-shm", "-wal"):
            path = Path(f"{TEST_DB}{suffix}")
            if path.exists():
                path.unlink()
        init_db()

    def test_modal_parser_success_maps_to_editable_rows(self) -> None:
        payload = {
            "model": "modal-test",
            "parsed": {
                "supplier": "Mahalakshmi Marketing",
                "items": [
                    {
                        "product_raw": "Bingo(C)",
                        "qty_cases": 4,
                        "qty_units": 4,
                        "unit_cost": 870.0,
                        "total": 3480.0,
                    }
                ],
            },
            "latency_seconds": 1.25,
        }

        with patch.dict(os.environ, {"MODAL_RECEIPT_LLM_ENDPOINT": "https://example.test/parse"}):
            with patch("dukaan_saathi.integrations.modal_receipt_llm.requests.post", return_value=_FakeResponse(payload)):
                rows, trace = parse_receipt_with_modal_llm("Bingo(C) 4 X 870 = 3480")

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["apply"])
        self.assertEqual(rows[0]["matched_product_id"], "bingo_c")
        self.assertIn("[modal_llm] Parsed 1 rows with modal-test", "\n".join(trace))

    def test_missing_endpoint_falls_back_to_deterministic_parser(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            rows, trace = parse_receipt_with_modal_llm("Mahalakshmi Marketing\nBingo 4 X 870 = 3480")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["matched_product_id"], "bingo_c")
        self.assertIn("MODAL_RECEIPT_LLM_ENDPOINT is not set", "\n".join(trace))

    def test_bad_response_falls_back_to_deterministic_parser(self) -> None:
        payload = {"model": "modal-test", "raw_json": "{\"items\": []}"}

        with patch.dict(os.environ, {"MODAL_RECEIPT_LLM_ENDPOINT": "https://example.test/parse"}):
            with patch("dukaan_saathi.integrations.modal_receipt_llm.requests.post", return_value=_FakeResponse(payload)):
                rows, trace = parse_receipt_with_modal_llm("Mahalakshmi Marketing\nBingo 4 X 870 = 3480")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["matched_product_id"], "bingo_c")
        self.assertIn("Fallback to deterministic parser", "\n".join(trace))


if __name__ == "__main__":
    unittest.main()
