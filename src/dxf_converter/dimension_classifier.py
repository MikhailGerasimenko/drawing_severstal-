"""Универсальная классификация размерных токенов для тел вращения."""
from __future__ import annotations

import re
from typing import Any, Optional

INTERNAL_FIT_RE = re.compile(r"H\d+|C\d+", re.IGNORECASE)
EXTERNAL_FIT_RE = re.compile(r"[efgs]\d+", re.IGNORECASE)
DIAMETER_VALUE_RE = re.compile(r"[Ø∅]\s*(\d+(?:[,.]\d+)?)", re.IGNORECASE)
PITCH_ANGLE_RE = re.compile(r"(?:\d+\s*[xх×]\s*)?\d+\s*°", re.IGNORECASE)
LENGTH_TOLERANCE_RE = re.compile(r"^L\s*-?\s*\d", re.IGNORECASE)
LENGTH_MM_RE = re.compile(r"^\d+(?:[,.]\d+)?\s*(?:±|\+|-)", re.IGNORECASE)


def _parse_diameter_mm(normalized: str) -> float:
    match = DIAMETER_VALUE_RE.search(normalized)
    if not match:
        return 0.0
    return float(match.group(1).replace(",", "."))


def _is_diameter_token(token: dict[str, Any]) -> bool:
    return bool(DIAMETER_VALUE_RE.search(token.get("normalized", "")))


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


