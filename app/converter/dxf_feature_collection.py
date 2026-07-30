import math
import re
from typing import Any, Optional

import ezdxf


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _base_props(entity: Any) -> dict[str, Any]:
    return {
        "ENTITIES": entity.dxftype(),
        "LayerName": str(getattr(entity.dxf, "layer", "")),
        "Handle": str(getattr(entity.dxf, "handle", "")),
        "laCouleur": str(getattr(entity.dxf, "color", "BYLAYER")),
        "Link": "",
    }


def _extract_format_tokens(text: str) -> list[str]:
    # Keep original formatting commands as explicit metadata.
    return re.findall(r"\\[A-Za-z][^;]*;", text)


def _to_plain_text(text: str) -> str:
    plain = text.replace("\\P", "\n")
    plain = re.sub(r"\{\\.*?;([^}]*)\}", r"\1", plain)
    plain = re.sub(r"\\[A-Za-z0-9]+;?", "", plain)
    return re.sub(r"\s+", " ", plain).strip()


def _feature(props: dict[str, Any], geometry: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "Feature", "properties": props, "geometry": geometry}


def _line_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    start = entity.dxf.start
    end = entity.dxf.end
    return _feature(
        props,
        {
            "type": "LineString",
            "coordinates": [[_safe_float(start[0]), _safe_float(start[1])], [_safe_float(end[0]), _safe_float(end[1])]],
        },
    )


def _lwpolyline_feature(entity: Any, props: dict[str, Any]) -> Optional[dict[str, Any]]:
    points = [[_safe_float(x), _safe_float(y)] for x, y, *_ in entity.get_points("xy")]
    if len(points) < 2:
        return None
    if entity.closed:
        return _feature(props, {"type": "Polygon", "coordinates": [points + [points[0]]]})
    return _feature(props, {"type": "LineString", "coordinates": points})


def _polyline_feature(entity: Any, props: dict[str, Any]) -> Optional[dict[str, Any]]:
    points = [[_safe_float(v.x), _safe_float(v.y)] for v in entity.points()]
    if len(points) < 2:
        return None
    if entity.is_closed:
        return _feature(props, {"type": "Polygon", "coordinates": [points + [points[0]]]})
    return _feature(props, {"type": "LineString", "coordinates": points})


def _circle_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    center = entity.dxf.center
    cx, cy = _safe_float(center[0]), _safe_float(center[1])
    r = _safe_float(entity.dxf.radius)
    coords = []
    for deg in range(0, 360, 10):
        angle = math.radians(deg)
        coords.append([cx + math.cos(angle) * r, cy + math.sin(angle) * r])
    coords.append(coords[0])
    return _feature(props, {"type": "Polygon", "coordinates": [coords]})


def _arc_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    center = entity.dxf.center
    cx, cy = _safe_float(center[0]), _safe_float(center[1])
    r = _safe_float(entity.dxf.radius)
    start = _safe_float(entity.dxf.start_angle)
    end = _safe_float(entity.dxf.end_angle)
    if end < start:
        end += 360.0
    step = 10.0
    coords = []
    angle = start
    while angle <= end:
        rad = math.radians(angle)
        coords.append([cx + math.cos(rad) * r, cy + math.sin(rad) * r])
        angle += step
    if not coords:
        coords = [[cx, cy]]
    return _feature(props, {"type": "LineString", "coordinates": coords})


def _flattening_feature(entity: Any, props: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        points = [[_safe_float(v.x), _safe_float(v.y)] for v in entity.flattening(distance=0.5)]
    except Exception:
        return None
    if len(points) < 2:
        return None
    return _feature(props, {"type": "LineString", "coordinates": points})


def _text_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    insert = entity.dxf.insert
    raw_text = str(getattr(entity.dxf, "text", ""))
    props["LaNote"] = raw_text
    props["LaNoteRaw"] = raw_text
    props["LaNotePlain"] = _to_plain_text(raw_text)
    props["LaNoteFormatTokens"] = _extract_format_tokens(raw_text)
    return _feature(
        props,
        {"type": "Point", "coordinates": [_safe_float(insert[0]), _safe_float(insert[1])]},
    )


def _mtext_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    insert = entity.dxf.insert
    raw_text = str(getattr(entity, "text", ""))
    props["LaNote"] = raw_text.replace("\\P", " ")
    props["LaNoteRaw"] = raw_text
    props["LaNotePlain"] = _to_plain_text(raw_text)
    props["LaNoteFormatTokens"] = _extract_format_tokens(raw_text)
    return _feature(
        props,
        {"type": "Point", "coordinates": [_safe_float(insert[0]), _safe_float(insert[1])]},
    )


def _point_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    location = entity.dxf.location
    return _feature(
        props,
        {"type": "Point", "coordinates": [_safe_float(location[0]), _safe_float(location[1])]},
    )


def _insert_feature(entity: Any, props: dict[str, Any]) -> dict[str, Any]:
    insert = entity.dxf.insert
    props["leBloc"] = str(getattr(entity.dxf, "name", ""))
    for attrib in getattr(entity, "attribs", []):
        key = str(getattr(attrib.dxf, "tag", "")).strip()
        value = str(getattr(attrib.dxf, "text", "")).strip()
        if key:
            props[key] = value
    return _feature(
        props,
        {"type": "Point", "coordinates": [_safe_float(insert[0]), _safe_float(insert[1])]},
    )


def _entity_to_feature(entity: Any) -> Optional[dict[str, Any]]:
    props = _base_props(entity)
    entity_type = entity.dxftype()
    if entity_type == "LINE":
        return _line_feature(entity, props)
    if entity_type == "LWPOLYLINE":
        return _lwpolyline_feature(entity, props)
    if entity_type == "POLYLINE":
        return _polyline_feature(entity, props)
    if entity_type == "CIRCLE":
        return _circle_feature(entity, props)
    if entity_type == "ARC":
        return _arc_feature(entity, props)
    if entity_type in {"ELLIPSE", "SPLINE"}:
        return _flattening_feature(entity, props)
    if entity_type == "TEXT":
        return _text_feature(entity, props)
    if entity_type == "MTEXT":
        return _mtext_feature(entity, props)
    if entity_type == "POINT":
        return _point_feature(entity, props)
    if entity_type == "INSERT":
        return _insert_feature(entity, props)
    return None


def convert_dxf_to_feature_collection(dxf_path: str) -> dict[str, Any]:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    features: list[dict[str, Any]] = []

    for entity in msp:
        feature = _entity_to_feature(entity)
        if feature is not None:
            features.append(feature)
        if entity.dxftype() == "INSERT":
            try:
                for virtual in entity.virtual_entities():
                    v_feature = _entity_to_feature(virtual)
                    if v_feature is not None:
                        features.append(v_feature)
            except Exception:
                pass

    return {"type": "FeatureCollection", "name": "DXF2JSON", "features": features}
