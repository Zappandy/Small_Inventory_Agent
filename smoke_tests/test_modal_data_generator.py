from __future__ import annotations

import json
import unittest

from modal_apps.receipt_data_generator import (
    _dedupe_examples,
    _extract_json_array,
    _validate_training_example,
)


class ModalDataGeneratorTest(unittest.TestCase):
    def test_extract_json_array_from_markdown_output(self) -> None:
        text = '```json\n[{"input": "x", "output": "{\\"items\\": []}"}]\n```'

        parsed = _extract_json_array(text)

        self.assertEqual(parsed[0]["input"], "x")

    def test_validate_normalizes_output_object_to_json_string(self) -> None:
        example = {
            "input": "Receipt\nBingo 2 X 10 = 20",
            "output": {
                "supplier": "Receipt",
                "invoice_no": None,
                "date": "2026-06-01",
                "items": [
                    {
                        "product_raw": "Bingo",
                        "qty_cases": 0,
                        "qty_units": 2,
                        "unit_cost": 10.0,
                        "total": 20.0,
                    }
                ],
                "subtotal": 20.0,
                "discount": 0.0,
                "gst": 0.0,
                "net_total": 20.0,
            },
        }

        validated = _validate_training_example(example)

        self.assertIsInstance(validated["output"], str)
        self.assertEqual(json.loads(validated["output"])["items"][0]["product_raw"], "Bingo")

    def test_dedupe_examples_by_input(self) -> None:
        examples = [
            {"input": "same", "output": "{}"},
            {"input": "same", "output": "{}"},
            {"input": "other", "output": "{}"},
        ]

        deduped = _dedupe_examples(examples)

        self.assertEqual([example["input"] for example in deduped], ["same", "other"])


if __name__ == "__main__":
    unittest.main()
