from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any


def normalize_text(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace("Ø", "ø").replace("⌀", "ø")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,.])\s*", r"\1", text)
    return text.lower()


def similarity(a: str, b: str) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


@dataclass
class PassportFields:
    part_type: str = ""
    designation: str = ""
    overall_dimensions: str = ""
    material_hardness: str = ""
    outer_geometry: str = ""
    inner_geometry: str = ""
    special_elements: str = ""
    gdt: str = ""
    notes: str = ""
    raw_text: str = ""
    source_format: str = "markdown"


@dataclass
class FieldComparison:
    name: str
    expected: str
    actual: str
    exact_match: bool
    similarity: float


@dataclass
class ComparisonReport:
    case_id: str
    fields: list[FieldComparison] = field(default_factory=list)
    converter_designation: str = ""
    converter_part_type: str = ""
    converter_gate_status: str = ""
    converter_gate_warnings: list[str] = field(default_factory=list)

    @property
    def header_exact_rate(self) -> float:
        header = [item for item in self.fields if item.name in HEADER_FIELDS]
        if not header:
            return 0.0
        return sum(1 for item in header if item.exact_match) / len(header)

    @property
    def average_similarity(self) -> float:
        if not self.fields:
            return 0.0
        return sum(item.similarity for item in self.fields) / len(self.fields)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["header_exact_rate"] = self.header_exact_rate
        payload["average_similarity"] = self.average_similarity
        return payload


HEADER_FIELDS = {
    "part_type",
    "designation",
    "overall_dimensions",
    "material_hardness",
}

COMPARE_FIELDS = [
    "part_type",
    "designation",
    "overall_dimensions",
    "material_hardness",
    "outer_geometry",
    "inner_geometry",
    "special_elements",
    "gdt",
    "notes",
]


def compare_passports(expected: PassportFields, actual: PassportFields) -> list[FieldComparison]:
    results: list[FieldComparison] = []
    for name in COMPARE_FIELDS:
        exp = getattr(expected, name, "")
        got = getattr(actual, name, "")
        results.append(
            FieldComparison(
                name=name,
                expected=exp,
                actual=got,
                exact_match=normalize_text(exp) == normalize_text(got) and bool(normalize_text(exp)),
                similarity=similarity(exp, got),
            )
        )
    return results
