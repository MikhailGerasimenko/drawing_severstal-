"""Смысловое сравнение паспортов: ключевые факты вместо побуквенного similarity."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .compare import PassportFields, normalize_text

DIAMETER_RE = re.compile(r"[ø∅⌀]\s*(\d+(?:[,.]\d+)?)\s*([a-zа-я]\d+)?", re.IGNORECASE)
RA_RE = re.compile(r"\bra\s*(\d+(?:[,.]\d+)?)\b", re.IGNORECASE)
GOST_RE = re.compile(r"гост\s*[\d-]+", re.IGNORECASE)
HRC_RE = re.compile(r"(\d+)\s*(?:\.\.\.|…|-)\s*(\d+)\s*hrc", re.IGNORECASE)
GDT_TOL_RE = re.compile(r"не более\s*0[,.]\d+|\b0[,.]\d{1,3}\s*мм|\b0[,.]\d{1,3}\b", re.IGNORECASE)

NOTE_KEYWORDS = ("маркир", "h14", "it14", "it/4", "таблиц", "тверд", "масса")

SEMANTIC_WEIGHTS = {
    "part_type": 2.0,
    "designation": 2.0,
    "material_hardness": 2.0,
    "overall_dimensions": 1.5,
    "outer_geometry": 2.0,
    "inner_geometry": 2.0,
    "special_elements": 1.5,
    "gdt": 1.5,
    "notes": 1.0,
}


@dataclass
class SemanticFieldScore:
    name: str
    score: float
    detail: str = ""


@dataclass
class SemanticComparisonReport:
    case_id: str
    fields: list[SemanticFieldScore] = field(default_factory=list)

    @property
    def average_score(self) -> float:
        if not self.fields:
            return 0.0
        return sum(item.score for item in self.fields) / len(self.fields)

    @property
    def weighted_score(self) -> float:
        total_weight = 0.0
        weighted = 0.0
        for item in self.fields:
            weight = SEMANTIC_WEIGHTS.get(item.name, 1.0)
            weighted += item.score * weight
            total_weight += weight
        if not total_weight:
            return 0.0
        return weighted / total_weight

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["average_score"] = self.average_score
        payload["weighted_score"] = self.weighted_score
        return payload


def _parse_decimal(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _extract_diameter_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for match in DIAMETER_RE.finditer(normalize_text(text)):
        number = match.group(1).replace(".", ",")
        fit = (match.group(2) or "").lower()
        keys.add(f"{number}|{fit}")
    return keys


def _extract_ra_values(text: str) -> set[str]:
    return {match.group(1).replace(".", ",") for match in RA_RE.finditer(normalize_text(text))}


def _extract_gdt_tolerances(text: str) -> set[str]:
    values: set[str] = set()
    for match in GDT_TOL_RE.finditer(normalize_text(text)):
        number = re.search(r"0[,.]\d+", match.group(0))
        if not number:
            continue
        decimal = _parse_decimal(number.group(0))
        if decimal is None or decimal > 0.2:
            continue
        values.add(number.group(0).replace(".", ","))
    return values


def _diameter_coverage(expected: str, actual: str) -> float:
    expected_keys = _extract_diameter_keys(expected)
    actual_keys = _extract_diameter_keys(actual)
    if not expected_keys and not actual_keys:
        return 1.0
    if not expected_keys:
        return 0.5
    if not actual_keys:
        return 0.0
    hits = 0
    for key in expected_keys:
        number, fit = key.split("|", 1)
        number_dot = number.replace(",", ".")
        for actual_key in actual_keys:
            actual_number, actual_fit = actual_key.split("|", 1)
            if actual_number.replace(",", ".") != number_dot:
                continue
            if not fit or not actual_fit or fit == actual_fit:
                hits += 1
                break
    return hits / len(expected_keys)


def _score_header(expected: str, actual: str) -> tuple[float, str]:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)
    if not expected_norm and not actual_norm:
        return 1.0, "both_empty"
    if not expected_norm or not actual_norm:
        return 0.0, "one_empty"
    if expected_norm == actual_norm or expected_norm in actual_norm or actual_norm in expected_norm:
        return 1.0, "match"
    if expected_norm.split("-")[-1] == actual_norm.split("-")[-1]:
        return 0.85, "suffix_match"
    return 0.2, "mismatch"


def _score_material(expected: str, actual: str) -> tuple[float, str]:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)
    if not expected_norm and not actual_norm:
        return 1.0, "both_empty"
    if not expected_norm or not actual_norm:
        return 0.0, "one_empty"

    parts: list[float] = []
    expected_gost = set(match.group(0) for match in GOST_RE.finditer(expected_norm))
    actual_gost = set(match.group(0) for match in GOST_RE.finditer(actual_norm))
    if expected_gost:
        parts.append(len(expected_gost & actual_gost) / len(expected_gost))

    hardness = HRC_RE.search(expected_norm)
    if hardness:
        parts.append(1.0 if hardness.group(1) in actual_norm and hardness.group(2) in actual_norm else 0.0)

    material_markers = ("сталь", "бронз", "латун", "чугун")
    parts.append(
        1.0
        if any(marker in expected_norm for marker in material_markers)
        and any(marker in actual_norm for marker in material_markers)
        else 0.0
    )
    return sum(parts) / len(parts), "facts"


def _score_gdt(expected: str, actual: str) -> tuple[float, str]:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)
    if not expected_norm and not actual_norm:
        return 1.0, "both_empty"
    if "отсутств" in expected_norm and ("отсутств" in actual_norm or not actual_norm.strip()):
        return 1.0, "absent"
    if "отсутств" in expected_norm:
        return 0.4, "unexpected_gdt"

    expected_ra = _extract_ra_values(expected_norm)
    actual_ra = _extract_ra_values(actual_norm)
    expected_tol = _extract_gdt_tolerances(expected_norm)
    actual_tol = _extract_gdt_tolerances(actual_norm)

    scores: list[float] = []
    if expected_ra:
        scores.append(len(expected_ra & actual_ra) / len(expected_ra))
    if expected_tol:
        scores.append(len(expected_tol & actual_tol) / len(expected_tol))

    expected_keywords = ("биени", "радиал", "торцев", "симметр", "позици")
    if any(keyword in expected_norm for keyword in expected_keywords):
        if any(keyword in actual_norm for keyword in (*expected_keywords, "допуск формы", "кандидат")):
            scores.append(0.6)
        elif actual_tol:
            scores.append(0.4)

    if not scores:
        return 1.0 if not actual_norm else 0.3, "no_expected_facts"
    return sum(scores) / len(scores), "facts"


def _score_notes(expected: str, actual: str) -> tuple[float, str]:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)
    if not expected_norm.strip():
        return 1.0, "both_empty"
    if not actual_norm.strip():
        return 0.0, "missing"
    expected_hits = [keyword for keyword in NOTE_KEYWORDS if keyword in expected_norm]
    if not expected_hits:
        return 0.5, "generic"
    actual_hits = sum(1 for keyword in expected_hits if keyword in actual_norm)
    return actual_hits / len(expected_hits), "keywords"


def score_field(name: str, expected: str, actual: str) -> SemanticFieldScore:
    if name in {"part_type", "designation"}:
        score, detail = _score_header(expected, actual)
    elif name == "material_hardness":
        score, detail = _score_material(expected, actual)
    elif name == "gdt":
        score, detail = _score_gdt(expected, actual)
    elif name == "notes":
        score, detail = _score_notes(expected, actual)
    elif name == "overall_dimensions":
        score = _diameter_coverage(expected, actual)
        detail = "diameters"
    elif name in {"outer_geometry", "inner_geometry", "special_elements"}:
        score = _diameter_coverage(expected, actual)
        detail = "diameters"
    else:
        score, detail = 0.0, "unknown"
    return SemanticFieldScore(name=name, score=score, detail=detail)


def compare_passports_semantic(expected: PassportFields, actual: PassportFields) -> SemanticComparisonReport:
    fields = [
        score_field(name, getattr(expected, name, ""), getattr(actual, name, ""))
        for name in SEMANTIC_WEIGHTS
    ]
    return SemanticComparisonReport(case_id="", fields=fields)
