import math
from pathlib import Path
from typing import Any


def _read_pairs(path: str) -> list[tuple[str, str]]:
    lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    pairs: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(lines):
        pairs.append((lines[i].strip(), lines[i + 1].rstrip("\n")))
        i += 2
    return pairs


def _entity_segments(pairs: list[tuple[str, str]]) -> list[tuple[str, list[tuple[str, str]]]]:
    entities: list[tuple[str, list[tuple[str, str]]]] = []
    in_entities = False
    i = 0
    while i < len(pairs):
        code, value = pairs[i]
        if code == "0" and value == "SECTION":
            if i + 1 < len(pairs) and pairs[i + 1] == ("2", "ENTITIES"):
                in_entities = True
                i += 2
                continue
        if in_entities and code == "0" and value == "ENDSEC":
            break
        if not in_entities:
            i += 1
            continue
        if code == "0":
            etype = value
            data: list[tuple[str, str]] = []
            i += 1
            while i < len(pairs) and pairs[i][0] != "0":
                data.append(pairs[i])
                i += 1
            entities.append((etype, data))
            continue
        i += 1
    return entities


def _last(tags: list[tuple[str, str]], key: str, default: str = "") -> str:
    for code, value in reversed(tags):
        if code == key:
            return value
    return default


def _all(tags: list[tuple[str, str]], key: str) -> list[str]:
    return [v for c, v in tags if c == key]


def _parse_color(tags: list[tuple[str, str]]) -> str:
    color = _last(tags, "62", "BYLAYER")
    return color


def _extract_link(tags: list[tuple[str, str]]) -> str:
    for i in range(len(tags) - 2):
        if tags[i] == ("1001", "PE_URL") and tags[i + 1][0] == "1000":
            return tags[i + 1][1]
    return ""


def _base_props(etype: str, tags: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "ENTITIES": etype,
        "LayerName": _last(tags, "8", ""),
        "Handle": _last(tags, "5", ""),
        "laCouleur": _parse_color(tags),
        "Link": _extract_link(tags),
    }


def _feature(etype: str, props: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "properties": {"ENTITIES": etype, **props}, "geometry": geometry}


def convert_dxf_to_feature_collection(dxf_path: str) -> dict[str, Any]:
    pairs = _read_pairs(dxf_path)
    entities = _entity_segments(pairs)
    features: list[dict[str, Any]] = []

    i = 0
    while i < len(entities):
        etype, tags = entities[i]
        props = _base_props(etype, tags)

        if etype == "LWPOLYLINE":
            xs = _all(tags, "10")
            ys = _all(tags, "20")
            points = [[float(x), float(y)] for x, y in zip(xs, ys)]
            closed = int(_last(tags, "70", "0") or "0") & 1 == 1
            if len(points) >= 2:
                if closed:
                    coords = points + [points[0]]
                    features.append(_feature(etype, props, {"type": "Polygon", "coordinates": [coords]}))
                else:
                    features.append(_feature(etype, props, {"type": "LineString", "coordinates": points}))

        elif etype == "LINE":
            x1, y1 = _last(tags, "10", "0"), _last(tags, "20", "0")
            x2, y2 = _last(tags, "11", "0"), _last(tags, "21", "0")
            coords = [[float(x1), float(y1)], [float(x2), float(y2)]]
            features.append(_feature(etype, props, {"type": "LineString", "coordinates": coords}))

        elif etype == "CIRCLE":
            cx, cy = float(_last(tags, "10", "0")), float(_last(tags, "20", "0"))
            r = float(_last(tags, "40", "0"))
            coords = []
            for deg in range(0, 360, 10):
                a = math.radians(deg)
                coords.append([cx + math.cos(a) * r, cy + math.sin(a) * r])
            if coords:
                coords.append(coords[0])
                features.append(_feature(etype, props, {"type": "Polygon", "coordinates": [coords]}))

        elif etype == "MTEXT":
            x, y = float(_last(tags, "10", "0")), float(_last(tags, "20", "0"))
            line1 = _last(tags, "1", "")
            chunks = _all(tags, "3")
            text = (line1 + "".join(chunks)).replace("\\P", " ")
            props["LaNote"] = text
            features.append(_feature(etype, props, {"type": "Point", "coordinates": [x, y]}))

        elif etype == "POINT":
            x, y = float(_last(tags, "10", "0")), float(_last(tags, "20", "0"))
            features.append(_feature(etype, props, {"type": "Point", "coordinates": [x, y]}))

        elif etype == "INSERT":
            x, y = float(_last(tags, "10", "0")), float(_last(tags, "20", "0"))
            props["leBloc"] = _last(tags, "2", "")
            j = i + 1
            while j < len(entities) and entities[j][0] == "ATTRIB":
                _, atags = entities[j]
                key = _last(atags, "2", "")
                value = _last(atags, "1", "")
                if key:
                    props[key] = value
                j += 1
            features.append(_feature(etype, props, {"type": "Point", "coordinates": [x, y]}))
            i = j
            continue

        i += 1

    return {"type": "FeatureCollection", "name": "DXF2JSON", "features": features}
