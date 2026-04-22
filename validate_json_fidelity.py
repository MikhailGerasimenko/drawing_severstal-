import argparse
import json
import math
import sys
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Tuple, Dict

sys.path.append(str(Path(__file__).parent / "src"))

from passport_builder.dxf_parser import parse_dxf


def _compare_float(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


def _compare_bbox(
    expected: Optional[Dict[str, Any]], actual: Optional[Dict[str, Any]], tol: float
) -> Tuple[bool, str]:
    if expected is None and actual is None:
        return True, "bbox: both missing"
    if expected is None or actual is None:
        return False, "bbox: one side missing"

    keys = ["min_x", "min_y", "max_x", "max_y", "width", "height"]
    for key in keys:
        if key not in expected or key not in actual:
            return False, f"bbox: missing key {key}"
        if not _compare_float(expected[key], actual[key], tol=tol):
            return False, f"bbox: mismatch on {key} (dxf={expected[key]}, json={actual[key]})"
    return True, "bbox: match"


def _compare_list_lengths(expected: list[Any], actual: list[Any], name: str) -> Tuple[bool, str]:
    if len(expected) != len(actual):
        return False, f"{name}: length mismatch (dxf={len(expected)}, json={len(actual)})"
    return True, f"{name}: length match ({len(expected)})"


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_summary_like(payload: dict[str, Any]) -> dict[str, Any]:
    if "drawing_facts" in payload:
        facts = payload.get("drawing_facts", {})
        legacy = payload.get("legacy_summary", {})
        return {
            "units": facts.get("units", legacy.get("units")),
            "entity_counts": facts.get("entity_counts", legacy.get("entity_counts", {})),
            "bounding_box": facts.get("bounding_box", legacy.get("bounding_box")),
            "dimensions": facts.get("dimensions", legacy.get("dimensions", [])),
            "layers": facts.get("layers", legacy.get("layers", [])),
            "extracted_texts": facts.get("extracted_texts", legacy.get("extracted_texts", [])),
            "geometry": facts.get("geometry", legacy.get("geometry", {})),
            "feature_collection": facts.get("feature_collection", legacy.get("feature_collection", {})),
        }
    return payload


def validate(dxf_path: str, json_path: str, tol: float) -> dict[str, Any]:
    dxf_summary = asdict(parse_dxf(dxf_path))
    json_summary = _extract_summary_like(json.loads(Path(json_path).read_text(encoding="utf-8")))

    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add_check(
        "units",
        dxf_summary.get("units") == json_summary.get("units"),
        f"dxf={dxf_summary.get('units')} json={json_summary.get('units')}",
    )
    add_check(
        "entity_counts",
        dxf_summary.get("entity_counts") == json_summary.get("entity_counts"),
        f"dxf={dxf_summary.get('entity_counts')} json={json_summary.get('entity_counts')}",
    )

    bbox_ok, bbox_detail = _compare_bbox(dxf_summary.get("bounding_box"), json_summary.get("bounding_box"), tol=tol)
    add_check("bounding_box", bbox_ok, bbox_detail)

    for key in ["dimensions", "layers", "extracted_texts"]:
        ok, detail = _compare_list_lengths(dxf_summary.get(key, []), json_summary.get(key, []), key)
        add_check(key, ok, detail)

    dxf_geom = dxf_summary.get("geometry", {})
    json_geom = json_summary.get("geometry", {})
    for key in ["lines", "circles", "arcs", "polylines", "texts"]:
        ok, detail = _compare_list_lengths(dxf_geom.get(key, []), json_geom.get(key, []), f"geometry.{key}")
        add_check(f"geometry.{key}", ok, detail)

    dxf_fc = dxf_summary.get("feature_collection", {})
    json_fc = json_summary.get("feature_collection", {})
    dxf_features = dxf_fc.get("features", []) if isinstance(dxf_fc, dict) else []
    json_features = json_fc.get("features", []) if isinstance(json_fc, dict) else []
    ok_fc, detail_fc = _compare_list_lengths(dxf_features, json_features, "feature_collection.features")
    add_check("feature_collection.features", ok_fc, detail_fc)

    for key in ["dimensions", "layers", "extracted_texts"]:
        exp = dxf_summary.get(key, [])
        act = json_summary.get(key, [])
        if exp and act:
            add_check(
                f"{key}.fingerprint",
                _fingerprint(exp) == _fingerprint(act),
                f"dxf={_fingerprint(exp)} json={_fingerprint(act)}",
            )

    for key in ["lines", "circles", "arcs", "polylines", "texts"]:
        exp = dxf_geom.get(key, [])
        act = json_geom.get(key, [])
        if exp and act:
            sample_size = min(len(exp), len(act), 20)
            add_check(
                f"geometry.{key}.sample_fingerprint",
                _fingerprint(exp[:sample_size]) == _fingerprint(act[:sample_size]),
                f"sample_size={sample_size}",
            )

    if dxf_features and json_features:
        sample_size = min(len(dxf_features), len(json_features), 20)
        add_check(
            "feature_collection.sample_fingerprint",
            _fingerprint(dxf_features[:sample_size]) == _fingerprint(json_features[:sample_size]),
            f"sample_size={sample_size}",
        )

    passed = all(c["ok"] for c in checks)
    return {
        "dxf_file": Path(dxf_path).name,
        "json_file": Path(json_path).name,
        "passed": passed,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate JSON fidelity against DXF parser output")
    parser.add_argument("--dxf", required=True, help="Path to source DXF")
    parser.add_argument("--json", required=True, help="Path to generated JSON")
    parser.add_argument("--tol", type=float, default=1e-6, help="Float tolerance for bbox comparison")
    parser.add_argument("--out", default=None, help="Optional output report path (.json)")
    args = parser.parse_args()

    report = validate(args.dxf, args.json, args.tol)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved report: {args.out}")

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
