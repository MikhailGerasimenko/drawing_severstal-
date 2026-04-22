import hashlib
import mimetypes
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Union

from .models import (
    DxfSummary,
    NormalizedDrawing,
    PreviewArtifact,
    SemanticCandidate,
    SemanticPassportJson,
    SourceManifest,
)


DESIGNATION_RE = re.compile(r"\b\d{1,4}(?:-\d+){0,4}\b")
MATERIAL_RE = re.compile(r"(сталь|бронза|латунь|алюминий|чугун|hrc|гост)", re.IGNORECASE)
GDT_RE = re.compile(r"(биени|симметрич|допуск|⌅|∥|⟂|○|◎)", re.IGNORECASE)


def _sha256(path: Union[str, Path]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_manifest(path: Union[str, Path], input_type: str) -> SourceManifest:
    file_path = Path(path)
    mime_type, _ = mimetypes.guess_type(file_path.name)
    return SourceManifest(
        input_type=input_type,
        file_name=file_path.name,
        original_path=str(file_path),
        mime_type=mime_type or "application/octet-stream",
        size_bytes=file_path.stat().st_size,
        checksum_sha256=_sha256(file_path),
    )


def collect_text_evidence(summary: DxfSummary) -> list[str]:
    evidence: list[str] = []
    evidence.extend(summary.extracted_texts)

    features = summary.feature_collection.get("features", [])
    for feature in features:
        props = feature.get("properties", {})
        if props.get("ENTITIES") == "MTEXT" and props.get("LaNote"):
            evidence.append(str(props["LaNote"]))
        if props.get("ENTITIES") == "INSERT":
            for key, value in props.items():
                if key in {"ENTITIES", "LayerName", "Handle", "laCouleur", "Link", "leBloc"}:
                    continue
                if value:
                    evidence.append(f"{key}: {value}")
    return [item for item in evidence if item]


def _pick_name(summary: DxfSummary, text_evidence: list[str]) -> SemanticCandidate:
    value = summary.title_guess or (text_evidence[0] if text_evidence else "Не указано в чертеже")
    confidence = "high" if summary.title_guess else ("medium" if text_evidence else "low")
    evidence = [summary.title_guess] if summary.title_guess else text_evidence[:3]
    return SemanticCandidate(value=value, confidence=confidence, evidence=evidence)


def _pick_designation(summary: DxfSummary, text_evidence: list[str]) -> SemanticCandidate:
    if summary.designation_guess:
        return SemanticCandidate(
            value=summary.designation_guess,
            confidence="high",
            evidence=[summary.designation_guess],
        )
    for text in text_evidence:
        match = DESIGNATION_RE.search(text)
        if match:
            return SemanticCandidate(value=match.group(0), confidence="medium", evidence=[text])
    return SemanticCandidate(value="Не указано в чертеже", confidence="low", evidence=[])


def _pick_material(text_evidence: list[str]) -> SemanticCandidate:
    for text in text_evidence:
        if MATERIAL_RE.search(text):
            return SemanticCandidate(value=text, confidence="medium", evidence=[text])
    return SemanticCandidate(value="Не указано в чертеже", confidence="low", evidence=[])


def _pick_units(summary: DxfSummary) -> SemanticCandidate:
    confidence = "high" if summary.units and summary.units != "unitless" else "low"
    value = summary.units if summary.units else "Не указано в чертеже"
    return SemanticCandidate(value=value, confidence=confidence, evidence=[summary.units] if summary.units else [])


def _pick_dimensions(summary: DxfSummary) -> SemanticCandidate:
    if summary.dimensions:
        value = ", ".join(str(d) for d in summary.dimensions[:20])
        return SemanticCandidate(value=value, confidence="medium", evidence=value.split(", ")[:5])
    if summary.bounding_box:
        bbox = summary.bounding_box
        value = f"width={bbox['width']}, height={bbox['height']}"
        return SemanticCandidate(value=value, confidence="low", evidence=["bounding_box"])
    return SemanticCandidate(value="Не указано в чертеже", confidence="low", evidence=[])


def build_semantic_passport_json(summary: DxfSummary) -> SemanticPassportJson:
    text_evidence = collect_text_evidence(summary)
    geometry_facts = [f"{key}: {count}" for key, count in summary.entity_counts.items()]
    gdt_facts = [text for text in text_evidence if GDT_RE.search(text)]
    notes_facts = text_evidence[:50]

    semantic = SemanticPassportJson(
        product_name=_pick_name(summary, text_evidence),
        designation=_pick_designation(summary, text_evidence),
        units=_pick_units(summary),
        material_hardness=_pick_material(text_evidence),
        overall_dimensions=_pick_dimensions(summary),
        geometry_facts=geometry_facts,
        gdt_facts=gdt_facts,
        notes_facts=notes_facts,
    )

    if semantic.product_name.value == "Не указано в чертеже":
        semantic.missing_fields.append("product_name")
    if semantic.designation.value == "Не указано в чертеже":
        semantic.missing_fields.append("designation")
    if semantic.material_hardness.value == "Не указано в чертеже":
        semantic.missing_fields.append("material_hardness")
    if semantic.overall_dimensions.value == "Не указано в чертеже":
        semantic.missing_fields.append("overall_dimensions")
    if not semantic.gdt_facts:
        semantic.missing_fields.append("gdt")

    return semantic


def normalize_dxf_summary(
    summary: DxfSummary,
    source_path: Union[str, Path],
    preview_path: Optional[str] = None,
    preview_width: Optional[int] = None,
    preview_height: Optional[int] = None,
) -> NormalizedDrawing:
    semantic = build_semantic_passport_json(summary)
    preview = None
    if preview_path:
        preview = PreviewArtifact(
            path=str(preview_path),
            width=preview_width,
            height=preview_height,
            dpi=None,
        )

    return NormalizedDrawing(
        source=build_source_manifest(source_path, "dxf"),
        preview=preview,
        drawing_facts={
            "units": summary.units,
            "entity_counts": summary.entity_counts,
            "layers": summary.layers,
            "dimensions": summary.dimensions,
            "bounding_box": summary.bounding_box,
            "extracted_texts": summary.extracted_texts,
            "geometry": summary.geometry,
            "feature_collection": summary.feature_collection,
        },
        ocr_blocks=[],
        vision_blocks=[],
        semantic_candidates=asdict(semantic),
        evidence={
            "product_name": semantic.product_name.evidence,
            "designation": semantic.designation.evidence,
            "material_hardness": semantic.material_hardness.evidence,
            "overall_dimensions": semantic.overall_dimensions.evidence,
            "gdt": semantic.gdt_facts[:10],
        },
        legacy_summary=asdict(summary),
    )


def normalized_from_dict(payload: dict[str, Any], source_path_fallback: str = "") -> NormalizedDrawing:
    if "source" in payload and "drawing_facts" in payload:
        source = payload["source"]
        preview = payload.get("preview")
        return NormalizedDrawing(
            source=SourceManifest(**source),
            preview=PreviewArtifact(**preview) if preview else None,
            drawing_facts=payload.get("drawing_facts", {}),
            ocr_blocks=payload.get("ocr_blocks", []),
            vision_blocks=payload.get("vision_blocks", []),
            semantic_candidates=payload.get("semantic_candidates", {}),
            evidence=payload.get("evidence", {}),
            legacy_summary=payload.get("legacy_summary", {}),
        )

    summary = DxfSummary(
        file_name=payload.get("file_name", Path(source_path_fallback).name),
        designation_guess=payload.get("designation_guess"),
        title_guess=payload.get("title_guess"),
        units=payload.get("units", "unitless"),
        entity_counts=payload.get("entity_counts", {}),
        dimensions=payload.get("dimensions", []),
        layers=payload.get("layers", []),
        bounding_box=payload.get("bounding_box"),
        extracted_texts=payload.get("extracted_texts", []),
        geometry=payload.get("geometry", {}),
        feature_collection=payload.get("feature_collection", {}),
    )
    return normalize_dxf_summary(summary, source_path_fallback or summary.file_name)
