from pathlib import Path

import pytest

from dxf_converter.dxf_parser import parse_dxf
from dxf_converter.semantic_schema import build_semantic_passport_json

DRAWINGS2 = Path(__file__).resolve().parents[1] / "чертежи 2"


def _dxf(pattern: str) -> Path:
    matches = list(DRAWINGS2.glob(pattern))
    if not matches:
        pytest.skip(f"missing чертежи 2 dxf: {pattern}")
    return matches[0]


def test_drawings2_54_20_punch():
    semantic = build_semantic_passport_json(parse_dxf(_dxf("54-20*.dxf")))
    assert "Пуансон" in semantic.product_name.value
    assert semantic.designation.value.startswith("54-20")
    assert "45d10" in (semantic.overall_dimensions.value or "")
    assert "128" in (semantic.overall_dimensions.value or "")
    ext = " ".join(str(item.get("value")) for item in semantic.engineering_features["external_contour"])
    int_vals = " ".join(str(item.get("value")) for item in semantic.engineering_features["internal_system"])
    assert "R52" not in int_vals and "R14" not in int_vals
    assert "b-0,2" in ext or "b-0.2" in ext or any(
        item.get("type") == "straight_section" for item in semantic.engineering_features["external_contour"]
    )


def test_drawings2_54_25_clamp():
    semantic = build_semantic_passport_json(parse_dxf(_dxf("54-25*.dxf")))
    assert semantic.product_name.value == "Прижим"
    overall = semantic.overall_dimensions.value or ""
    assert "80" in overall
    assert "28" in overall
    assert any(
        item.get("type") == "rectangular_window"
        for item in semantic.engineering_features["internal_system"]
    )
    assert any(
        item.get("type") == "corner_blind_holes"
        for item in semantic.engineering_features["special_elements"]
    )
    chamfer_targets = [
        item
        for item in semantic.engineering_features["internal_system"]
        if item.get("type") == "chamfers"
    ]
    assert chamfer_targets, "6×45° должна быть во внутренней системе"
