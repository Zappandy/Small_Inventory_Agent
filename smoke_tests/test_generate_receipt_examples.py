from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_receipt_examples import generate_examples, write_examples


class GenerateReceiptExamplesTest(unittest.TestCase):
    def test_generation_is_deterministic_for_seed(self) -> None:
        first = generate_examples(count=5, seed=42)
        second = generate_examples(count=5, seed=42)

        self.assertEqual(first, second)

    def test_generated_examples_have_training_schema(self) -> None:
        examples = generate_examples(count=10, seed=3)

        for example in examples:
            self.assertIsInstance(example["input"], str)
            parsed = json.loads(example["output"])
            self.assertIn("supplier", parsed)
            self.assertIn("items", parsed)
            self.assertGreaterEqual(len(parsed["items"]), 1)
            for item in parsed["items"]:
                self.assertIn("product_raw", item)
                self.assertIn("qty_cases", item)
                self.assertIn("qty_units", item)
                self.assertIn("unit_cost", item)
                self.assertIn("total", item)

    def test_write_examples_validates_and_writes_jsonl(self) -> None:
        examples = generate_examples(count=3, seed=9)
        output_path = Path(tempfile.gettempdir()) / "dukaan_saathi_generated_examples_test.jsonl"

        write_examples(examples, output_path)

        lines = output_path.read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0])["input"], examples[0]["input"])


if __name__ == "__main__":
    unittest.main()
