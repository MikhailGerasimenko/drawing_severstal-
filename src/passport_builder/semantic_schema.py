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
GDT_RE = re.compile(r"(биени|симметрич|допуск|⌅|∥|⟂|○|◎|\bT\s*0[,.]\d+|\b0[,.]\d+\s*[А-ЯA-Z]\b)", re.IGNORECASE)
DXF_PREFIX_RE = re.compile(r"^(?:\.\d+(?:[,.]\d+)?;)+")
STAMP_NOISE = {
    "изм.", "лист", "листов", "№ докум.", "подп.", "дата", "лит.",
    "разраб.", "пров.", "т.контр.", "н.контр.", "утв.", "зам.",
    "масштаб", "формат", "копировал", "инв. № подл.", "инв. № дубл.",
    "подп. и дата", "взам. инв. №", "справ. №", "перв. примен.",
}


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
    def normalize_text(text: str) -> str:
        value = DXF_PREFIX_RE.sub("", text).strip()
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def is_useful(text: str) -> bool:
        lowered = text.lower().strip()
        if not lowered:
            return False
        if lowered in STAMP_NOISE:
            return False
        if len(lowered) <= 1 and lowered not in {"a", "б", "в", "г", "l", "t"}:
            return False
        return True

    evidence: list[str] = []
    for item in summary.extracted_texts:
        cleaned = normalize_text(item)
        if is_useful(cleaned):
            evidence.append(cleaned)

    features = summary.feature_collection.get("features", [])
    for feature in features:
        props = feature.get("properties", {})
        if props.get("ENTITIES") in {"MTEXT", "TEXT"}:
            preferred = props.get("LaNotePlain") or props.get("LaNote")
            if preferred:
                cleaned = normalize_text(str(preferred))
                if is_useful(cleaned):
                    evidence.append(cleaned)
        if props.get("ENTITIES") == "INSERT":
            for key, value in props.items():
                if key in {"ENTITIES", "LayerName", "Handle", "laCouleur", "Link", "leBloc"}:
                    continue
                if value:
                    pair = normalize_text(f"{key}: {value}")
                    if is_useful(pair):
                        evidence.append(pair)
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
    material_line = ""
    hardness_line = ""
    for text in text_evidence:
        if MATERIAL_RE.search(text):
            if "hrc" in text.lower():
                hardness_line = text
            elif not material_line:
                material_line = text
    if material_line and hardness_line and material_line != hardness_line:
        combined = f"{material_line} / {hardness_line}"
        return SemanticCandidate(value=combined, confidence="high", evidence=[material_line, hardness_line])
    if material_line:
        return SemanticCandidate(value=material_line, confidence="medium", evidence=[material_line])
    if hardness_line:
        return SemanticCandidate(value=hardness_line, confidence="medium", evidence=[hardness_line])
    return SemanticCandidate(value="Не указано в чертеже", confidence="low", evidence=[])


def _pick_units(summary: DxfSummary) -> SemanticCandidate:
    confidence = "high" if summary.units and summary.units != "unitless" else "low"
    value = summary.units if summary.units else "Не указано в чертеже"
    return SemanticCandidate(value=value, confidence=confidence, evidence=[summary.units] if summary.units else [])


def _pick_dimensions(summary: DxfSummary) -> SemanticCandidate:
    valid_dims = [float(d) for d in summary.dimensions if isinstance(d, (int, float)) and float(d) > 0]
    if valid_dims:
        value = ", ".join(str(d) for d in valid_dims[:20])
        return SemanticCandidate(value=value, confidence="medium", evidence=value.split(", ")[:5])

    text_evidence = collect_text_evidence(summary)
    dim_candidates: list[str] = []
    seen: set[str] = set()
    dim_patterns = [
        r"[Ø∅]\s*\d+(?:[,.]\d+)?(?:[A-Za-zА-Яа-я0-9]+)?",
        r"\b\d+(?:[,.]\d+)?\s*[xх×]\s*\d+(?:[,.]\d+)?\b",
        r"\b\d+(?:[,.]\d+)?\s*(?:мм|mm)\b",
        r"\bL-?\s*\d+(?:[,.]\d+)?\b",
    ]
    merged = re.compile("|".join(f"(?:{p})" for p in dim_patterns), re.IGNORECASE)
    for text in text_evidence:
        for match in merged.finditer(text):
            candidate = re.sub(r"\s+", " ", match.group(0)).strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                dim_candidates.append(candidate)
    if dim_candidates:
        value = ", ".join(dim_candidates[:20])
        return SemanticCandidate(value=value, confidence="medium", evidence=dim_candidates[:5])

    # Special fallback for execution tables like: L-0,05 and rows 75 ... 78,5.
    has_l = any(item.strip().lower() == "l" for item in text_evidence)
    l_values: list[float] = []
    for item in text_evidence:
        token = item.strip().replace(",", ".")
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            value = float(token)
            if 10 <= value <= 500:
                l_values.append(value)
    if has_l and l_values:
        min_l = min(l_values)
        max_l = max(l_values)
        value = f"L: {min_l:g}...{max_l:g} мм (по исполнениям)"
        return SemanticCandidate(value=value, confidence="medium", evidence=["L", f"{min_l:g}", f"{max_l:g}"])

    # Avoid substituting drawing sheet bbox as part dimensions.
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
            "raw_entities": summary.raw_entities,
            "raw_virtual_entities": summary.raw_virtual_entities,
            "blocks": summary.blocks,
            "dimension_entities": summary.dimension_entities,
            "hatch_entities": summary.hatch_entities,
            "conversion_coverage": summary.conversion_coverage,
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
        raw_entities=payload.get("raw_entities", []),
        raw_virtual_entities=payload.get("raw_virtual_entities", []),
        blocks=payload.get("blocks", []),
        dimension_entities=payload.get("dimension_entities", []),
        hatch_entities=payload.get("hatch_entities", []),
        conversion_coverage=payload.get("conversion_coverage", {}),
    )
    return normalize_dxf_summary(summary, source_path_fallback or summary.file_name)
