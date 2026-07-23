"""Сборка габаритов и фильтрация критичных нераспознанных размеров."""
from __future__ import annotations

import re
from typing import Any

from .dimension_classifier import DIAMETER_VALUE_RE, LENGTH_MM_RE, LENGTH_TOLERANCE_RE

CRITICAL_DIMENSION_RE = re.compile(
    r"([Ø∅]|H\d+|h\d+|[a-z]{1,2}\d+|IT\d+|±|[+-]\s*\d|R\s*\d|Ra\s*\d|°)"
)
DIMENSION_LABEL_RE = re.compile(r"^[lL]\d+$")
THREAD_RE = re.compile(r"^M\d+(?:[,.]\d+)?(?:-\d+[A-Za-z])?", re.IGNORECASE)


def _parse_diameter_mm(normalized: str) -> float:
    match = DIAMETER_VALUE_RE.search(normalized)
    if not match:
        return 0.0
    return float(match.group(1).replace(",", "."))


def _parse_length_mm(normalized: str) -> float | None:
    token = normalized.replace(" ", "")
    match = re.match(r"^[LH]-?(\d+(?:,\d+)?)", token, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", "."))
    match = re.match(r"^(\d+(?:,\d+)?)(?:±|\+|-)", token)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _is_dimension_label(normalized: str) -> bool:
    return bool(DIMENSION_LABEL_RE.match(normalized))


def _is_length_token(normalized: str) -> bool:
    if _is_dimension_label(normalized):
        return False
    if LENGTH_TOLERANCE_RE.search(normalized):
        return True
    return bool(LENGTH_MM_RE.search(normalized))


def pick_main_length(tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        token
        for token in tokens
        if _is_length_token(token.get("normalized", ""))
        and _parse_length_mm(token.get("normalized", "")) is not None
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: _parse_length_mm(item.get("normalized", "")) or 0.0,
    )


def finalize_overall_display(features: dict[str, Any], tokens: list[dict[str, Any]]) -> None:
    """Собрать человекочитаемые габариты из классифицированных фактов."""
    overall = features.setdefault("overall", {})
    max_diameter = overall.get("max_diameter")
    if not max_diameter:
        for fact in features.get("external_contour", []):
            if fact.get("type") in {"outer_diameter", "external_step_diameter"}:
                value = fact.get("value")
                if isinstance(value, dict):
                    value = value.get("diameter")
                if value:
                    max_diameter = value
                    overall["max_diameter"] = value
                    break

    main_length = overall.get("main_length")
    if not main_length:
        length_token = pick_main_length(tokens)
        if length_token:
            main_length = length_token["value"]
            overall["main_length"] = main_length
    # H14 и подобные посадки/допуски не должны становиться габаритом.
    if main_length and re.fullmatch(r"[HhНн]\d{2}", str(main_length).replace(" ", "")):
        main_length = None
        overall.pop("main_length", None)

    length_table = overall.get("length_table")
    diameter_table = overall.get("diameter_table")
    parts: list[str] = []
    length_param = (length_table or {}).get("parameter") or "L"

    # Таблица исполнений приоритетнее, если явной габаритной длины нет или она короче диапазона.
    prefer_table = bool(length_table) and (
        not main_length
        or (
            isinstance(length_table.get("max"), (int, float))
            and _parse_length_mm(str(main_length).replace(" ", "")) is not None
            and (_parse_length_mm(str(main_length).replace(" ", "")) or 0) < float(length_table["max"]) * 0.5
        )
    )

    if max_diameter and main_length and not prefer_table:
        parts.append(f"{max_diameter} × {main_length}")
    elif max_diameter and length_table:
        tol = f" ({length_table['tolerance']})" if length_table.get("tolerance") else ""
        parts.append(
            f"{max_diameter} × {length_param}{tol} "
            f"({length_table['min']:g}...{length_table['max']:g} мм, по исполнениям)"
        )
    elif main_length and diameter_table:
        fit = diameter_table.get("fit")
        fit_suffix = f" {fit}" if fit else ""
        values = ", ".join(f"Ø{v:g}{fit_suffix}" for v in diameter_table.get("values", [])[:8])
        parts.append(f"{main_length}; Ø по исполнениям: {values}")
    elif max_diameter:
        parts.append(str(max_diameter))
    elif main_length:
        parts.append(str(main_length))
    elif length_table:
        parts.append(
            f"{length_param} {length_table['min']:g}...{length_table['max']:g} мм (по исполнениям)"
        )
    elif diameter_table:
        fit = diameter_table.get("fit")
        fit_suffix = f" {fit}" if fit else ""
        values = ", ".join(f"Ø{v:g}{fit_suffix}" for v in diameter_table.get("values", [])[:8])
        parts.append(f"Ø по исполнениям: {values}")

    if parts:
        overall["display"] = "; ".join(parts)


def cleanup_external_contour(features: dict[str, Any]) -> None:
    """Убрать из наружного контура длины и служебные метки."""
    cleaned: list[dict[str, Any]] = []
    for fact in features.get("external_contour", []):
        value = str(fact.get("value", ""))
        normalized = value.replace(" ", "").lower()
        if fact.get("type") == "overall_length":
            continue
        if _is_length_token(normalized):
            continue
        if _is_dimension_label(normalized):
            continue
        cleaned.append(fact)
    features["external_contour"] = cleaned


def filter_critical_unclassified(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    critical: list[dict[str, Any]] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.get("normalized", "")
        lowered = normalized.lower()
        if lowered in seen:
            continue
        if re.search(r"^Ra\s*\d", normalized, re.IGNORECASE):
            continue
        if re.fullmatch(r"IT\d+", normalized, re.IGNORECASE):
            continue
        if THREAD_RE.search(normalized):
            continue
        if _is_dimension_label(normalized):
            continue
        if re.fullmatch(r"\d+°", normalized):
            continue
        if not CRITICAL_DIMENSION_RE.search(normalized):
            continue
        seen.add(lowered)
        critical.append(token)
    return critical
