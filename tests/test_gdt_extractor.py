"""Тесты извлечения ГДТ и парсера эталонных паспортов."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from dxf_converter.dxf_parser import parse_dxf
from dxf_converter.gdt_extractor import extract_gdt
from dxf_converter.semantic_schema import build_semantic_passport_json
from lib.golden import load_golden_passport

GOLDEN_DIR = ROOT / "dxf+паспорт"


def test_extract_gdt_from_flange_drawing():
    summary = parse_dxf(GOLDEN_DIR / "07-54-105 - сложность 3 Фланец.dxf")
    semantic = build_semantic_passport_json(summary)
    gdt = semantic.engineering_features.get("gdt", [])

    assert semantic.gdt_facts
    assert "gdt" not in semantic.missing_fields
    assert any(item.get("type") == "surface_roughness" for item in gdt)
    assert any(item.get("type") == "form_tolerance" for item in gdt)
    assert any("0,03" in fact for fact in semantic.gdt_facts)


def test_extract_gdt_ra_values():
    facts, features = extract_gdt(["Ra 3,2 (", "Ra 0,80", "Ra 1,6"])
    assert any("Ra 3,2" in item for item in facts)
    assert any(item["type"] == "surface_roughness" for item in features)


def test_golden_docx_geometry_sections():
    passport = load_golden_passport(GOLDEN_DIR / "Паспорт  07-54-105.docx")
    assert passport.outer_geometry
    assert "ø119" in passport.outer_geometry or "119" in passport.outer_geometry
    assert passport.inner_geometry
    assert passport.gdt
    assert "0,03" in passport.gdt or "биени" in passport.gdt


@pytest.mark.parametrize(
    "docx_name",
    [
        "Паспорт  07-54-105.docx",
        "Паспорт 07-54-521.docx",
        "Паспорт 07-54-511.docx",
    ],
)
def test_golden_docx_has_gdt_section(docx_name: str):
    path = GOLDEN_DIR / docx_name
    if not path.is_file():
        pytest.skip(f"missing golden: {docx_name}")
    passport = load_golden_passport(path)
    assert passport.gdt


def test_washer_gdt_filters_tolerance_table():
    matches = list(GOLDEN_DIR.glob("*521*"))
    dxf = next((path for path in matches if path.suffix.lower() == ".dxf"), None)
    if dxf is None:
        pytest.skip("missing 521 dxf")
    semantic = build_semantic_passport_json(parse_dxf(dxf))
    form_facts = [
        item for item in semantic.engineering_features.get("gdt", [])
        if item.get("type") == "form_tolerance"
    ]
    assert len(form_facts) == 1
    assert form_facts[0]["value"]["tolerance_mm"] == "0,03"
