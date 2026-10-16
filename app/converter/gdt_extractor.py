"""Извлечение ГДТ и шероховатости из текстовых аннотаций DXF."""
from __future__ import annotations

import re
from typing import Any

RA_RE = re.compile(r"\bRa\s*(\d+(?:[,.]\d+)?)\b", re.IGNORECASE)
GDT_WORD_RE = re.compile(
    r"(биени|радиальн|торцев|симметрич|перпенд|параллельн|соосност|плоскост|позици|"
    r"круглост|цилиндричн|прямолинейн|профиль)",
    re.IGNORECASE,
)
GDT_SYMBOL_RE = re.compile(r"(⌅|∥|⟂|⊥|//|◎|≡|⌀)")
DATUM_LETTER_RE = re.compile(
    r"баз[аыеу]?\s*([A-Za-zА-Яа-я])\b|\bбаз(?:а|ы)?\s*[«\"']?([A-Za-zА-Яа-я])",
    re.IGNORECASE,
)
GENERAL_TOLERANCE_RE = re.compile(
    r"\b(?:H|h)\s*14\b|\bIT\s*14(?:\s*/\s*2)?\b",
    re.IGNORECASE,
)
STANDALONE_FORM_TOLERANCE_RE = re.compile(r"^0[,.]\d{1,3}$")
COMMON_GDT_TOLERANCE_MM = {0.01, 0.02, 0.03, 0.05}
# 0,1 / 0,17 часто из таблиц допусков, не из рамок ГДТ — не поднимать без повторов.
WEAK_GDT_TOLERANCE_MM = {0.1, 0.17, 0.2}
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
        if rounded in WEAK_GDT_TOLERANCE_MM:
            continue
        if rounded in COMMON_GDT_TOLERANCE_MM or count >= 2:
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


def _infer_gdt_kind(text: str) -> str:
    lowered = text.lower()
    if "симметрич" in lowered or "≡" in text:
        return "symmetry"
    if "позици" in lowered:
        return "position"
    if "перпенд" in lowered or "⟂" in text or "⊥" in text:
        return "perpendicularity"
    if "параллел" in lowered or "∥" in text or "⌅" in text:
        return "parallelism"
    if "соосн" in lowered or "◎" in text:
        return "coaxiality"
    if "плоскост" in lowered:
        return "flatness"
    if "круглост" in lowered:
        return "circularity"
    if "цилиндричн" in lowered:
        return "cylindricity"
    if "прямолинейн" in lowered:
        return "straightness"
    if "профиль" in lowered:
        return "profile"
    if "биени" in lowered or "радиальн" in lowered or "торцев" in lowered:
        return "runout"
    return "unknown"


