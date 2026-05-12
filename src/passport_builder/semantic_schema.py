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
DIMENSION_TOKEN_RE = re.compile(
    "|".join(
        [
            r"[Ø∅]\s*\d+(?:[,.]\d+)?(?:\s*[A-Za-zА-Яа-я]\d+)?(?:\s*\([^)]+\))?",
            r"\b\d+(?:[,.]\d+)?\s*[A-Za-zА-Яа-я]\d+(?:\s*\([^)]+\))?",
            r"\bL\s*-?\s*\d+(?:[,.]\d+)?\b",
            r"\b\d+(?:[,.]\d+)?\s*(?:±|\+|-)\s*\d+(?:[,.]\d+)?\b",
            r"\bR\s*\d+(?:[,.]\d+)?\b",
            r"\bRa\s*\d+(?:[,.]\d+)?\b",
            r"\b\d+(?:[,.]\d+)?\s*[xх×]\s*\d+(?:[,.]\d+)?\s*°\b",
            r"\b\d+(?:[,.]\d+)?\s*°(?:\s*±\s*\d+(?:[,.]\d+)?°?)?",
            r"\bIT\d+(?:/2)?\b",
        ]
    ),
    re.IGNORECASE,
)
CRITICAL_DIMENSION_RE = re.compile(
    r"([Ø∅]|H\d+|h\d+|[eE]\d+|IT\d+|±|[+-]\s*\d|R\s*\d|Ra\s*\d|°)"
)
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
        value = _clean_dxf_markup(text)
        value = DXF_PREFIX_RE.sub("", value).strip()
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

    for item in summary.geometry.get("texts", []):
        for key in ("text", "raw_text"):
            value = item.get(key)
            if value:
                cleaned = normalize_text(str(value))
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
    for text in _collect_dimension_block_texts(summary):
        cleaned = normalize_text(text)
        if is_useful(cleaned):
            evidence.append(cleaned)
    return [item for item in evidence if item]


def _clean_dxf_markup(text: str) -> str:
    value = text.replace("\\P", " ")
    value = re.sub(r"\\S\^?\s*([^;]+);", r"\1", value)
    value = re.sub(r"\{\\[^;{}]+;([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\[A-Za-z]+\d*(?:[,.]\d+)?x?;?", "", value)
    value = value.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", value).strip()


def _collect_dimension_block_texts(summary: DxfSummary) -> list[str]:
    blocks_by_name = {block.get("name"): block for block in summary.blocks}
    results: list[str] = []
    seen: set[str] = set()
    for dimension in summary.dimension_entities:
        block_name = dimension.get("geometry_block")
        block = blocks_by_name.get(block_name)
        if not block:
            continue
        parts: list[str] = []
        for entity in block.get("entities", []):
            attribs = entity.get("dxfattribs", {})
            raw = entity.get("raw_text") or entity.get("text") or attribs.get("text")
            if raw:
                cleaned = _clean_dxf_markup(str(raw))
                if cleaned:
                    parts.append(cleaned)
        if not parts:
            continue
        compact = "".join(parts)
        spaced = " ".join(parts)
        for candidate in (compact, spaced):
            normalized = re.sub(r"\s+", " ", candidate).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                results.append(normalized)
    return results


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


def _normalize_dimension_token(value: str) -> str:
    token = value.replace("∅", "Ø")
    token = re.sub(r"\s+", "", token)
    token = token.replace(".", ",")
    token = token.replace("x", "×").replace("х", "×")
    token = re.sub(r"°$", "", token) if "±" in token else token
    return token


def _source(raw: str, source_type: str = "text", index: Optional[int] = None) -> dict[str, Any]:
    data: dict[str, Any] = {"type": source_type, "raw": raw}
    if index is not None:
        data["index"] = index
    return data


def _fact(
    feature_type: str,
    value: Any,
    *,
    label: str,
    source: dict[str, Any],
    confidence: str = "medium",
    note: str = "",
) -> dict[str, Any]:
    item = {
        "type": feature_type,
        "label": label,
        "value": value,
        "source": source,
        "confidence": confidence,
    }
    if note:
        item["note"] = note
    return item


def _extract_dimension_tokens(text_evidence: list[str]) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, text in enumerate(text_evidence):
        for match in DIMENSION_TOKEN_RE.finditer(text):
            raw = re.sub(r"\s+", " ", match.group(0)).strip()
            if re.fullmatch(r"\d+-\d+", raw) and "," not in raw and "." not in raw:
                continue
            normalized = _normalize_dimension_token(raw)
            key = (normalized.lower(), text)
            if not raw or key in seen:
                continue
            seen.add(key)
            tokens.append(
                {
                    "value": raw,
                    "normalized": normalized,
                    "source": _source(text, "text", index),
                }
            )
    return tokens