def apply_generic_dimension_classification(
    features: dict[str, Any],
    tokens: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    """Дополнить external_contour / internal_system / special_elements эвристиками по посадкам."""
    if not tokens:
        return

    available = [token for token in tokens if token["normalized"].lower() not in classified]
    diameters = [token for token in available if _is_diameter_token(token)]

    internal = [token for token in diameters if INTERNAL_FIT_RE.search(token["normalized"])]
    external = [token for token in diameters if EXTERNAL_FIT_RE.search(token["normalized"])]
    plain = [
        token
        for token in diameters
        if token not in internal and token not in external
    ]

    _classify_pitch_hole_groups(features, diameters, classified, text_evidence)
    _classify_external_shafts(features, external, classified)
    _classify_internal_holes(features, internal, classified)
    _classify_plain_diameters(features, plain, classified)
    _classify_lengths(features, available, classified)
    _classify_chamfers_generic(features, available, classified)


def _mark(classified: set[str], *tokens: Optional[dict[str, Any]]) -> None:
    for token in tokens:
        if token:
            classified.add(token["normalized"].lower())


def _classify_pitch_hole_groups(
    features: dict[str, Any],
    diameters: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    hole_tokens = [token for token in diameters if INTERNAL_FIT_RE.search(token["normalized"])]
    pitch_candidates = [
        token
        for token in diameters
        if not INTERNAL_FIT_RE.search(token["normalized"])
        and not EXTERNAL_FIT_RE.search(token["normalized"])
        and _parse_diameter_mm(token["normalized"]) > 0
    ]
    has_angle = any(PITCH_ANGLE_RE.search(item) for item in text_evidence)
    has_qty = any(re.search(r"\b3\b", item) and re.search(r"отв|шт|×", item, re.I) for item in text_evidence)

    if any(item.get("type") == "axial_hole_pattern" for item in features["special_elements"]):
        return
    if not hole_tokens or not pitch_candidates or not (has_angle or has_qty):
        return

    pitch_candidates.sort(key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    pitch = pitch_candidates[0]
    hole = max(hole_tokens, key=lambda item: _parse_diameter_mm(item["normalized"]))
    value: dict[str, Any] = {
        "pitch_diameter": pitch["value"],
        "hole_diameter": hole["value"],
    }
    for item in text_evidence:
        angle = re.search(r"(\d+)\s*[xх×]\s*(\d+)\s*°", item)
        if angle:
            value["angular_spacing"] = f"{angle.group(2)}°"
            break
    if has_qty:
        value["quantity"] = 3

    features["special_elements"].append(
        _fact(
            "axial_hole_pattern",
            value,
            label="Группа осевых отверстий",
            source=pitch["source"],
            confidence="medium",
            note="Классифицировано по сочетанию делительного Ø, отверстий H-посадки и углового шага.",
        )
    )
    _mark(classified, pitch, hole)


def _classify_external_shafts(
    features: dict[str, Any],
    external: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not external:
        return
    ordered = sorted(external, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    main = ordered[0]
    if not features["external_contour"]:
        features["external_contour"].append(
            _fact(
                "outer_diameter",
                main["value"],
                label="Основной наружный диаметр",
                source=main["source"],
                confidence="high",
            )
        )
        features["overall"]["max_diameter"] = main["value"]
        _mark(classified, main)

    for step in ordered[1:3]:
        if step["normalized"].lower() in classified:
            continue
        features["external_contour"].append(
            _fact(
                "external_step_diameter",
                step["value"],
                label="Наружная ступень",
                source=step["source"],
                confidence="medium",
            )
        )
        _mark(classified, step)


def _classify_internal_holes(
    features: dict[str, Any],
    internal: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not internal:
        return
    ordered = sorted(internal, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    main = ordered[0]
    if not any(item.get("type") == "main_axial_hole_candidate" for item in features["internal_system"]):
        features["internal_system"].append(
            _fact(
                "main_axial_hole_candidate",
                main["value"],
                label="Основное осевое отверстие",
                source=main["source"],
                confidence="medium",
            )
        )
        _mark(classified, main)

    for extra in ordered[1:4]:
        if extra["normalized"].lower() in classified:
            continue
        features["internal_system"].append(
            _fact(
                "counterbore_or_stepped_hole",
                extra["value"],
                label="Внутренняя ступень/расточка",
                source=extra["source"],
                confidence="medium",
            )
        )
        _mark(classified, extra)


def _classify_plain_diameters(
    features: dict[str, Any],
    plain: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not plain:
        return
    ordered = sorted(plain, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    if not features["external_contour"] and ordered:
        main = ordered[0]
        features["external_contour"].append(
            _fact(
                "outer_diameter",
                main["value"],
                label="Основной наружный диаметр",
                source=main["source"],
                confidence="medium",
                note="Посадка не указана; определено как наружный Ø по величине.",
            )
        )
        features["overall"]["max_diameter"] = main["value"]
        _mark(classified, main)
        ordered = ordered[1:]

    for token in ordered[:3]:
        if token["normalized"].lower() in classified:
            continue
        if not features["internal_system"]:
            features["internal_system"].append(
                _fact(
                    "main_axial_hole_candidate",
                    token["value"],
                    label="Кандидат на осевое отверстие",
                    source=token["source"],
                    confidence="low",
                    note="Ø без посадки; требует проверки по разрезу.",
                )
            )
            _mark(classified, token)
            break


def _classify_lengths(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
) -> None:
    length_tokens = [
        token
        for token in available
        if LENGTH_TOLERANCE_RE.search(token["normalized"]) or LENGTH_MM_RE.search(token["normalized"])
    ]
    if not length_tokens:
        return
    values = [token["value"] for token in length_tokens[:5]]
    if "display" not in features["overall"] and values:
        features["overall"]["display"] = ", ".join(values)
        if features["external_contour"]:
            features["external_contour"].append(
                _fact(
                    "overall_length",
                    values[0],
                    label="Габаритная длина",
                    source=length_tokens[0]["source"],
                    confidence="medium",
                )
            )
    for token in length_tokens:
        _mark(classified, token)


def _classify_chamfers_generic(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
) -> None:
    chamfers = [
        token
        for token in available
        if re.search(r"^\d+(?:[,.]\d+)?\s*[xх×]\s*\d+\s*°", token["normalized"], re.IGNORECASE)
    ]
    if not chamfers:
        return
    if not any(item.get("type") == "chamfers" for item in features["special_elements"]):
        features["special_elements"].append(
            _fact(
                "chamfers",
                [token["value"] for token in chamfers[:8]],
                label="Фаски",
                source=chamfers[0]["source"],
                confidence="medium",
            )
        )
    _mark(classified, *chamfers)
