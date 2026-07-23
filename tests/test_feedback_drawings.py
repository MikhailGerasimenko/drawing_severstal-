from pathlib import Path

import pytest

from dxf_converter.dxf_parser import parse_dxf
from dxf_converter.semantic_schema import build_semantic_passport_json

FEEDBACK_DIR = Path(__file__).resolve().parents[1] / "обратная связь по чертежам"


def _feedback_dxf(pattern: str) -> Path:
    matches = list(FEEDBACK_DIR.glob(pattern))
    if not matches:
        pytest.skip(f"missing feedback dxf: {pattern}")
    return matches[0]


def test_feedback_18_06_2_identity_and_hardness():
    dxf = _feedback_dxf("18-06.2*.dxf")
    semantic = build_semantic_passport_json(parse_dxf(dxf))
    assert semantic.designation.value == "18-06.2"
    assert "Втулка отрезная" in semantic.product_name.value
    assert "подвижная" in semantic.product_name.value.lower()
    assert "48...52" in semantic.material_hardness.value
    assert "56...58" not in semantic.material_hardness.value
    assert "18-06.2" not in (semantic.overall_dimensions.value or "")
    features = semantic.engineering_features
    assert any(item.get("type") == "axial_hole_pattern" for item in features["special_elements"])
    assert any(item.get("type") == "variable_conical_bore" for item in features["internal_system"])


def test_feedback_54_247_outer_vs_hole():
    dxf = _feedback_dxf("54-247*.dxf")
    semantic = build_semantic_passport_json(parse_dxf(dxf))
    assert "71,8" in semantic.overall_dimensions.value
    assert "50" in semantic.overall_dimensions.value
    ext_values = " ".join(str(item.get("value")) for item in semantic.engineering_features["external_contour"])
    int_values = " ".join(str(item.get("value")) for item in semantic.engineering_features["internal_system"])
    assert "71,8" in ext_values
    assert "68,3" in ext_values
    assert "24" in int_values
    assert "71,8" not in int_values


def test_feedback_54_24_hole_tolerance_and_no_fake_specials():
    dxf = _feedback_dxf("54-24*.dxf")
    # Не перепутать с 54-247
    dxf = next(path for path in FEEDBACK_DIR.glob("54-24*.dxf") if "247" not in path.name)
    semantic = build_semantic_passport_json(parse_dxf(dxf))
    assert "80f7" in semantic.overall_dimensions.value
    assert "L" in semantic.overall_dimensions.value
    int_values = " ".join(str(item.get("value")) for item in semantic.engineering_features["internal_system"])
    assert "+0,1" in int_values or "+0.1" in int_values
    assert not any(
        item.get("type") == "groove_detail_candidates"
        for item in semantic.engineering_features["special_elements"]
    )


def test_feedback_55_136_height_table_and_hole():
    dxf = _feedback_dxf("55-136*.dxf")
    semantic = build_semantic_passport_json(parse_dxf(dxf))
    assert "59" in semantic.overall_dimensions.value
    assert "H" in semantic.overall_dimensions.value
    assert "12" in semantic.overall_dimensions.value
    int_values = " ".join(str(item.get("value")) for item in semantic.engineering_features["internal_system"])
    assert "25,9" in int_values
    assert "+0,1" in int_values or "+0.1" in int_values
    ext_values = " ".join(str(item.get("value")) for item in semantic.engineering_features["external_contour"])
    assert "25,9" not in ext_values
