from dataclasses import asdict
from pathlib import Path

import fitz
from PIL import Image

from .models import NormalizedDrawing, PreviewArtifact
from .semantic_schema import build_source_manifest


def ingest_pdf(path: str, preview_path: str, dpi: int = 200) -> NormalizedDrawing:
    pdf_path = Path(path)
    out_path = Path(preview_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(out_path)

    preview = PreviewArtifact(path=str(out_path), width=pix.width, height=pix.height, dpi=dpi)
    drawing_facts = {
        "page_count": doc.page_count,
        "image_size": {"width": pix.width, "height": pix.height},
        "entities": {},
        "texts": [],
        "feature_collection": {"type": "FeatureCollection", "name": "RasterInput", "features": []},
    }
    doc.close()

    return NormalizedDrawing(
        source=build_source_manifest(pdf_path, "pdf"),
        preview=preview,
        drawing_facts=drawing_facts,
        ocr_blocks=[],
        vision_blocks=[],
        semantic_candidates={
            "product_name": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "designation": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "units": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "material_hardness": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "overall_dimensions": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "geometry_facts": [],
            "gdt_facts": [],
            "notes_facts": [],
            "missing_fields": ["product_name", "designation", "material_hardness", "overall_dimensions", "gdt"],
            "conflicts": [],
        },
        evidence={},
        legacy_summary={},
    )


def ingest_image(path: str, preview_path: str, dpi: int = 200) -> NormalizedDrawing:
    image_path = Path(path)
    out_path = Path(preview_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:
        converted = image.convert("RGB")
        converted.save(out_path, format="PNG")
        width, height = converted.size

    preview = PreviewArtifact(path=str(out_path), width=width, height=height, dpi=dpi)
    drawing_facts = {
        "page_count": 1,
        "image_size": {"width": width, "height": height},
        "entities": {},
        "texts": [],
        "feature_collection": {"type": "FeatureCollection", "name": "RasterInput", "features": []},
    }
    return NormalizedDrawing(
        source=build_source_manifest(image_path, "image"),
        preview=preview,
        drawing_facts=drawing_facts,
        ocr_blocks=[],
        vision_blocks=[],
        semantic_candidates={
            "product_name": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "designation": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "units": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "material_hardness": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "overall_dimensions": {"value": "Не указано в чертеже", "confidence": "low", "evidence": []},
            "geometry_facts": [],
            "gdt_facts": [],
            "notes_facts": [],
            "missing_fields": ["product_name", "designation", "material_hardness", "overall_dimensions", "gdt"],
            "conflicts": [],
        },
        evidence={},
        legacy_summary={},
    )


def normalized_to_dict(normalized: NormalizedDrawing) -> dict:
    return asdict(normalized)
