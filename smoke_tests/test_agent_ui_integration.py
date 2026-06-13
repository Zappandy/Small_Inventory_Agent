from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DB = Path(tempfile.gettempdir()) / "dukaan_saathi_agent_ui_test.db"
os.environ["DB_PATH"] = str(TEST_DB)

from dukaan_saathi.storage import init_db


class _BrokenReactAgent:
    def parse_stock_command(self, command: str):
        raise RuntimeError("react down")

    def parse_receipt_text(self, raw_text: str):
        raise RuntimeError("react down")


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

    def test_command_handler_uses_react_agent(self) -> None:
        from dukaan_saathi.ui import gradio_app

        action, trace, pending = gradio_app.handle_parse_command("Bingo అయిపోయింది")

        self.assertEqual(action["status"], "pending_approval")
        self.assertEqual(action["product_id"], "bingo_c")
        self.assertEqual(pending, action)
        self.assertIn("Thought:", trace)
        self.assertIn("Action: parse_stock_command_tool", trace)
        self.assertIn("Observation:", trace)

    def test_command_handler_falls_back_when_react_agent_unavailable(self) -> None:
        from dukaan_saathi.ui import gradio_app

        with patch.object(gradio_app, "_react_agent", return_value=_BrokenReactAgent()):
            action, trace, pending = gradio_app.handle_parse_command("Bingo అయిపోయింది")

        self.assertEqual(action["status"], "pending_approval")
        self.assertEqual(action["product_id"], "bingo_c")
        self.assertEqual(pending, action)
        self.assertIn("ReAct agent unavailable; using deterministic parser", trace)

    def test_receipt_handler_falls_back_when_agent_unavailable(self) -> None:
        from dukaan_saathi.ui import gradio_app

        raw_text = "Mahalakshmi Marketing\nBingo 4 X 870 = 3480"
        with patch.object(gradio_app.config, "RECEIPT_BACKEND", "deterministic"):
            with patch.object(gradio_app, "_react_agent", return_value=_BrokenReactAgent()):
                df, trace = gradio_app.handle_parse_receipt(None, raw_text)

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["matched_product_id"], "bingo_c")
        self.assertIn("ReAct agent unavailable; using configured receipt backend (deterministic)", trace)

    def test_hf_inference_backend_failure_returns_editable_fallback_rows(self) -> None:
        from dukaan_saathi.ui import gradio_app

        raw_text = "Mahalakshmi Marketing\nBingo 4 X 870 = 3480"
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(gradio_app.config, "RECEIPT_BACKEND", "hf_inference"):
                with patch.object(gradio_app, "_react_agent", return_value=_BrokenReactAgent()):
                    df, trace = gradio_app.handle_parse_receipt(None, raw_text)

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["matched_product_id"], "bingo_c")
        self.assertIn("Configured receipt backend (hf_inference) failed", trace)
        self.assertIn("Fallback parser produced editable rows", trace)

    def test_dashboard_stats_reflect_seed_inventory(self) -> None:
        from dukaan_saathi.ui import gradio_app

        stats = gradio_app.dashboard_stats()

        self.assertEqual(stats["total_items"], 6)
        self.assertGreaterEqual(stats["low_stock_count"], 1)
        self.assertGreaterEqual(stats["estimated_reorder_value"], 0)


if __name__ == "__main__":
    unittest.main()
