"""Unit-тесты извлечения ГДТ."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.converter.dxf_parser import parse_dxf
from app.converter.gdt_extractor import extract_gdt
from app.converter.semantic_schema import build_semantic_passport_json

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"


@pytest.mark.unit
def test_extract_gdt_ra_values():
    facts, features = extract_gdt(["Ra 3,2 (", "Ra 0,80", "Ra 1,6"])
    assert any("Ra 3,2" in item for item in facts)
    assert any(item["type"] == "surface_roughness" for item in features)


@pytest.mark.unit
def test_extract_gdt_from_sample_flange():
    dxf = SAMPLES_DIR / "07-54-105 - сложность 3 Фланец.dxf"
    if not dxf.is_file():
        pytest.skip("sample flange dxf missing")
    summary = parse_dxf(dxf)
    semantic = build_semantic_passport_json(summary)
    gdt = semantic.engineering_features.get("gdt", [])

    assert semantic.gdt_facts
    assert "gdt" not in semantic.missing_fields
    assert any(item.get("type") == "surface_roughness" for item in gdt)
    assert any(item.get("type") == "form_tolerance" for item in gdt)
    assert any("0,03" in fact for fact in semantic.gdt_facts)
