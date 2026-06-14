import re
from pathlib import Path
from typing import Any, Optional, Union

import ezdxf

from .dxf_feature_collection import convert_dxf_to_feature_collection
from .part_identity import extract_part_type_from_stamp, is_garbage_title
from .models import DxfSummary


UNITS_MAP = {
    0: "unitless",
    1: "inch",
    2: "foot",
    3: "mile",
    4: "mm",
    5: "cm",
    6: "m",
}


def _clean_dxf_text(value: str) -> str:
    text = value.replace("\\P", "\n")
    text = re.sub(r"\{\\.*?;([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z0-9]+;?", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _guess_designation(texts: list[str], file_name: str) -> Optional[str]:
    pattern = re.compile(r"\b\d{1,4}(?:-\d+){1,4}\b")
    for line in [file_name, *texts]:
        found = pattern.search(line)
        if found:
            return found.group(0)
    return None


def _guess_title(blocks: list[dict[str, Any]], text_entities: list[str], file_stem: str) -> Optional[str]:
    stamp = extract_part_type_from_stamp(blocks)
    if stamp:
        return stamp[0]

    for text in text_entities:
        cleaned = _clean_dxf_text(text)
        if not is_garbage_title(cleaned) and len(cleaned) > 4:
            return cleaned

    return file_stem if not is_garbage_title(file_stem) else None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if all(hasattr(value, attr) for attr in ("x", "y", "z")):
        return [float(value.x), float(value.y), float(value.z)]
    if all(hasattr(value, attr) for attr in ("x", "y")):
        return [float(value.x), float(value.y)]
    return str(value)


def _entity_raw(entity: Any, *, source: str) -> dict[str, Any]:
    try:
        attribs = entity.dxfattribs()
    except Exception:
        attribs = {}
    detail = {
        "source": source,
        "type": entity.dxftype(),
        "handle": str(getattr(entity.dxf, "handle", "")),
        "layer": str(getattr(entity.dxf, "layer", "")),
        "dxfattribs": _json_safe(attribs),
    }
    if entity.dxftype() in {"TEXT", "MTEXT", "ATTRIB"}:
        raw_text = getattr(entity.dxf, "text", None)
        if entity.dxftype() == "MTEXT":
            raw_text = getattr(entity, "text", raw_text)
        if raw_text:
            detail["text"] = _clean_dxf_text(str(raw_text))
            detail["raw_text"] = str(raw_text)
    return detail


def _dimension_detail(entity: Any, *, source: str) -> dict[str, Any]:
    detail = _entity_raw(entity, source=source)
    detail.update(
        {
            "measurement": _json_safe(getattr(entity.dxf, "actual_measurement", None)),
            "text": _json_safe(getattr(entity.dxf, "text", "")),
            "dimtype": _json_safe(getattr(entity.dxf, "dimtype", None)),
            "geometry_block": _json_safe(getattr(entity.dxf, "geometry", "")),
            "style": _json_safe(getattr(entity.dxf, "dimstyle", "")),
        }
    )
    return detail


def _hatch_detail(entity: Any, *, source: str) -> dict[str, Any]:
    detail = _entity_raw(entity, source=source)
    path_summaries = []
    try:
        for path in entity.paths:
            path_summaries.append(
                {
                    "type": type(path).__name__,
                    "edge_count": len(getattr(path, "edges", []) or []),
                    "vertices_count": len(getattr(path, "vertices", []) or []),
                }
            )
    except Exception:
        path_summaries = []
    detail.update(
        {
            "pattern_name": _json_safe(getattr(entity.dxf, "pattern_name", "")),
            "solid_fill": bool(getattr(entity.dxf, "solid_fill", False)),
            "paths": path_summaries,
        }
    )
    return detail


def _collect_blocks(doc: Any) -> list[dict[str, Any]]:
    blocks = []
    for block in doc.blocks:
        entity_counts: dict[str, int] = {}
        raw_entities = []
        for entity in block:
            entity_type = entity.dxftype()
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
            raw_entities.append(_entity_raw(entity, source=f"block:{block.name}"))
        blocks.append(
            {
                "name": block.name,
                "base_point": _json_safe(getattr(block.block.dxf, "base_point", None)),
                "entity_counts": entity_counts,
                "entities": raw_entities,
            }
        )
    return blocks


def _collect_geometry(entity: Any, geometry: dict[str, list[dict[str, Any]]]) -> None:
    t = entity.dxftype()
    if t == "LINE":
        start = entity.dxf.start
        end = entity.dxf.end
        geometry["lines"].append(
            {
                "x1": float(start[0]),
                "y1": float(start[1]),
                "x2": float(end[0]),
                "y2": float(end[1]),
                "layer": str(getattr(entity.dxf, "layer", "")),
                "handle": str(getattr(entity.dxf, "handle", "")),
            }
        )
    elif t == "CIRCLE":
        center = entity.dxf.center
        geometry["circles"].append(
            {
                "cx": float(center[0]),
                "cy": float(center[1]),
                "r": float(entity.dxf.radius),
                "layer": str(getattr(entity.dxf, "layer", "")),
                "handle": str(getattr(entity.dxf, "handle", "")),
            }
        )
    elif t == "ARC":
        center = entity.dxf.center
        geometry["arcs"].append(
            {
                "cx": float(center[0]),
                "cy": float(center[1]),
                "r": float(entity.dxf.radius),
                "start_angle": float(entity.dxf.start_angle),
                "end_angle": float(entity.dxf.end_angle),
                "layer": str(getattr(entity.dxf, "layer", "")),
                "handle": str(getattr(entity.dxf, "handle", "")),
            }
        )
    elif t == "LWPOLYLINE":
        points = [[float(x), float(y)] for x, y, *_ in entity.get_points("xy")]
        if len(points) >= 2:
            geometry["polylines"].append(
                {
                    "points": points,
                    "closed": bool(entity.closed),
                    "layer": str(getattr(entity.dxf, "layer", "")),
                    "handle": str(getattr(entity.dxf, "handle", "")),
                }
            )
    elif t == "POLYLINE":
        points = [[float(v.x), float(v.y)] for v in entity.points()]
        if len(points) >= 2:
            geometry["polylines"].append(
                {
                    "points": points,
                    "closed": bool(entity.is_closed),
                    "layer": str(getattr(entity.dxf, "layer", "")),
                    "handle": str(getattr(entity.dxf, "handle", "")),
                }
            )
    elif t == "ELLIPSE":
        try:
            points = [[float(v.x), float(v.y)] for v in entity.flattening(distance=0.5)]
            if len(points) >= 2:
                geometry["polylines"].append(
                    {
                        "points": points,
                        "closed": False,
                        "source_type": "ELLIPSE",
                        "layer": str(getattr(entity.dxf, "layer", "")),
                        "handle": str(getattr(entity.dxf, "handle", "")),
                    }
                )
        except Exception:
            pass
    elif t == "SPLINE":
        try:
            points = [[float(v.x), float(v.y)] for v in entity.flattening(distance=0.5)]
            if len(points) >= 2:
                geometry["polylines"].append(
                    {
                        "points": points,
                        "closed": False,
                        "source_type": "SPLINE",
                        "layer": str(getattr(entity.dxf, "layer", "")),
                        "handle": str(getattr(entity.dxf, "handle", "")),
                    }
                )
        except Exception:
            pass
    elif t in {"TEXT", "ATTRIB"}:
        value = getattr(entity.dxf, "text", "")
        if value:
            cleaned = _clean_dxf_text(str(value))
            insert = entity.dxf.insert
            geometry["texts"].append(
                {
                    "raw_text": str(value),
                    "text": cleaned,
                    "x": float(insert[0]),
                    "y": float(insert[1]),
                    "height": float(getattr(entity.dxf, "height", 2.5)),
                    "rotation": float(getattr(entity.dxf, "rotation", 0.0)),
                    "layer": str(getattr(entity.dxf, "layer", "")),
                    "handle": str(getattr(entity.dxf, "handle", "")),
                }
            )
    elif t == "MTEXT":
        value = getattr(entity, "text", "")
        if value:
            cleaned = _clean_dxf_text(str(value))
            insert = entity.dxf.insert
            geometry["texts"].append(
                {
                    "raw_text": str(value),
                    "text": cleaned,
                    "x": float(insert[0]),
                    "y": float(insert[1]),
                    "height": float(getattr(entity.dxf, "char_height", 2.5)),
                    "rotation": float(getattr(entity.dxf, "rotation", 0.0)),
                    "layer": str(getattr(entity.dxf, "layer", "")),
                    "handle": str(getattr(entity.dxf, "handle", "")),
                }
            )


def parse_dxf(path: Union[str, Path]) -> DxfSummary:
    dxf_path = Path(path)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    text_entities = []
    for entity in msp:
        if entity.dxftype() in {"TEXT", "MTEXT"}:
            value = entity.dxf.text if entity.dxftype() == "TEXT" else entity.text
            cleaned = _clean_dxf_text(value)
            if cleaned:
                text_entities.append(cleaned)

    dimensions: list[float] = []
    dimension_entities: list[dict[str, Any]] = []
    for dim in msp.query("DIMENSION"):
        measurement = getattr(dim.dxf, "actual_measurement", None)
        if measurement is not None:
            dimensions.append(float(measurement))
        dimension_entities.append(_dimension_detail(dim, source="modelspace"))

    entity_counts: dict[str, int] = {}
    geometry: dict[str, list[dict[str, Any]]] = {
        "lines": [],
        "circles": [],
        "arcs": [],
        "polylines": [],
        "texts": [],
    }
    raw_entities: list[dict[str, Any]] = []
    raw_virtual_entities: list[dict[str, Any]] = []
    hatch_entities: list[dict[str, Any]] = []
    virtual_entity_counts: dict[str, int] = {}
    for entity in msp:
        t = entity.dxftype()
        entity_counts[t] = entity_counts.get(t, 0) + 1
        raw_entities.append(_entity_raw(entity, source="modelspace"))
        if t == "HATCH":
            hatch_entities.append(_hatch_detail(entity, source="modelspace"))
        _collect_geometry(entity, geometry)
        if t == "INSERT":
            try:
                for virtual in entity.virtual_entities():
                    vt = virtual.dxftype()
                    virtual_entity_counts[vt] = virtual_entity_counts.get(vt, 0) + 1
                    raw_virtual_entities.append(
                        _entity_raw(virtual, source=f"virtual:{getattr(entity.dxf, 'name', '')}")
                    )
                    if vt == "HATCH":
                        hatch_entities.append(
                            _hatch_detail(virtual, source=f"virtual:{getattr(entity.dxf, 'name', '')}")
                        )
                    _collect_geometry(virtual, geometry)
            except Exception:
                # Some INSERT blocks may fail virtual expansion; continue with other entities.
                pass

    layers = sorted({layer.dxf.name for layer in doc.layers})
    insunits = int(doc.header.get("$INSUNITS", 0))
    units = UNITS_MAP.get(insunits, f"code_{insunits}")

    extmin = doc.header.get("$EXTMIN")
    extmax = doc.header.get("$EXTMAX")
    bbox = None
    if extmin and extmax:
        bbox = {
            "min_x": float(extmin[0]),
            "min_y": float(extmin[1]),
            "max_x": float(extmax[0]),
            "max_y": float(extmax[1]),
            "width": float(extmax[0] - extmin[0]),
            "height": float(extmax[1] - extmin[1]),
        }

    blocks = _collect_blocks(doc)
    title_guess = _guess_title(blocks, text_entities, dxf_path.stem)
    designation_guess = _guess_designation(text_entities, dxf_path.stem)
    feature_collection = convert_dxf_to_feature_collection(str(dxf_path))
    geometry_counts = {key: len(value) for key, value in geometry.items()}
    coverage = {
        "modelspace_entity_counts": entity_counts,
        "virtual_entity_counts": virtual_entity_counts,
        "geometry_counts": geometry_counts,
        "feature_collection_count": len(feature_collection.get("features", [])),
        "raw_entity_count": len(raw_entities),
        "raw_virtual_entity_count": len(raw_virtual_entities),
        "dimension_entity_count": len(dimension_entities),
        "hatch_entity_count": len(hatch_entities),
        "notes": [
            "geometry is normalized for downstream processing",
            "raw_entities/raw_virtual_entities preserve parsed DXF attributes for audit",
            "curves such as SPLINE/ELLIPSE may be flattened in geometry/feature_collection",
        ],
    }

    return DxfSummary(
        file_name=dxf_path.name,
        designation_guess=designation_guess,
        title_guess=title_guess,
        units=units,
        entity_counts=entity_counts,
        dimensions=sorted(dimensions)[:200],
        layers=layers[:200],
        bounding_box=bbox,
        extracted_texts=text_entities[:400],
        geometry={
            "lines": geometry["lines"][:30000],
            "circles": geometry["circles"][:10000],
            "arcs": geometry["arcs"][:10000],
            "polylines": geometry["polylines"][:10000],
            "texts": geometry["texts"][:5000],
        },
        feature_collection=feature_collection,
        raw_entities=raw_entities,
        raw_virtual_entities=raw_virtual_entities,
        blocks=blocks,
        dimension_entities=dimension_entities,
        hatch_entities=hatch_entities,
        conversion_coverage=coverage,
    )
