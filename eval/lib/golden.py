from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from .compare import PassportFields, normalize_text


SECTION_HEADERS = {
    "geometry": re.compile(r"(?:^|\n)(?:#+\s*)?2\.\s*ГЕОМЕТРИЯ", re.IGNORECASE | re.MULTILINE),
    "gdt": re.compile(r"(?:^|\n)(?:#+\s*)?3\.\s*ГДТ", re.IGNORECASE | re.MULTILINE),
    "notes": re.compile(r"(?:^|\n)(?:#+\s*)?4\.\s*ПРИМЕЧАНИЯ", re.IGNORECASE | re.MULTILINE),
}

FIELD_PATTERNS = {
    "part_type": re.compile(
        r"(?:^|\n)\s*[-*]?\s*Тип:\s*(.+?)(?=\n\s*[-*]?\s*Обозначение:|\n#+\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "designation": re.compile(
        r"(?:^|\n)\s*[-*]?\s*Обозначение:\s*(.+?)(?=\n\s*[-*]?\s*Габариты|\n\s*[-*]?\s*Материал|\n#+\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "overall_dimensions": re.compile(
        r"(?:^|\n)\s*[-*]?\s*Габариты\s*\(?(?:Макс)?\)?:\s*(.+?)(?=\n\s*[-*]?\s*Материал|\n#|\s*2\.\s*ГЕОМЕТРИЯ|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "material_hardness": re.compile(
        r"(?:^|\n)\s*[-*]?\s*Материал\s*/?\s*Твердость:\s*(.+?)(?=\n#+\s|\s*2\.\s*ГЕОМЕТРИЯ|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
}

GEOMETRY_SUBSECTIONS = {
    "outer_geometry": re.compile(
        r"(?:^|\n)\s*Наружный\s+контур\s*:?\s*(.+?)(?=\n\s*(?:Внутренняя\s+система|Спец\.?\s*элементы|3\.\s*ГДТ)\b|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "inner_geometry": re.compile(
        r"(?:^|\n)\s*Внутренняя\s+система\s*:?\s*(.+?)(?=\n\s*(?:Спец\.?\s*элементы|3\.\s*ГДТ)\b|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "special_elements": re.compile(
        r"(?:^|\n)\s*Спец\.?\s*элементы\s*:?\s*(.+?)(?=\n\s*3\.\s*ГДТ\b|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
}


def parse_passport_markdown(text: str) -> PassportFields:
    return _from_text(text)


def load_golden_passport(path: Path) -> PassportFields:
    if path.suffix.lower() == ".json":
        return _from_json(path)
    if path.suffix.lower() == ".docx":
        return _from_text(_docx_to_text(path))
    return _from_text(path.read_text(encoding="utf-8"))


def _docx_to_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    paragraphs = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.DOTALL)
    lines: list[str] = []
    for paragraph in paragraphs:
        parts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", paragraph)
        if parts:
            lines.append("".join(parts))
    return "\n".join(lines)


def _from_json(path: Path) -> PassportFields:
    payload = json.loads(path.read_text(encoding="utf-8"))

    def field_value(key: str) -> str:
        raw = payload.get(key)
        if isinstance(raw, dict):
            return str(raw.get("value") or "").strip()
        return str(raw or "").strip()

    return PassportFields(
        part_type=field_value("part_type"),
        designation=field_value("designation"),
        overall_dimensions=field_value("overall_dimensions"),
        material_hardness=field_value("material_hardness"),
        outer_geometry=field_value("outer_geometry"),
        inner_geometry=field_value("inner_geometry"),
        special_elements=field_value("special_elements"),
        gdt=field_value("gdt"),
        notes=str(payload.get("notes") or "").strip(),
        raw_text=json.dumps(payload, ensure_ascii=False, indent=2),
        source_format="json",
    )


def _from_text(text: str) -> PassportFields:
    fields = {key: _extract_field(text, pattern) for key, pattern in FIELD_PATTERNS.items()}
    geometry = _extract_section_raw(text, "geometry", "gdt")
    return PassportFields(
        part_type=fields["part_type"],
        designation=fields["designation"],
        overall_dimensions=fields["overall_dimensions"],
        material_hardness=fields["material_hardness"],
        outer_geometry=_geometry_subsection(geometry, "outer_geometry"),
        inner_geometry=_geometry_subsection(geometry, "inner_geometry"),
        special_elements=_geometry_subsection(geometry, "special_elements"),
        gdt=normalize_text(_extract_section_raw(text, "gdt", "notes")),
        notes=normalize_text(_extract_section_raw(text, "notes", None)),
        raw_text=text,
        source_format="markdown",
    )


def _extract_field(text: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    value = match.group(1).strip()
    value = re.sub(r"\s+", " ", value)
    return normalize_text(value[:500])


def _extract_section_raw(text: str, start_key: str, end_key: str | None) -> str:
    start = SECTION_HEADERS[start_key].search(text)
    if not start:
        return ""
    start_idx = start.end()
    end_idx = len(text)
    if end_key and end_key in SECTION_HEADERS:
        end = SECTION_HEADERS[end_key].search(text, start_idx)
        if end:
            end_idx = end.start()
    return text[start_idx:end_idx].strip()


def _geometry_subsection(geometry: str, key: str) -> str:
    if not geometry:
        return ""
    pattern = GEOMETRY_SUBSECTIONS.get(key)
    if not pattern:
        return ""
    match = pattern.search(geometry)
    if not match:
        return _subsection_legacy(geometry, _legacy_label(key))
    value = match.group(1).strip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    return normalize_text(value)


def _legacy_label(key: str) -> str:
    return {
        "outer_geometry": "Наружный контур",
        "inner_geometry": "Внутренняя система",
        "special_elements": "Спец",
    }.get(key, "")


def _subsection_legacy(geometry: str, label_prefix: str) -> str:
    lines: list[str] = []
    capture = False
    prefixes = {
        "наружный контур": ("внутренняя система", "спец"),
        "внутренняя система": ("спец", "спец.", "гдт"),
        "спец": ("гдт", "примечания", "3."),
    }
    stop_prefixes = prefixes.get(label_prefix.lower(), ())
    for line in geometry.splitlines():
        stripped = line.strip()
        lowered = stripped.lower().rstrip(":")
        if lowered.startswith(label_prefix.lower()) or lowered.startswith("спец. элементы"):
            capture = True
            continue
        if capture and any(lowered.startswith(stop) for stop in stop_prefixes):
            break
        if capture and stripped:
            lines.append(stripped)
    return normalize_text("\n".join(lines))
