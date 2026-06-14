from typing import Any

from .models import NormalizedDrawing


def _candidate_value(semantic: dict[str, Any], key: str) -> str:
    value = semantic.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value") or "Не указано в чертеже")
    return "Не указано в чертеже"


def _product_name(semantic: dict[str, Any]) -> str:
    value = _candidate_value(semantic, "product_name")
    designation = _candidate_value(semantic, "designation")
    prefix = f"{designation} - "
    if value.startswith(prefix):
        return value[len(prefix):].strip()
    return value


def _part_type(semantic: dict[str, Any], features: dict[str, Any]) -> str:
    part = features.get("part_type", {}) if isinstance(features, dict) else {}
    if isinstance(part, dict) and part.get("value"):
        return str(part["value"])
    return _product_name(semantic)


def _format_value(value: Any) -> str:
    if value is None:
        return "Не указано"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(f"{key}: {_format_value(item)}")
        return "; ".join(parts)
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value)
    return str(value)


def _fact_line(fact: dict[str, Any]) -> str:
    label = fact.get("label") or fact.get("type") or "Факт"
    value = _format_value(fact.get("value"))
    confidence = fact.get("confidence")
    note = fact.get("note")
    suffix = []
    if confidence:
        suffix.append(f"confidence: {confidence}")
    if note:
        suffix.append(f"note: {note}")
    tail = f" ({'; '.join(suffix)})" if suffix else ""
    return f"- **{label}**: {value}{tail}"


def _fact_section(title: str, facts: Any, *, empty: str = "Нет классифицированных фактов.") -> list[str]:
    lines = [f"## {title}"]
    if not facts:
        lines.append(empty)
        return lines
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict):
                lines.append(_fact_line(fact))
            else:
                lines.append(f"- {_format_value(fact)}")
        return lines
    if isinstance(facts, dict):
        for key, value in facts.items():
            lines.append(f"- **{key}**: {_format_value(value)}")
        return lines
    lines.append(_format_value(facts))
    return lines


def _dedupe_facts(facts: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for fact in facts:
        value = _format_value(fact.get("value"))
        key = f"{fact.get('type')}::{value}"
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
        if len(result) >= limit:
            break
    return result


def render_llm_markdown_context(normalized: NormalizedDrawing) -> str:
    """Render a compact engineering-focused context for LLM passport generation."""
    semantic = normalized.semantic_candidates or {}
    features = semantic.get("engineering_features", {}) if isinstance(semantic, dict) else {}
    audit = semantic.get("extraction_audit", {}) if isinstance(semantic, dict) else {}
    gate = semantic.get("validation_gate", {}) if isinstance(semantic, dict) else {}
    drawing_facts = normalized.drawing_facts or {}
    overall = features.get("overall", {}) if isinstance(features, dict) else {}
    overall_display = overall.get("display") or _candidate_value(semantic, "overall_dimensions")

    lines: list[str] = [
        "# LLM Engineering Context",
        "",
        "Этот Markdown является компактной инженерной выжимкой из normalized JSON.",
        "Используй его как основной источник фактов для паспорта изделия.",
        "Не используй bounding_box как габарит детали и не меняй типы классифицированных размеров.",
        "",
        "## Source",
        f"- **input_type**: {normalized.source.input_type}",
        f"- **file_name**: {normalized.source.file_name}",
        f"- **units**: {drawing_facts.get('units', 'Не указано')}",
        "",
        "## Product Identity",
        f"- **part_type**: {_part_type(semantic, features)}",
        f"- **product_name**: {_product_name(semantic)}",
        f"- **designation**: {_candidate_value(semantic, 'designation')}",
        f"- **overall_dimensions**: {overall_display}",
        f"- **material_hardness**: {_candidate_value(semantic, 'material_hardness')}",
        "",
        "## Validation Gate",
        f"- **status**: {gate.get('status', 'unknown')}",
        f"- **ready_for_llm**: {gate.get('ready_for_llm', 'unknown')}",
        f"- **errors**: {_format_value(gate.get('errors', [])) or 'нет'}",
        f"- **warnings**: {_format_value(gate.get('warnings', [])) or 'нет'}",
        "",
        "## Required Interpretation Rules",
    ]

    for rule in features.get("llm_interpretation_rules", []) or gate.get("required_checks", []):
        lines.append(f"- {rule}")
    if not (features.get("llm_interpretation_rules") or gate.get("required_checks")):
        lines.append("- Не выдумывать неподтвержденные размеры, посадки, ГДТ и материал.")

    lines.extend(["", *_fact_section("Overall", features.get("overall", {})), ""])
    lines.extend(_fact_section("External Contour", features.get("external_contour", [])))
    lines.append("")
    lines.extend(_fact_section("Internal System", features.get("internal_system", [])))
    lines.append("")
    lines.extend(_fact_section("Special Elements", features.get("special_elements", [])))
    lines.append("")
    gdt = features.get("gdt", [])
    if isinstance(gdt, list):
        gdt = _dedupe_facts([item for item in gdt if isinstance(item, dict)], limit=20)
    lines.extend(_fact_section("GDT", gdt, empty="ГДТ не классифицировано."))
    lines.append("")

    tech = features.get("technical_requirements", [])
    if isinstance(tech, list):
        tech = _dedupe_facts([item for item in tech if isinstance(item, dict)], limit=30)
    lines.extend(_fact_section("Technical Requirements", tech, empty="Технические требования не найдены."))
    lines.append("")

    lines.extend(
        [
            "## Extraction Audit",
            f"- **dimension_texts_total**: {audit.get('dimension_texts_total', 0)}",
            f"- **classified_total**: {audit.get('classified_total', 0)}",
            f"- **unclassified_total**: {audit.get('unclassified_total', 0)}",
        ]
    )

    critical = audit.get("critical_unclassified", [])
    if critical:
        lines.append("- **critical_unclassified**:")
        for item in critical[:50]:
            lines.append(f"  - {_format_value(item)}")
    else:
        lines.append("- **critical_unclassified**: нет")

    explicit_dimensions = features.get("explicit_dimensions", [])
    if explicit_dimensions:
        lines.extend(["", "## Explicit Dimension Tokens"])
        for item in explicit_dimensions[:80]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('value')} (source: {item.get('source', {}).get('raw', '')})")
            else:
                lines.append(f"- {_format_value(item)}")

    notes = semantic.get("notes_facts", []) if isinstance(semantic, dict) else []
    if notes:
        lines.extend(["", "## Source Notes Fragment"])
        seen_notes: set[str] = set()
        for note in notes[:80]:
            if note in seen_notes:
                continue
            seen_notes.add(str(note))
            lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "## Output Task For LLM",
            "Сформируй паспорт изделия в Markdown по этому контексту.",
            "Поле `part_type` — обязательный источник для строки «Тип» в разделе 1; не подставляй туда обозначение.",
            "Если `Validation Gate` содержит warnings/errors или есть `critical_unclassified`, не превращай сомнения в утверждения.",
            "Если факт есть только как low confidence или candidate, формулируй осторожно: `признаки присутствуют`, `требует проверки по чертежу`.",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"
