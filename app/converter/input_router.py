from pathlib import Path
from typing import Optional

from .dxf_parser import parse_dxf
from .models import NormalizedDrawing
from .semantic_schema import normalize_dxf_summary


def load_dxf(dxf_path: str, *, preview_path: Optional[str] = None) -> NormalizedDrawing:
    path = Path(dxf_path)
    if path.suffix.lower() != ".dxf":
        raise ValueError(f"Ожидается файл .dxf, получено: {path.name}")
    summary = parse_dxf(str(path))
    return normalize_dxf_summary(summary, str(path), preview_path=preview_path)
