import json
from pathlib import Path
from typing import Optional

from .dxf_parser import parse_dxf
from .models import NormalizedDrawing
from .raster_ingest import ingest_image, ingest_pdf
from .semantic_schema import normalize_dxf_summary, normalized_from_dict


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def load_normalized_json(path: str) -> NormalizedDrawing:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalized_from_dict(payload, source_path_fallback=path)


def route_input(
    *,
    dxf_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
    image_path: Optional[str] = None,
    json_path: Optional[str] = None,
    preview_path: Optional[str] = None,
    png_dpi: int = 300,
) -> NormalizedDrawing:
    if json_path:
        return load_normalized_json(json_path)
    if dxf_path:
        summary = parse_dxf(dxf_path)
        return normalize_dxf_summary(summary, dxf_path, preview_path=preview_path)
    if pdf_path:
        if not preview_path:
            raise ValueError("preview_path is required for PDF ingest")
        return ingest_pdf(pdf_path, preview_path, dpi=png_dpi)
    if image_path:
        if not preview_path:
            raise ValueError("preview_path is required for image ingest")
        return ingest_image(image_path, preview_path, dpi=png_dpi)
    raise ValueError("No supported input path provided")


def infer_input_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".dxf":
        return "dxf"
    if suffix == ".pdf":
        return "pdf"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"
