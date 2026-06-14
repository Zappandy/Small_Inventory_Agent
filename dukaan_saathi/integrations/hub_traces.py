"""
Push agent traces to a public HF dataset repo for the "Sharing is Caring"
hackathon badge.

Runs in a daemon thread — never blocks the approval flow.
No-op when HF_TOKEN is unset.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone


DATASET_REPO = "Zappandy/kirana-ai-agent-traces"


def push_trace(
    *,
    input_type: str,
    raw_command: str,
    trace: list[str],
    action: str,
    product: str,
    quantity: float | None,
) -> None:
    """Fire-and-forget: push one trace entry to the Hub dataset."""
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        return

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_type": input_type,
        "raw_command": raw_command,
        "trace": trace,
        "action": action,
        "product": product,
        "quantity": quantity,
    }
    threading.Thread(target=_upload, args=(payload, token), daemon=True).start()


def _upload(payload: dict, token: str) -> None:
    try:
        from huggingface_hub import HfApi

        api = HfApi(token=token)

        # Create repo on first use; no-op if it already exists.
        api.create_repo(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            exist_ok=True,
            private=False,
        )

        ts = payload["timestamp"].replace(":", "-").replace(".", "-")
        path_in_repo = f"traces/{ts}.json"

        api.upload_file(
            path_or_fileobj=json.dumps(payload, ensure_ascii=False, indent=2).encode(),
            path_in_repo=path_in_repo,
            repo_id=DATASET_REPO,
            repo_type="dataset",
            commit_message=f"trace: {payload['input_type']} / {payload['action']}",
        )
    except Exception:
        pass  # traces are best-effort; never break the approval flow
