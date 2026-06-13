from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


TRACE_DIR = Path(os.getenv("TRACE_DIR", "data/runs"))


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id(prefix: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid4().hex[:8]}"


def file_sha256(path: str | Path) -> str | None:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonl_count(path: str | Path) -> int | None:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    with file_path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def build_file_ref(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    ref: dict[str, Any] = {"path": str(file_path)}
    if file_path.exists() and file_path.is_file():
        ref["sha256"] = file_sha256(file_path)
        ref["bytes"] = file_path.stat().st_size
        if file_path.suffix == ".jsonl":
            ref["records"] = jsonl_count(file_path)
    else:
        ref["exists"] = False
    return ref


def manifest_path(run_id: str, trace_dir: str | Path | None = None) -> Path:
    directory = Path(trace_dir) if trace_dir is not None else TRACE_DIR
    return directory / f"{run_id}.json"


def write_manifest(manifest: dict[str, Any], trace_dir: str | Path | None = None) -> Path:
    run_id = str(manifest.get("run_id") or new_run_id("run"))
    manifest["run_id"] = run_id
    manifest.setdefault("created_at", utc_now_iso())

    path = manifest_path(run_id, trace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

