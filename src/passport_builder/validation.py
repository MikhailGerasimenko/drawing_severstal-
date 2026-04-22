import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PLACEHOLDER = "Не указано в чертеже"


def _extract_sections(markdown: str) -> Dict[str, str]:
    pattern = re.compile(r"^##\s+(.+?)\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
    result: Dict[str, str] = {}
    for match in pattern.finditer(markdown):
        title = match.group(1).strip().lower()
        body = match.group(2).strip()
        result[title] = body
    return result


def _extract_bullets(section_text: str) -> Dict[str, str]:
    bullets: Dict[str, str] = {}
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        payload = stripped[2:]
        if ":" in payload:
            key, value = payload.split(":", 1)
            bullets[key.strip().lower()] = value.strip()
    return bullets


def _is_filled(value: Optional[str]) -> bool:
    if not value:
        return False
    return PLACEHOLDER.lower() not in value.lower()


def validate_passport(markdown: str) -> Dict[str, Any]:
    sections = _extract_sections(markdown)
    general = _extract_bullets(sections.get("1. общие данные", ""))
    geometry = _extract_bullets(sections.get("2. геометрия (чистовая)", ""))
    gdt_section = sections.get("3. гдт", "")

    checks = [
        ("product_type", general.get("тип")),
        ("designation", general.get("обозначение")),
        ("dimensions_max", general.get("габариты (макс)")),
        ("material_hardness", general.get("материал/твердость")),
        ("geometry_main_sizes", geometry.get("основные размеры")),
        ("gdt", gdt_section if gdt_section else None),
    ]

    missing: List[str] = []
    for key, value in checks:
        if not _is_filled(value):
            missing.append(key)

    return {
        "is_valid": len(missing) == 0,
        "missing_fields": missing,
        "checked_fields": [name for name, _ in checks],
    }


def build_report(
    dxf_file: str,
    passport_name: str,
    validation: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dxf_file": dxf_file,
        "passport_name": passport_name,
        "validation": validation,
        "metadata": metadata or {},
    }


def save_report(report: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
