from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dukaan_saathi.traceability import (
    build_file_ref,
    new_run_id,
    utc_now_iso,
    write_manifest,
)


def _load_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON argument must be an object")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--started-at", default="")
    parser.add_argument("--ended-at", default="")
    parser.add_argument("--trace-dir", default=os.getenv("TRACE_DIR", "data/runs"))
    parser.add_argument("--input-file", action="append", default=[])
    parser.add_argument("--output-file", action="append", default=[])
    parser.add_argument("--metadata-json", default="")
    parser.add_argument("--error", default="")

    args = parser.parse_args()
    run_id = args.run_id or new_run_id(args.kind)
    ended_at = args.ended_at or utc_now_iso()

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "kind": args.kind,
        "status": args.status,
        "started_at": args.started_at or ended_at,
        "ended_at": ended_at,
        "inputs": [build_file_ref(path) for path in args.input_file],
        "outputs": [build_file_ref(path) for path in args.output_file],
        "metadata": _load_json(args.metadata_json),
    }
    if args.error:
        manifest["error"] = args.error

    path = write_manifest(manifest, trace_dir=Path(args.trace_dir))
    print(path)


if __name__ == "__main__":
    main()

