from dxf_converter.overall_display import finalize_overall_display, filter_critical_unclassified


def test_finalize_overall_display_max_diameter_and_length():
    features = {
        "overall": {"max_diameter": "∅70e8(-0,060-0,106)", "main_length": "105"},
        "external_contour": [],
    }
    finalize_overall_display(features, [])
    assert features["overall"]["display"] == "∅70e8(-0,060-0,106) × 105"


def test_filter_critical_unclassified_skips_ra_and_it():
    tokens = [
        {"normalized": "Ra0,80", "value": "Ra 0,80"},
        {"normalized": "IT14", "value": "IT14"},
        {"normalized": "Ø16c11(-0,095-0,205)", "value": "∅16c11(-0,095-0,205)"},
    ]
    critical = filter_critical_unclassified(tokens)
    assert len(critical) == 1
    assert "c11" in critical[0]["value"]
