"""Извлечение ГДТ и шероховатости из текстовых аннотаций DXF."""
from __future__ import annotations

import re
from typing import Any

RA_RE = re.compile(r"\bRa\s*(\d+(?:[,.]\d+)?)\b", re.IGNORECASE)
GDT_WORD_RE = re.compile(
    r"(биени|радиальн|торцев|симметрич|перпенд|параллельн|соосност|плоскост|позици)",
    re.IGNORECASE,
)
GDT_SYMBOL_RE = re.compile(r"(⌅|∥|⟂|⊥|//|◎|≡)")
GENERAL_TOLERANCE_RE = re.compile(
    r"\b(?:H|h)\s*14\b|\bIT\s*14(?:\s*/\s*2)?\b",
    re.IGNORECASE,
)
STANDALONE_FORM_TOLERANCE_RE = re.compile(r"^0[,.]\d{1,3}$")
COMMON_GDT_TOLERANCE_MM = {0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2}
OUTER_DIAMETER_RE = re.compile(
    r"[Ø∅]\s*(\d+(?:[,.]\d+)?)\s*([a-zA-Zа-яА-Я]\d+)?",
    re.IGNORECASE,
)
def _parse_decimal(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _format_decimal(value: str) -> str:
    return value.replace(".", ",")


def _source(raw: str) -> dict[str, str]:
    return {"type": "text", "raw": raw}


def _fact(
    fact_type: str,
    value: Any,
    *,
    label: str,
    source: dict[str, str],
    confidence: str = "medium",
    note: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": fact_type,
        "value": value,
        "label": label,
        "source": source,
        "confidence": confidence,
    }
    if note:
        payload["note"] = note
    return payload


def _collect_ra_values(text_evidence: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for text in text_evidence:
        for match in RA_RE.finditer(text):
            raw = match.group(1)
            formatted = _format_decimal(raw)
            if formatted not in seen:
                seen.add(formatted)
                values.append(formatted)
    return values


def _collect_form_tolerance_values(text_evidence: list[str]) -> list[tuple[str, str]]:
    counts: dict[str, int] = {}
    sources: dict[str, str] = {}
    for text in text_evidence:
        cleaned = text.strip().rstrip("(").strip()
        if not STANDALONE_FORM_TOLERANCE_RE.match(cleaned):
            continue
        decimal = _parse_decimal(cleaned)
        if decimal is None or decimal < 0.005 or decimal > 0.5:
            continue
        counts[cleaned] = counts.get(cleaned, 0) + 1
        sources.setdefault(cleaned, text)

    if len(counts) >= 6:
        counts = {
            value: count
            for value, count in counts.items()
            if _parse_decimal(value) in COMMON_GDT_TOLERANCE_MM
        }
    elif len(counts) >= 4:
        decimals = sorted({_parse_decimal(value) for value in counts if _parse_decimal(value) is not None})
        if len(decimals) >= 4:
            steps = {round(decimals[index + 1] - decimals[index], 3) for index in range(len(decimals) - 1)}
            if len(steps) == 1 and next(iter(steps)) > 0:
                counts = {
                    value: count
                    for value, count in counts.items()
                    if _parse_decimal(value) in COMMON_GDT_TOLERANCE_MM
                }

    results: list[tuple[str, str]] = []
    for value, count in sorted(counts.items(), key=lambda item: item[0]):
        decimal = _parse_decimal(value)
        if decimal is None:
            continue
        rounded = round(decimal, 3)
        if count >= 2 or rounded in COMMON_GDT_TOLERANCE_MM:
            results.append((value, sources[value]))
    return results


def _collect_general_tolerances(text_evidence: list[str]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for text in text_evidence:
        if not GENERAL_TOLERANCE_RE.search(text):
            continue
        normalized = re.sub(r"\s+", " ", text.strip())
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append((normalized, text))
    return results


def _collect_descriptive_gdt(text_evidence: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for text in text_evidence:
        if not (GDT_WORD_RE.search(text) or GDT_SYMBOL_RE.search(text)):
            continue
        normalized = re.sub(r"\s+", " ", text.strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    return results


def _collect_outer_diameters_for_runout(text_evidence: list[str]) -> list[str]:
    seen: set[str] = set()
    diameters: list[str] = []
    for text in text_evidence:
        for match in OUTER_DIAMETER_RE.finditer(text):
            diameter = match.group(1)
            fit = (match.group(2) or "").strip()
            token = f"Ø{diameter}{fit}" if fit else f"Ø{diameter}"
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            diameters.append(token)
    return diameters[:5]


def extract_gdt(text_evidence: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Возвращает (gdt_facts для semantic, structured facts для engineering_features)."""
    facts: list[str] = []
    features: list[dict[str, Any]] = []
    seen_facts: set[str] = set()

    def add_fact_line(line: str) -> None:
        normalized = re.sub(r"\s+", " ", line.strip())
        if normalized and normalized.lower() not in seen_facts:
            seen_facts.add(normalized.lower())
            facts.append(normalized)

    for text in _collect_descriptive_gdt(text_evidence):
        add_fact_line(text)
        features.append(
            _fact(
                "gdt_note",
                text,
                label="Текстовая аннотация ГДТ",
                source=_source(text),
                confidence="high",
            )
        )

    ra_values = _collect_ra_values(text_evidence)
    if ra_values:
        if len(ra_values) == 1:
            line = f"Шероховатость: Ra {ra_values[0]}"
        else:
            line = "Шероховатость: " + ", ".join(f"Ra {value}" for value in ra_values)
        add_fact_line(line)
        features.append(
            _fact(
                "surface_roughness",
                [{"parameter": "Ra", "value": value} for value in ra_values],
                label="Шероховатость поверхностей",
                source=_source(line),
                confidence="high",
                note="Значения Ra из аннотаций чертежа; привязка к конкретным поверхностям требует визуальной проверки.",
            )
        )

    form_tolerances = _collect_form_tolerance_values(text_evidence)
    outer_diams = _collect_outer_diameters_for_runout(text_evidence)
    for value, source_text in form_tolerances:
        if outer_diams:
            target = outer_diams[0]
            line = f"Допуск формы (кандидат): не более {value} мм (возможно биение {target})"
        else:
            line = f"Допуск формы (кандидат): не более {value} мм"
        add_fact_line(line)
        features.append(
            _fact(
                "form_tolerance",
                {"tolerance_mm": value, "related_geometry": outer_diams[:3]},
                label="Допуск формы / биение (кандидат)",
                source=_source(source_text),
                confidence="medium" if outer_diams else "low",
                note="На чертеже указано только числовое значение рамки ГДТ без текстовой расшифровки.",
            )
        )

    for value, source_text in _collect_general_tolerances(text_evidence):
        add_fact_line(f"Общие допуски: {value}")
        features.append(
            _fact(
                "general_tolerance",
                value,
                label="Общие допуски (H14/IT14)",
                source=_source(source_text),
                confidence="high",
            )
        )

    if not facts:
        for text in text_evidence:
            if GDT_SYMBOL_RE.search(text):
                add_fact_line(text)
                features.append(
                    _fact(
                        "gdt_symbol",
                        text,
                        label="Символ ГДТ",
                        source=_source(text),
                        confidence="medium",
                    )
                )

    return facts, features
