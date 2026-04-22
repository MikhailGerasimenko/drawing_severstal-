import re
from pathlib import Path
from typing import Any, Optional, Union

import ezdxf

from .dxf_feature_collection import convert_dxf_to_feature_collection
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


def _guess_title(texts: list[str], file_stem: str) -> Optional[str]:
    priority = [t for t in texts if any(ch.isalpha() for ch in t) and len(t) > 4]
    if priority:
        return priority[0]
    return file_stem


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
    for dim in msp.query("DIMENSION"):
        measurement = getattr(dim.dxf, "actual_measurement", None)
        if measurement is not None:
            dimensions.append(float(measurement))

    entity_counts: dict[str, int] = {}
    geometry: dict[str, list[dict[str, Any]]] = {
        "lines": [],
        "circles": [],
        "arcs": [],
        "polylines": [],
        "texts": [],
    }
    for entity in msp:
        t = entity.dxftype()
        entity_counts[t] = entity_counts.get(t, 0) + 1
        _collect_geometry(entity, geometry)
        if t == "INSERT":
            try:
                for virtual in entity.virtual_entities():
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

    title_guess = _guess_title(text_entities, dxf_path.stem)
    designation_guess = _guess_designation(text_entities, dxf_path.stem)

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
        feature_collection=convert_dxf_to_feature_collection(str(dxf_path)),
    )