def _infer_datum_letter(text: str) -> str | None:
    match = DATUM_LETTER_RE.search(text)
    if not match:
        return None
    letter = match.group(1) or match.group(2)
    if not letter:
        return None
    # Кириллические А/В/С в штампах → латиница для стабильного JSON.
    normalized = letter.upper().translate(str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX"))
    return normalized


def _kind_label(kind: str, datum: str | None) -> str:
    base = datum or "А"
    labels = {
        "symmetry": f"Симметричность относительно базы {base}",
        "position": f"Позиционный допуск относительно базы {base}",
        "coaxiality": f"Соосность относительно базы {base}",
        "perpendicularity": f"Перпендикулярность относительно базы {base}",
        "parallelism": f"Параллельность относительно базы {base}",
        "flatness": "Плоскостность",
        "circularity": "Круглость",
        "cylindricity": "Цилиндричность",
        "straightness": "Прямолинейность",
        "profile": "Профиль поверхности/линии",
        "runout": f"Биение относительно базы {base}",
    }
    return labels.get(kind, f"Геометрический допуск относительно базы {base}")


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
        kind = _infer_gdt_kind(text)
        add_fact_line(text)
        features.append(
            _fact(
                "gdt_note",
                {"text": text, "kind": kind},
                label="Текстовая аннотация ГДТ",
                source=_source(text),
                confidence="high",
                note="Тип ГДТ берётся из формулировки/символа, не из одного числа допуска.",
            )
        )

    ra_values = _collect_ra_values(text_evidence)
    ra_targets: list[dict[str, str]] = []
    for text in text_evidence:
        match = RA_RE.search(text)
        if not match:
            continue
        target = ""
        diam = OUTER_DIAMETER_RE.search(text)
        if diam:
            target = f"Ø{diam.group(1)}"
        elif re.search(r"торц|баз", text, re.I):
            target = "face_or_datum"
        elif re.search(r"неуказан|общ\w*\s+шерох|для\s+остальн", text, re.I):
            target = "general_unspecified"
        # Одиночный короткий токен Ra без Ø рядом — типичный общий знак (правый верх).
        elif len(text.strip()) <= 12 and not diam:
            target = "general_unspecified"
        ra_targets.append(
            {
                "parameter": "Ra",
                "value": _format_decimal(match.group(1)),
                "target_hint": target or "unbound",
            }
        )
    if ra_values:
        if len(ra_values) == 1:
            line = f"Шероховатость: Ra {ra_values[0]}"
        else:
            line = "Шероховатость: " + ", ".join(f"Ra {value}" for value in ra_values)
        add_fact_line(line)
        features.append(
            _fact(
                "surface_roughness",
                ra_targets or [{"parameter": "Ra", "value": value, "target_hint": "unbound"} for value in ra_values],
                label="Шероховатость поверхностей",
                source=_source(line),
                confidence="high",
                note=(
                    "Локальные Ra — с target_hint (Ø/торец). "
                    "general_unspecified — общая неуказанная шероховатость (обычно правый верх), только в notes."
                ),
            )
        )

    form_tolerances = _collect_form_tolerance_values(text_evidence)
    if any(_infer_gdt_kind(text) == "symmetry" for text in text_evidence):
        seen_tol = {item[0] for item in form_tolerances}
        for text in text_evidence:
            cleaned = text.strip().rstrip("(").strip()
            if cleaned in seen_tol:
                continue
            if STANDALONE_FORM_TOLERANCE_RE.match(cleaned) and _parse_decimal(cleaned) == 0.1:
                form_tolerances.append((cleaned, text))
                seen_tol.add(cleaned)
    outer_diams = _collect_outer_diameters_for_runout(text_evidence)
    descriptive = _collect_descriptive_gdt(text_evidence)
    descriptive_kinds = {_infer_gdt_kind(text) for text in descriptive}
    preferred_kind = next(
        (
            kind
            for kind in ("symmetry", "position", "coaxiality", "perpendicularity", "parallelism")
            if kind in descriptive_kinds
        ),
        "runout",
    )
    preferred_datum = next(
        (letter for text in descriptive if (letter := _infer_datum_letter(text))),
        "A",
    )
    for value, source_text in form_tolerances:
        kind = _infer_gdt_kind(source_text)
        if kind == "unknown":
            kind = preferred_kind
        datum = _infer_datum_letter(source_text) or preferred_datum
        label = _kind_label(kind, datum)
        related = outer_diams[:3] or [None]
        for target in related:
            surfaces = [target] if target else []
            line = f"{label}: не более {value} мм"
            if target:
                line += f" (поверхность: {target})"
            add_fact_line(line)
            features.append(
                _fact(
                    "form_tolerance",
                    {
                        "kind": kind,
                        "tolerance_mm": value,
                        "related_geometry": surfaces,
                        "base_hint": datum,
                        "formulation_hint": label,
                    },
                    label=label,
                    source=_source(source_text),
                    confidence="medium" if target else "low",
                    note=(
                        "Отдельный факт на каждую поверхность; 0,1 без символа биения не считать биением. "
                        "Укажи конкретную базовую поверхность (Ø/торец/отверстие), не только букву. "
                        "Не объединяй две поверхности в одно требование."
                    ),
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
