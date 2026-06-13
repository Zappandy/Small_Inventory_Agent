from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DB = Path(tempfile.gettempdir()) / "dukaan_saathi_agent_ui_test.db"
os.environ["DB_PATH"] = str(TEST_DB)

from dukaan_saathi.storage import init_db


class AgentUiIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for suffix in ("", "-shm", "-wal"):
            path = Path(f"{TEST_DB}{suffix}")
            if path.exists():
                path.unlink()
        init_db()

    def test_gradio_app_imports_without_starting_agent(self) -> None:
        from dukaan_saathi.ui import gradio_app

        self.assertTrue(callable(gradio_app.build_demo))

    def test_agent_tools_import_with_smolagents_schema(self) -> None:
        from dukaan_saathi.agent import tools

        tools.reset_state()
        self.assertIsNone(tools.get_last_action())

    def test_command_handler_falls_back_when_agent_unavailable(self) -> None:
        from dukaan_saathi.ui import gradio_app

        with patch.object(gradio_app, "_run_agent", side_effect=RuntimeError("llama down")):
            action, trace, pending = gradio_app.handle_parse_command("Bingo అయిపోయింది")

        self.assertEqual(action["status"], "pending_approval")
        self.assertEqual(action["product_id"], "bingo_c")
        self.assertEqual(pending, action)
        self.assertIn("Agent unavailable; using deterministic parser", trace)

    def test_receipt_handler_falls_back_when_agent_unavailable(self) -> None:
        from dukaan_saathi.ui import gradio_app

        raw_text = "Mahalakshmi Marketing\nBingo 4 X 870 = 3480"
        with patch.object(gradio_app, "_run_agent", side_effect=RuntimeError("llama down")):
            df, trace = gradio_app.handle_parse_receipt(None, raw_text)

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["matched_product_id"], "bingo_c")
        self.assertIn("Agent unavailable; using deterministic parser", trace)


if __name__ == "__main__":
    unittest.main()
