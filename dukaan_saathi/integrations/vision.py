from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias


VisionBackendName: TypeAlias = Literal["modal"]
VisionModelName: TypeAlias = str
VisionTrace: TypeAlias = list[str]
VisionRow: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class VisionRequest:
    image_path: Path


@dataclass(frozen=True)
class VisionExtractionResult:
    backend_name: VisionBackendName
    model_name: VisionModelName
    raw_text: str = ""
    rows: list[VisionRow] = field(default_factory=list)
    latency_seconds: float | None = None
    trace_messages: VisionTrace = field(default_factory=list)


class ReceiptVisionBackend(Protocol):
    backend_name: VisionBackendName

    def extract_receipt(self, request: VisionRequest) -> VisionExtractionResult:
        ...
