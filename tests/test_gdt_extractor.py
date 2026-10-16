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
    roughness = next(item for item in features if item["type"] == "surface_roughness")
    hints = {entry["target_hint"] for entry in roughness["value"]}
    assert "general_unspecified" in hints


@pytest.mark.unit
def test_extract_gdt_symmetry_not_runout_for_0_1():
    facts, features = extract_gdt(["симметричность относительно базы А", "0,1", "Ø20"])
    form = [item for item in features if item["type"] == "form_tolerance"]
    assert form
    assert form[0]["value"]["kind"] == "symmetry"
    assert form[0]["value"]["base_hint"] == "A"
    assert any("Симметрич" in item for item in facts)
    assert not any("Биение относительно базы А: не более 0,1" in item for item in facts)


@pytest.mark.unit
def test_extract_gdt_perpendicularity_and_datum_b():
    facts, features = extract_gdt(["перпендикулярность относительно базы B", "0,02", "Ø50"])
    form = [item for item in features if item["type"] == "form_tolerance"]
    assert form
    assert form[0]["value"]["kind"] == "perpendicularity"
    assert form[0]["value"]["base_hint"] == "B"
    assert any("Перпендикулярность" in item for item in facts)


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
