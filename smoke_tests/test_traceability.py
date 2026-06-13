from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dukaan_saathi.traceability import build_file_ref, file_sha256, jsonl_count, write_manifest


class TraceabilityTest(unittest.TestCase):
    def test_file_ref_includes_hash_and_jsonl_count(self) -> None:
        path = Path(tempfile.gettempdir()) / "dukaan_saathi_traceability_test.jsonl"
        path.write_text('{"x": 1}\n\n{"x": 2}\n', encoding="utf-8")

        ref = build_file_ref(path)

        self.assertEqual(ref["path"], str(path))
        self.assertEqual(ref["records"], 2)
        self.assertEqual(ref["sha256"], file_sha256(path))
        self.assertEqual(jsonl_count(path), 2)

    def test_write_manifest_adds_run_id_and_created_at(self) -> None:
        trace_dir = Path(tempfile.gettempdir()) / "dukaan_saathi_traceability_runs"
        path = write_manifest(
            {
                "run_id": "trace-test",
                "kind": "unit-test",
                "status": "succeeded",
            },
            trace_dir=trace_dir,
        )

        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "trace-test.json")
        self.assertEqual(payload["kind"], "unit-test")
        self.assertEqual(payload["status"], "succeeded")
        self.assertIn("created_at", payload)


if __name__ == "__main__":
    unittest.main()
