from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dxf_converter.input_router import load_dxf


@dataclass
class ConverterResult:
    llm_context: str
    designation: str
    part_type: str
    gate_status: str
    gate_warnings: list[str]
    gate_errors: list[str]
    file_name_used: str


def run_converter(dxf_path: Path, *, simulate_drawing_upload: bool = False) -> ConverterResult:
    target = dxf_path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    if simulate_drawing_upload:
        temp_dir = tempfile.TemporaryDirectory()
        target = Path(temp_dir.name) / "drawing.dxf"
        shutil.copy(dxf_path, target)

    try:
        normalized = load_dxf(target)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    semantic = normalized.semantic_candidates or {}
    features = semantic.get("engineering_features", {}) if isinstance(semantic, dict) else {}
    gate = semantic.get("validation_gate", {}) if isinstance(semantic, dict) else {}

    designation = _candidate(semantic, "designation")
    part_type = ""
    if isinstance(features, dict):
        part = features.get("part_type", {})
        if isinstance(part, dict):
            part_type = str(part.get("value") or "")
    if not part_type:
        part_type = _candidate(semantic, "product_name")

    from dxf_converter.markdown_context import render_llm_markdown_context

    return ConverterResult(
        llm_context=render_llm_markdown_context(normalized),
        designation=designation,
        part_type=part_type,
        gate_status=str(gate.get("status") or "unknown"),
        gate_warnings=list(gate.get("warnings") or []),
        gate_errors=list(gate.get("errors") or []),
        file_name_used=target.name,
    )


def _candidate(semantic: dict, key: str) -> str:
    raw = semantic.get(key, {})
    if isinstance(raw, dict):
        return str(raw.get("value") or "")
    return str(raw or "")
