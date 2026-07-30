from dxf_converter.dimension_classifier import (
    INTERNAL_FIT_RE,
    SHAFT_FIT_RE,
    _has_internal_fit,
    _has_shaft_fit,
    apply_generic_dimension_classification,
)


def _token(value: str) -> dict:
    return {"value": value, "normalized": value.replace("∅", "Ø").replace(" ", ""), "source": {"raw": value}}


def test_c11_is_external_shaft_fit():
    assert not _has_internal_fit("Ø16c11(-0,095-0,205)")
    assert _has_shaft_fit("Ø16c11(-0,095-0,205)")


def test_h11_is_internal_hole_fit():
    assert _has_internal_fit("Ø8H11(+0,09)")
    assert not _has_shaft_fit("Ø8H11(+0,09)")


def test_b10_is_external_shaft_fit():
    assert _has_shaft_fit("Ø70b10(-0,20-0,32)")


def test_generic_classification_puts_c11_to_external_contour():
    features = {
        "overall": {},
        "external_contour": [],
        "internal_system": [],
        "special_elements": [],
    }
    classified: set[str] = set()
    tokens = [_token("∅16c11(-0,095-0,205)"), _token("100±0,2"), _token("M8-7H")]
    apply_generic_dimension_classification(features, tokens, classified, ["M8-7H"])
    assert features["external_contour"]
    assert "c11" in features["external_contour"][0]["value"].lower()
    assert any(item.get("type") == "thread" for item in features["special_elements"])


def test_length_not_added_as_outer_diameter():
    features = {
        "overall": {},
        "external_contour": [],
        "internal_system": [],
        "special_elements": [],
        "llm_interpretation_rules": [],
    }
    classified: set[str] = set()
    tokens = [_token("∅30s7(+0,056+0,035)"), _token("60-0,5")]
    apply_generic_dimension_classification(features, tokens, classified, [])
    assert features["overall"].get("main_length") == "60-0,5"
    # Длина может быть в external_contour как overall_length, но не как outer_diameter.
    assert all(
        item.get("type") != "outer_diameter" or "60" not in str(item.get("value"))
        for item in features["external_contour"]
    )
