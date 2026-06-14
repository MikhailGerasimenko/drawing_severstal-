import re
from pathlib import Path
from typing import Any, Optional

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
DESIGNATION_PREFIX_RE = re.compile(r"^\d{1,4}(?:-\d+){1,4}\s*-\s*", re.IGNORECASE)
COMPLEXITY_PREFIX_RE = re.compile(r"^сложность\s*\d+\s+", re.IGNORECASE)
FORMAT_GARBAGE_RE = re.compile(r"^[\d\.,;\\HhWwQq\s]{3,}")
DXF_PREFIX_RE = re.compile(r"^(?:\.\d+(?:[,.]\d+)?;)+")
DESIGNATION_RE = re.compile(r"^\d{1,4}(?:-\d+){1,4}(?:-\d{2})?$")
MATERIAL_MARKERS_RE = re.compile(
    r"(сталь|гост|hrc|маркир|тверд|твёрд|фаск|отв\.|паз|рад\.|кромк|диаметр|металл|табл|шуруп|сирия|бирке)",
    re.IGNORECASE,
)

STAMP_MARKERS = {
    "утв.",
    "обозначение",
    "масштаб",
    "разраб.",
    "н.контр.",
    "т.контр.",
    "листов",
}

STAMP_NOISE = {
    "изм.",
    "лист",
    "листов",
    "№ докум.",
    "подп.",
    "дата",
    "лит.",
    "разраб.",
    "пров.",
    "т.контр.",
    "н.контр.",
    "утв.",
    "зам.",
    "масштаб",
    "масса",
    "формат",
    "копировал",
    "инв. № подл.",
    "инв. № дубл.",
    "подп. и дата",
    "взам. инв. №",
    "справ. №",
    "перв. примен.",
    "обозначение",
    "см. табл",
}


def clean_dxf_markup(text: str) -> str:
    value = str(text).replace("\\P", "\n")
    value = re.sub(r"\{\\.*?;([^}]*)\}", r"\1", value)
    value = re.sub(r"\\[A-Za-z0-9]+;?", "", value)
    value = DXF_PREFIX_RE.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def is_garbage_title(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 3:
        return True
    if not CYRILLIC_RE.search(cleaned):
        return True
    if FORMAT_GARBAGE_RE.match(cleaned) and len(cleaned) < 12:
        return True
    if re.fullmatch(r"[\d\.,;\\]+", cleaned):
        return True
    return False


def _normalize_part_type(value: str) -> str:
    part = COMPLEXITY_PREFIX_RE.sub("", value.strip())
    part = part.strip(" -–—()")
    return part


def _is_stamp_product_name(text: str) -> bool:
    cleaned = _normalize_part_type(clean_dxf_markup(text))
    if not cleaned or is_garbage_title(cleaned):
        return False
    lowered = cleaned.lower()
    if lowered in STAMP_NOISE:
        return False
    if MATERIAL_MARKERS_RE.search(cleaned):
        return False
    if DESIGNATION_RE.fullmatch(cleaned.replace(" ", "")):
        return False
    if re.search(r"\d", cleaned):
        return False
    if re.fullmatch(r"[А-Яа-яЁё][А-Яа-яЁё\-]{2,40}", cleaned):
        return True
    return False


def extract_part_type_from_stamp(blocks: list[dict[str, Any]]) -> Optional[tuple[str, str]]:
    """Извлечь наименование изделия из блока штампа (основной надписи)."""
    best: Optional[tuple[str, str, int]] = None

    for block in blocks:
        name = str(block.get("name") or "")
        entities = block.get("entities") or []
        texts: list[str] = []
        for entity in entities:
            if entity.get("type") not in {"MTEXT", "TEXT", "ATTRIB"}:
                continue
            for key in ("text", "raw_text"):
                raw = entity.get(key)
                if raw:
                    texts.append(str(raw))

        if not texts:
            continue

        cleaned_texts = [clean_dxf_markup(item) for item in texts if clean_dxf_markup(item)]
        block_blob = " ".join(cleaned_texts).lower()
        marker_hits = sum(1 for marker in STAMP_MARKERS if marker in block_blob)
        if marker_hits < 2:
            continue

        for raw in texts:
            candidate = clean_dxf_markup(raw)
            if not _is_stamp_product_name(candidate):
                continue
            score = len(candidate)
            if name.upper().startswith("U"):
                score += 50
            score += marker_hits * 10
            evidence = f"dxf_stamp:block:{name}"
            if best is None or score > best[2]:
                best = (_normalize_part_type(candidate), evidence, score)

    if best:
        return best[0], best[1]
    return None


def parse_part_type_from_filename(file_name: str) -> Optional[str]:
    """Fallback: тип из имени файла."""
    stem = Path(file_name).stem.strip()
    if not stem:
        return None

    match = re.match(
        r"^(?:\d{1,4}(?:-\d+){1,4})\s*-\s*(?:сложность\s*\d+\s+)?(?P<type>.+)$",
        stem,
        flags=re.IGNORECASE,
    )
    if match:
        part_type = _normalize_part_type(match.group("type"))
        if part_type and not is_garbage_title(part_type):
            return part_type

    generic = re.match(r"^.+?\s*-\s*(?P<type>.+)$", stem)
    if generic:
        part_type = _normalize_part_type(generic.group("type"))
        if part_type and CYRILLIC_RE.search(part_type) and not is_garbage_title(part_type):
            return part_type

    if CYRILLIC_RE.search(stem) and not re.match(r"^\d", stem) and not is_garbage_title(stem):
        return stem

    return None


def pick_part_type(
    *,
    file_name: str,
    title_guess: Optional[str] = None,
    text_evidence: Optional[list[str]] = None,
    blocks: Optional[list[dict[str, Any]]] = None,
    stamp_part_type: Optional[str] = None,
    stamp_evidence: Optional[str] = None,
) -> tuple[str, str, list[str]]:
    """Вернуть (part_type, confidence, evidence). Приоритет: штамп DXF → тексты → имя файла."""
    if stamp_part_type and not is_garbage_title(stamp_part_type):
        return stamp_part_type, "high", [stamp_evidence or "dxf_stamp"]

    if blocks:
        stamp = extract_part_type_from_stamp(blocks)
        if stamp:
            return stamp[0], "high", [stamp[1]]

    if title_guess and not is_garbage_title(title_guess):
        cleaned = _normalize_part_type(clean_dxf_markup(title_guess))
        if cleaned and _is_stamp_product_name(cleaned):
            return cleaned, "high", [f"dxf_title:{title_guess}"]

    for text in text_evidence or []:
        cleaned = _normalize_part_type(clean_dxf_markup(text))
        if _is_stamp_product_name(cleaned):
            return cleaned, "medium", [cleaned]

    from_filename = parse_part_type_from_filename(file_name)
    if from_filename:
        return from_filename, "low", [f"file_name_fallback:{file_name}"]

    return "Не указано в чертеже", "low", []
