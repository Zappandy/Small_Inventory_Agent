from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DB = Path(tempfile.gettempdir()) / "dukaan_saathi_agent_ui_test.db"


def _app_module():
    os.environ["DB_PATH"] = str(TEST_DB)
    if "app" in sys.modules:
        return sys.modules["app"]
    return importlib.import_module("app")


class CustomAppSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if "app" not in sys.modules:
            for suffix in ("", "-shm", "-wal"):
                path = Path(f"{TEST_DB}{suffix}")
                if path.exists():
                    path.unlink()

    def test_voice_parse_requires_apply_before_stock_write(self) -> None:
        app = _app_module()
        state = app._new_state()
        before = app.db.get_product("bun")["quantity"]

        try:
            state, parse_toast = app._h_voice_command(state, {"text": "add Bun 12"})
            after_parse = app.db.get_product("bun")["quantity"]

            self.assertEqual(after_parse, before)
            self.assertIn("approve before stock changes", parse_toast)
            self.assertTrue(state["voice_result"]["needs_approval"])

            state, apply_toast = app._h_voice_apply(state, state["voice_result"])
            after_apply = app.db.get_product("bun")["quantity"]

            self.assertEqual(after_apply, before + 12)
            self.assertIn("success|Added 12 to Bun", apply_toast)
        finally:
            app.db.adjust_stock("bun", before, mode="set")

    def test_add_to_order_persists_pending_order(self) -> None:
        app = _app_module()
        state = app._new_state()

        state, toast = app._h_add_to_order(state, {"pid": "bun", "qty": "3"})

        self.assertEqual(state["page"], "orders")
        self.assertEqual(state["orders_filter"], "pending")
        self.assertIn("Reorder queued for Bun", toast)
        self.assertTrue(
            any(
                order["product_id"] == "bun"
                and order["status"] == "pending"
                and float(order["qty_needed"]) == 3.0
                for order in app.db.get_pending_orders()
            )
        )

    def test_mark_order_received_requires_approval_then_updates_stock(self) -> None:
        app = _app_module()
        before = app.db.get_product("bun")["quantity"]
        app.db.insert_orders([
            {
                "product_id": "bun",
                "product_name": "Bun",
                "qty_needed": 2,
                "unit": "piece",
                "reason": "Safety test order",
                "ai_confidence": 1.0,
            }
        ])
        order = next(
            order for order in app.db.get_pending_orders()
            if order["product_id"] == "bun" and order["reason"] == "Safety test order"
        )

        try:
            state = app._new_state()
            state, early_toast = app._h_mark_order_received(state, {"oid": order["id"]})
            self.assertIn("Approve the order before marking it received", early_toast)
            self.assertEqual(app.db.get_product("bun")["quantity"], before)

            app.db.update_order_status(order["id"], "approved")
            state, received_toast = app._h_mark_order_received(state, {"oid": order["id"]})

            self.assertIn("stock updated", received_toast)
            self.assertEqual(app.db.get_product("bun")["quantity"], before + 2)
        finally:
            app.db.adjust_stock("bun", before, mode="set")

    def test_receipt_rows_are_matched_to_existing_inventory(self) -> None:
        app = _app_module()
        trace: list[str] = []

        rows = app._match_receipt_rows([
            {"product_raw": "Bingo", "quantity": 4, "matched_product_id": None}
        ], trace)

        self.assertEqual(rows[0]["matched_product_id"], "bingo_c")
        self.assertEqual(rows[0]["matched_product_name"], "Bingo (C)")
        self.assertTrue(any("Matched 'Bingo'" in line for line in trace))

    def test_demo_aliases_cover_common_product_variants(self) -> None:
        app = _app_module()

        self.assertEqual(app.db.find_by_name("bread bun")[0]["id"], "bun")
        self.assertEqual(app.db.find_by_name("Parle biscuit")[0]["id"], "parle_bulk")
        self.assertEqual(app.db.find_by_name("O B M")[0]["id"], "obm")

    def test_fractional_stock_delta_is_preserved(self) -> None:
        app = _app_module()
        before = app.db.get_product("bun")["quantity"]

        try:
            app.db.adjust_stock("bun", 0.5, mode="add")
            after = app.db.get_product("bun")["quantity"]
            self.assertEqual(after, before + 0.5)
        finally:
            app.db.adjust_stock("bun", before, mode="set")

    def test_stock_ledger_delta_column_is_real(self) -> None:
        app = _app_module()

        conn = app.db.get_conn()
        try:
            columns = conn.execute("PRAGMA table_info(stock_ledger)").fetchall()
        finally:
            conn.close()

        delta_column = next(column for column in columns if column["name"] == "delta")
        self.assertEqual(str(delta_column["type"]).upper(), "REAL")

    def test_hf_receipt_failure_falls_back_to_editable_rows_in_custom_photo_path(self) -> None:
        app = _app_module()

        rows, trace, raw_text, _model = app._parse_receipt_rows_from_text(
            "Mahalakshmi Marketing\nBingo 4 X 870 = 3480",
            backend_parser=lambda _raw_text: (_ for _ in ()).throw(ValueError("hf malformed json")),
        )

        self.assertEqual(raw_text.count("Bingo"), 1)
        self.assertEqual(rows[0]["matched_product_id"], "bingo_c")
        self.assertTrue(any("Configured backend failed" in line for line in trace))

    def test_modal_ocr_malformed_json_returns_trace_not_crash(self) -> None:
        from dukaan_saathi.integrations.modal_receipt import _extract_receipt_result_with_modal

        class _BadJsonResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                raise ValueError("bad json")

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image:
            image.write(b"not really an image")
            image.flush()
            with patch.dict(os.environ, {"MODAL_RECEIPT_ENDPOINT": "https://example.test/ocr"}):
                with patch("dukaan_saathi.integrations.modal_receipt.requests.post", return_value=_BadJsonResponse()):
                    result = _extract_receipt_result_with_modal(image.name)

        self.assertEqual(result.raw_text, "")
        self.assertIn("Modal endpoint did not return valid JSON.", result.trace_messages)

    def test_modal_speech_malformed_json_returns_trace_not_crash(self) -> None:
        from dukaan_saathi.integrations.speech import transcribe_audio

        class _BadJsonResponse:
            status_code = 200
            text = "not json"

            def json(self):
                raise ValueError("bad json")

        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            audio.write(b"not really audio")
            audio.flush()
            with patch.dict(os.environ, {"MODAL_SPEECH_ENDPOINT": "https://example.test/asr"}):
                with patch("dukaan_saathi.integrations.speech.requests.post", return_value=_BadJsonResponse()):
                    transcript, trace = transcribe_audio(audio.name)

        self.assertEqual(transcript, "")
        self.assertTrue(any("Could not parse ASR response JSON" in line for line in trace))

    def test_modal_ocr_success_returns_raw_text_and_model_name(self) -> None:
        from dukaan_saathi.integrations.modal_receipt import _extract_receipt_result_with_modal

        class _GoodResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"text": "Bingo 4 units\nParle bulk 2 units", "model": "minicpm-v"}

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image:
            image.write(b"not really an image")
            image.flush()
            with patch.dict(os.environ, {"MODAL_RECEIPT_ENDPOINT": "https://example.test/ocr"}):
                with patch("dukaan_saathi.integrations.modal_receipt.requests.post", return_value=_GoodResponse()):
                    result = _extract_receipt_result_with_modal(image.name)

        self.assertIn("Bingo", result.raw_text)
        self.assertEqual(result.model_name, "minicpm-v")
        self.assertFalse(any("error" in m.lower() or "failed" in m.lower() for m in result.trace_messages))

    def test_modal_speech_success_returns_transcript(self) -> None:
        from dukaan_saathi.integrations.speech import transcribe_audio

        class _GoodResponse:
            status_code = 200
            text = '{"text": "add Bun 12", "model": "distil-whisper"}'

            def json(self):
                return {"text": "add Bun 12", "model": "distil-whisper"}

        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            audio.write(b"not really audio")
            audio.flush()
            with patch.dict(os.environ, {"MODAL_SPEECH_ENDPOINT": "https://example.test/asr"}):
                with patch("dukaan_saathi.integrations.speech.requests.post", return_value=_GoodResponse()):
                    transcript, trace = transcribe_audio(audio.name)

        self.assertEqual(transcript, "add Bun 12")
        self.assertTrue(any("add Bun 12" in line for line in trace))
        self.assertTrue(any("distil-whisper" in line for line in trace))


if __name__ == "__main__":
    unittest.main()