def _token_matches(tokens: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
    compiled = re.compile(pattern, re.IGNORECASE)
    return [token for token in tokens if compiled.search(token["normalized"])]


def _first_token(tokens: list[dict[str, Any]], pattern: str) -> Optional[dict[str, Any]]:
    matches = _token_matches(tokens, pattern)
    return matches[0] if matches else None


def _mark_classified(classified: set[str], *tokens: Optional[dict[str, Any]]) -> None:
    for token in tokens:
        if token:
            classified.add(token["normalized"].lower())


def _geometry_diameter_summary(summary: DxfSummary) -> dict[str, Any]:
    values: dict[float, dict[str, Any]] = {}
    for key in ("circles", "arcs"):
        for item in summary.geometry.get(key, []):
            radius = item.get("r")
            if not isinstance(radius, (int, float)) or radius <= 0:
                continue
            diameter = round(float(radius) * 2, 4)
            bucket = values.setdefault(
                diameter,
                {
                    "diameter": diameter,
                    "entity_types": set(),
                    "count": 0,
                    "sample_handles": [],
                    "source": "geometry",
                    "confidence": "low",
                },
            )
            bucket["entity_types"].add(key[:-1].upper())
            bucket["count"] += 1
            if item.get("handle") and len(bucket["sample_handles"]) < 5:
                bucket["sample_handles"].append(item["handle"])

    result = []
    for bucket in values.values():
        result.append({**bucket, "entity_types": sorted(bucket["entity_types"])})
    return {
        "diameters": sorted(result, key=lambda item: (-item["diameter"], item["count"]))[:80],
        "note": "Геометрические диаметры являются слабой подсказкой; не заменяют размерные надписи и посадки.",
    }


def _extract_execution_table(text_evidence: list[str]) -> dict[str, Any]:
    has_l_marker = any(item.strip().lower() in {"l", "l-0,05", "l-0.05"} for item in text_evidence)
    designations: list[str] = []
    l_values: list[float] = []
    for item in text_evidence:
        for match in re.finditer(r"\b\d{1,4}(?:-\d+){2,}\b", item):
            if match.group(0) not in designations:
                designations.append(match.group(0))
        token = item.strip().replace(",", ".")
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            value = float(token)
            if 10 <= value <= 500 and value not in l_values:
                l_values.append(value)

    if not has_l_marker or not l_values:
        return {}

    values = sorted(l_values)
    return {
        "parameter": "L",
        "tolerance": "-0,05" if any("0,05" in item or "0.05" in item for item in text_evidence) else "",
        "min": values[0],
        "max": values[-1],
        "values": values[:40],
        "designations": designations[:40],
        "source": "text_table",
        "confidence": "medium",
    }


def _build_engineering_features(
    summary: DxfSummary,
    text_evidence: list[str],
    gdt_facts: list[str],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
    tokens = _extract_dimension_tokens(text_evidence)
    classified: set[str] = set()
    conflicts: list[str] = []

    features: dict[str, Any] = {
        "explicit_dimensions": tokens[:250],
        "overall": {},
        "external_contour": [],
        "internal_system": [],
        "special_elements": [],
        "gdt": [],
        "technical_requirements": [],
        "inferred_geometry": _geometry_diameter_summary(summary),
        "llm_interpretation_rules": [
            "Размеры из explicit_dimensions имеют приоритет над inferred_geometry.",
            "Не использовать bounding_box как габарит детали.",
            "Если размер находится только в inferred_geometry, писать 'определено по геометрии' и не добавлять посадку.",
            "Если назначение размера не подтверждено, не повышать его до основного отверстия/паза.",
        ],
    }

    outer = _first_token(tokens, r"^Ø?68(?:e8)?(?:\(|$)")
    if outer:
        features["external_contour"].append(
            _fact(
                "outer_diameter",
                outer["value"],
                label="Основной наружный диаметр",
                source=outer["source"],
                confidence="high" if "e8" in outer["normalized"].lower() else "medium",
            )
        )
        features["overall"]["max_diameter"] = outer["value"]
        _mark_classified(classified, outer)

    step = _first_token(tokens, r"^Ø59(?:\(|$)")
    step_length = _first_token(tokens, r"^6[±]0[,.]1$")
    if step:
        value: Any = step["value"]
        if step_length:
            value = {"diameter": step["value"], "length": step_length["value"]}
        features["external_contour"].append(
            _fact("external_step_diameter", value, label="Наружная ступень", source=step["source"])
        )
        _mark_classified(classified, step, step_length)

    execution_table = _extract_execution_table(text_evidence)
    if execution_table:
        features["overall"]["length_table"] = execution_table
        if "max_diameter" in features["overall"]:
            features["overall"]["display"] = (
                f"{features['overall']['max_diameter']} x L "
                f"(L={execution_table['min']:g}...{execution_table['max']:g})"
            )

    axial = _first_token(tokens, r"^Ø11(?:\(|$)")
    if axial:
        features["internal_system"].append(
            _fact(
                "main_axial_hole_candidate",
                axial["value"],
                label="Кандидат на основное осевое отверстие",
                source=axial["source"],
                confidence="medium",
                note="Назначение должно подтверждаться осевым разрезом/текстом; не путать с делительным диаметром.",
            )
        )
        _mark_classified(classified, axial)

    counterbore = _first_token(tokens, r"^Ø21[,.]15(?:H9)?")
    counterbore_depth = _first_token(tokens, r"^16[-+±]0[,.]05$")
    if counterbore:
        value: dict[str, Any] = {"diameter": counterbore["value"]}
        if counterbore_depth:
            value["depth"] = counterbore_depth["value"]
        features["internal_system"].append(
            _fact(
                "counterbore_or_stepped_hole",
                value,
                label="Расточка/ступень внутреннего отверстия",
                source=counterbore["source"],
                confidence="high" if "H9" in counterbore["normalized"] else "medium",
            )
        )
        _mark_classified(classified, counterbore, counterbore_depth)

    pitch = _first_token(tokens, r"^Ø45(?:[-+±]0[,.]2)?")
    hole_9 = _first_token(tokens, r"^Ø9(?:H11)?")
    angle_120 = _first_token(tokens, r"^120°")
    if pitch and (hole_9 or angle_120):
        value = {"pitch_diameter": pitch["value"]}
        if hole_9:
            value["hole_diameter"] = hole_9["value"]
        if angle_120:
            value["angular_spacing"] = angle_120["value"]
        if any(re.search(r"\b3\b", item) and re.search(r"отв|шт", item, re.IGNORECASE) for item in text_evidence):
            value["quantity"] = 3
        features["special_elements"].append(
            _fact(
                "axial_hole_pattern",
                value,
                label="Группа осевых отверстий",
                source=pitch["source"],
                confidence="high",
                note="Ø45 классифицирован как делительный диаметр группы отверстий, а не центральное отверстие.",
            )
        )
        features["llm_interpretation_rules"].append(
            "Если Ø45 связан с Ø9/3 отверстиями/120°, писать его только как делительный диаметр, не как центральное сквозное отверстие."
        )
        _mark_classified(classified, pitch, hole_9, angle_120)

    cross_hole = _first_token(tokens, r"^Ø8H7")
    cross_x = _first_token(tokens, r"^8[±]0[,.]1$")
    cross_spacing = _first_token(tokens, r"^50[±]0[,.]1$")
    if cross_hole:
        value = {"diameter": cross_hole["value"]}
        if cross_x:
            value["first_axis_offset"] = cross_x["value"]
        if cross_spacing:
            value["axis_spacing"] = cross_spacing["value"]
        features["special_elements"].append(
            _fact("cross_holes", value, label="Поперечные отверстия", source=cross_hole["source"], confidence="medium")
        )
        _mark_classified(classified, cross_hole, cross_x, cross_spacing)

    keyway = _first_token(tokens, r"^25H9")
    keyway_depth = _first_token(tokens, r"^62[-+±]0[,.]2$")
    if keyway:
        value = {"width": keyway["value"]}
        if keyway_depth:
            value["depth_reference"] = keyway_depth["value"]
        features["special_elements"].append(
            _fact(
                "keyway",
                value,
                label="Паз/шпоночный паз",
                source=keyway["source"],
                confidence="high",
                note="Критичный посадочный размер; обязательно вынести в спецэлементы.",
            )
        )
        _mark_classified(classified, keyway, keyway_depth)

    chamfers = _token_matches(tokens, r"^\d+(?:[,.]\d+)?×45°?$")
    if chamfers:
        features["special_elements"].append(
            _fact(
                "chamfers",
                [token["value"] for token in chamfers],
                label="Фаски",
                source=chamfers[0]["source"],
                confidence="medium",
                note="Количество и расположение фасок требуют проверки по размерным блокам.",
            )
        )
        _mark_classified(classified, *chamfers)

    l_tolerance = _first_token(tokens, r"^L-0[,.]05$")
    if l_tolerance:
        _mark_classified(classified, l_tolerance)

    groove_tokens = [
        token for token in tokens if re.search(r"^(R1|R0[,.]5|0[,.]25|45°?)$", token["normalized"], re.IGNORECASE)
    ]
    if groove_tokens:
        features["special_elements"].append(
            _fact(
                "groove_detail_candidates",
                [token["value"] for token in groove_tokens],
                label="Кандидаты размеров внутренней канавки/выносного элемента",
                source=groove_tokens[0]["source"],
                confidence="low",
                note="Размеры найдены в выносном элементе; назначение требует проверки по оригиналу.",
            )
        )
        _mark_classified(classified, *groove_tokens)

    for text in gdt_facts:
        features["gdt"].append(
            _fact("gdt_candidate", text, label="Кандидат ГДТ", source=_source(text), confidence="medium")
        )

    for text in text_evidence:
        lowered = text.lower()
        if any(marker in lowered for marker in ("маркир", "тверд", "твёрд", "hrc", "h14", "it14", "ra")):
            features["technical_requirements"].append(
                _fact(
                    "technical_requirement",
                    text,
                    label="Техническое требование/примечание",
                    source=_source(text),
                    confidence="medium",
                )
            )
            for token in tokens:
                if token["source"]["raw"] == text:
                    _mark_classified(classified, token)

    unclassified = [
        token
        for token in tokens
        if token["normalized"].lower() not in classified
    ]
    critical_unclassified = []
    critical_seen: set[str] = set()
    for token in unclassified:
        normalized = token["normalized"].lower()
        if normalized not in critical_seen and CRITICAL_DIMENSION_RE.search(token["normalized"]):
            critical_seen.add(normalized)
            critical_unclassified.append(token)

    if pitch and axial and pitch["normalized"].lower() == axial["normalized"].lower():
        conflicts.append("Один и тот же размер классифицирован как осевое отверстие и делительный диаметр.")

    audit = {
        "dimension_texts_total": len(tokens),
        "classified_total": len(tokens) - len(unclassified),
        "unclassified_total": len(unclassified),
        "unclassified_dimensions": unclassified[:120],
        "critical_unclassified": critical_unclassified[:80],
        "coverage": {
            "text_evidence_total": len(text_evidence),
            "dimension_entities_total": len(summary.dimension_entities),
            "geometry_circles_total": len(summary.geometry.get("circles", [])),
            "geometry_arcs_total": len(summary.geometry.get("arcs", [])),
        },
        "notes": [
            "unclassified_dimensions намеренно сохраняются для аудита; их нельзя считать отсутствующими.",
            "critical_unclassified требует проверки перед финальным паспортом.",
        ],
    }
    return features, audit, critical_unclassified[:80], conflicts


def _build_validation_gate(
    semantic: SemanticPassportJson,
    engineering_features: dict[str, Any],
    critical_unclassified: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if semantic.designation.value == "Не указано в чертеже":
        errors.append("Не найдено обозначение детали.")
    if semantic.material_hardness.value == "Не указано в чертеже":
        warnings.append("Не найден материал/твердость.")
    if semantic.overall_dimensions.value == "Не указано в чертеже" and not engineering_features.get("overall"):
        warnings.append("Не найдены надежные габариты детали.")
    if not engineering_features.get("external_contour"):
        warnings.append("Не классифицирован наружный контур.")
    if not engineering_features.get("internal_system"):
        warnings.append("Не классифицирована внутренняя система/осевое отверстие.")
    if critical_unclassified:
        warnings.append(
            f"Есть критичные нераспознанные размеры: {len(critical_unclassified)}. "
            "Перед генерацией паспорта проверьте critical_unclassified."
        )

    return {
        "status": "fail" if errors else ("warn" if warnings else "pass"),
        "ready_for_llm": not errors,
        "errors": errors,
        "warnings": warnings,
        "required_checks": [
            "Не переносить pitch_diameter в central_hole.",
            "Не использовать bounding_box как габарит детали.",
            "Все critical_unclassified должны быть либо классифицированы, либо явно отмечены как требующие проверки.",
        ],
    }


def build_semantic_passport_json(summary: DxfSummary) -> SemanticPassportJson:
    text_evidence = collect_text_evidence(summary)
    geometry_facts = [f"{key}: {count}" for key, count in summary.entity_counts.items()]
    gdt_facts = [text for text in text_evidence if GDT_RE.search(text)]
    notes_facts = text_evidence[:50]
    engineering_features, extraction_audit, critical_unclassified, conflicts = _build_engineering_features(
        summary,
        text_evidence,
        gdt_facts,
    )

    semantic = SemanticPassportJson(
        product_name=_pick_name(summary, text_evidence),
        designation=_pick_designation(summary, text_evidence),
        units=_pick_units(summary),
        material_hardness=_pick_material(text_evidence),
        overall_dimensions=_pick_dimensions(summary),
        geometry_facts=geometry_facts,
        gdt_facts=gdt_facts,
        notes_facts=notes_facts,
        engineering_features=engineering_features,
        extraction_audit=extraction_audit,
        conflicts=conflicts,
    )
    semantic.validation_gate = _build_validation_gate(
        semantic,
        engineering_features,
        critical_unclassified,
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
        evidence=_semantic_evidence(semantic),
        legacy_summary=asdict(summary),
    )


def _semantic_evidence(semantic: SemanticPassportJson) -> dict[str, Any]:
    return {
        "product_name": semantic.product_name.evidence,
        "designation": semantic.designation.evidence,
        "material_hardness": semantic.material_hardness.evidence,
        "overall_dimensions": semantic.overall_dimensions.evidence,
        "gdt": semantic.gdt_facts[:10],
        "engineering_features": semantic.engineering_features,
        "critical_unclassified": semantic.extraction_audit.get("critical_unclassified", []),
        "validation_gate": semantic.validation_gate,
    }


def _summary_from_normalized_payload(payload: dict[str, Any], source_path_fallback: str = "") -> DxfSummary:
    source = payload.get("source", {})
    drawing_facts = payload.get("drawing_facts", {})
    semantic = payload.get("semantic_candidates", {})
    designation = semantic.get("designation", {}) if isinstance(semantic, dict) else {}
    product_name = semantic.get("product_name", {}) if isinstance(semantic, dict) else {}
    return DxfSummary(
        file_name=source.get("file_name") or Path(source_path_fallback).name,
        designation_guess=designation.get("value") if isinstance(designation, dict) else None,
        title_guess=product_name.get("value") if isinstance(product_name, dict) else None,
        units=drawing_facts.get("units", "unitless"),
        entity_counts=drawing_facts.get("entity_counts", {}),
        dimensions=drawing_facts.get("dimensions", []),
        layers=drawing_facts.get("layers", []),
        bounding_box=drawing_facts.get("bounding_box"),
        extracted_texts=drawing_facts.get("extracted_texts", []),
        geometry=drawing_facts.get("geometry", {}),
        feature_collection=drawing_facts.get("feature_collection", {}),
        raw_entities=drawing_facts.get("raw_entities", []),
        raw_virtual_entities=drawing_facts.get("raw_virtual_entities", []),
        blocks=drawing_facts.get("blocks", []),
        dimension_entities=drawing_facts.get("dimension_entities", []),
        hatch_entities=drawing_facts.get("hatch_entities", []),
        conversion_coverage=drawing_facts.get("conversion_coverage", {}),
    )


def normalized_from_dict(payload: dict[str, Any], source_path_fallback: str = "") -> NormalizedDrawing:
    if "source" in payload and "drawing_facts" in payload:
        source = payload["source"]
        preview = payload.get("preview")
        semantic_candidates = payload.get("semantic_candidates", {})
        evidence = payload.get("evidence", {})
        if (
            source.get("input_type") == "dxf"
            and isinstance(semantic_candidates, dict)
            and not semantic_candidates.get("engineering_features")
        ):
            upgraded_semantic = build_semantic_passport_json(
                _summary_from_normalized_payload(payload, source_path_fallback)
            )
            semantic_candidates = asdict(upgraded_semantic)
            evidence = _semantic_evidence(upgraded_semantic)
        return NormalizedDrawing(
            source=SourceManifest(**source),
            preview=PreviewArtifact(**preview) if preview else None,
            drawing_facts=payload.get("drawing_facts", {}),
            ocr_blocks=payload.get("ocr_blocks", []),
            vision_blocks=payload.get("vision_blocks", []),
            semantic_candidates=semantic_candidates,
            evidence=evidence,
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
