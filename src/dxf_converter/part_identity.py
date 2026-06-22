import re
from pathlib import Path
from typing import Any, Optional

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
DESIGNATION_PREFIX_RE = re.compile(r"^\d{1,4}(?:-\d+){1,4}\s*-\s*", re.IGNORECASE)
COMPLEXITY_PREFIX_RE = re.compile(r"^сложность\s*\d+\s+", re.IGNORECASE)
FORMAT_GARBAGE_RE = re.compile(r"^[\d\.,;\\HhWwQq\s]{3,}")
DXF_PREFIX_RE = re.compile(r"^(?:\.\d+(?:[,.]\d+)?;)+")
DESIGNATION_RE = re.compile(
    r"^\d{1,4}(?:"
    r"/\d{2,4}(?:-\d{2})?"
    r"|"
    r"(?:-\d+){1,4}(?:-\d{2})?"
    r")$"
)
DESIGNATION_SEARCH_RE = re.compile(
    r"\b\d{1,4}/\d{2,4}(?:-\d{2})?\b"
    r"|\b\d{1,4}(?:-\d+){1,4}(?:-\d{2})?\b"
)
GOST_REFERENCE_RE = re.compile(r"^\d{4}-\d{2,4}$")
GENERIC_FILE_STEMS = frozenset({"drawing", "input", "untitled", "document", "file", "upload"})
TOLERANCE_ONLY_RE = re.compile(r"^[Tt]\s*0[,.]\d", re.IGNORECASE)
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
    "острая",
    "кромка",
    "кромке",
    "фаска",
    "фаски",
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


def is_generic_upload_name(file_name: str) -> bool:
    stem = Path(file_name).stem.strip().lower()
    return not stem or stem in GENERIC_FILE_STEMS


def is_gost_reference(value: str) -> bool:
    """Отсечь номера ГОСТ вида 5950-2000, 4543-71, 4543-2016."""
    cleaned = value.strip().replace(" ", "")
    if "/" in cleaned:
        return False
    if GOST_REFERENCE_RE.fullmatch(cleaned):
        return True
    parts = cleaned.split("-")
    if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 4:
        return True
    if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) <= 3:
        return True
    return False


def _normalize_designation_token(value: str) -> str:
    return value.strip().replace(" ", "")


def _designation_candidates_from_texts(cleaned_texts: list[str]) -> set[str]:
    candidates: set[str] = set()
    for text in cleaned_texts:
        compact = _normalize_designation_token(text)
        if DESIGNATION_RE.fullmatch(compact) and not is_gost_reference(compact):
            candidates.add(compact)
        for match in DESIGNATION_SEARCH_RE.findall(text):
            candidate = _normalize_designation_token(match)
            if DESIGNATION_RE.fullmatch(candidate) and not is_gost_reference(candidate):
                candidates.add(candidate)
    return candidates


def _block_has_product_name(cleaned_texts: list[str]) -> bool:
    return any(_is_stamp_product_name(text) for text in cleaned_texts)


def _designation_score(
    value: str,
    *,
    marker_hits: int,
    block_name: str,
    has_product_name: bool = False,
    near_label: bool = False,
) -> int:
    score = len(value) * 3
    if "/" in value:
        score += 40
    parts = value.replace("/", "-").split("-")
    score += len(parts) * 15
    if block_name.upper().startswith("U"):
        score += 50
    score += marker_hits * 10
    if has_product_name:
        score += 80
    if near_label:
        score += 60
    if len(parts) == 2 and all(part.isdigit() and len(part) <= 2 for part in parts):
        score -= 40
    if parts and parts[-1].isdigit() and len(parts[-1]) == 2 and len(parts) > 2:
        score += 5
    return score


def _near_designation_label(cleaned_texts: list[str], candidate: str) -> bool:
    for index, text in enumerate(cleaned_texts):
        if "обозначение" not in text.lower():
            continue
        window = cleaned_texts[index : index + 6]
        for item in window:
            if candidate in _normalize_designation_token(item):
                return True
    return False


def _stamp_block_texts(block: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for entity in block.get("entities") or []:
        if entity.get("type") not in {"MTEXT", "TEXT", "ATTRIB"}:
            continue
        for key in ("text", "raw_text"):
            raw = entity.get(key)
            if raw:
                texts.append(str(raw))
    return texts


def _iter_stamp_blocks(blocks: list[dict[str, Any]]):
    for block in blocks:
        texts = _stamp_block_texts(block)
        if not texts:
            continue
        cleaned_texts = [clean_dxf_markup(item) for item in texts if clean_dxf_markup(item)]
        if not cleaned_texts:
            continue
        block_blob = " ".join(cleaned_texts).lower()
        marker_hits = sum(1 for marker in STAMP_MARKERS if marker in block_blob)
        name = str(block.get("name") or "")
        has_product = _block_has_product_name(cleaned_texts)
        is_title_block = name.upper().startswith("U")
        if not is_title_block:
            continue
        if marker_hits >= 2 or has_product:
            yield block, cleaned_texts, marker_hits, has_product


def derive_base_designation(value: str) -> Optional[str]:
    """Сократить обозначение вида 07-55-42-2 → 42-2 (код изделия без кода документа)."""
    parts = value.strip().split("-")
    if len(parts) < 4:
        return None
    if len(parts[0]) > 2 or len(parts[1]) > 2 or len(parts[2]) > 2:
        return None
    base = "-".join(parts[2:])
    if DESIGNATION_RE.fullmatch(base):
        return base
    return None


def _combined_product_name_from_block(cleaned_texts: list[str]) -> Optional[str]:
    ordered: list[str] = []
    for text in cleaned_texts:
        candidate = _normalize_part_type(text)
        if _is_stamp_product_name(candidate) and candidate not in ordered:
            ordered.append(candidate)
    if len(ordered) >= 2:
        return " ".join(ordered[:4])
    if ordered:
        return ordered[0]
    return None


def extract_designation_from_stamp(blocks: list[dict[str, Any]]) -> Optional[tuple[str, str]]:
    """Извлечь обозначение изделия из блока штампа (основной надписи)."""
    best: Optional[tuple[str, str, int]] = None

    for block, cleaned_texts, marker_hits, has_product in _iter_stamp_blocks(blocks):
        name = str(block.get("name") or "")
        candidates = _designation_candidates_from_texts(cleaned_texts)

        for candidate in candidates:
            score = _designation_score(
                candidate,
                marker_hits=marker_hits,
                block_name=name,
                has_product_name=has_product,
                near_label=_near_designation_label(cleaned_texts, candidate),
            )
            evidence = f"dxf_stamp:block:{name}"
            if best is None or score > best[2]:
                best = (candidate, evidence, score)

    if best:
        value, evidence, _score = best
        base = derive_base_designation(value)
        if base:
            return base, f"{evidence}:base"
        return value, evidence
    return None


def _best_designation_from_texts(texts: list[str]) -> Optional[tuple[str, str, int]]:
    best: Optional[tuple[str, str, int]] = None
    for text in texts:
        if TOLERANCE_ONLY_RE.match(text.strip()) and "/" not in text and "-" not in text:
            continue
        for candidate in _designation_candidates_from_texts([text]):
            score = _designation_score(candidate, marker_hits=0, block_name="")
            if best is None or score > best[2]:
                best = (candidate, text, score)
    return best


def extract_part_type_from_stamp(blocks: list[dict[str, Any]]) -> Optional[tuple[str, str]]:
    """Извлечь наименование изделия из блока штампа (основной надписи)."""
    best: Optional[tuple[str, str, int]] = None

    for block, cleaned_texts, marker_hits, _has_product in _iter_stamp_blocks(blocks):
        name = str(block.get("name") or "")
        combined = _combined_product_name_from_block(cleaned_texts)
        if not combined:
            continue
        score = len(combined) + marker_hits * 10
        if name.upper().startswith("U"):
            score += 50
        if " " in combined:
            score += 40
        evidence = f"dxf_stamp:block:{name}"
        if best is None or score > best[2]:
            best = (combined, evidence, score)

    if best:
        return best[0], best[1]
    return None


def parse_part_type_from_filename(file_name: str) -> Optional[str]:
    """Fallback: тип из имени файла."""
    if is_generic_upload_name(file_name):
        return None

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


def pick_designation(
    *,
    file_name: str,
    text_evidence: Optional[list[str]] = None,
    blocks: Optional[list[dict[str, Any]]] = None,
    designation_guess: Optional[str] = None,
) -> tuple[str, str, list[str]]:
    """Вернуть (designation, confidence, evidence). Приоритет: штамп DXF → guess → тексты → имя файла."""
    if blocks:
        stamp = extract_designation_from_stamp(blocks)
        if stamp:
            return stamp[0], "high", [stamp[1]]

    if designation_guess and not is_gost_reference(designation_guess):
        return designation_guess, "high", [designation_guess]

    best_text = _best_designation_from_texts(text_evidence or [])
    if best_text:
        return best_text[0], "medium", [best_text[1]]

    if not is_generic_upload_name(file_name):
        stem = Path(file_name).stem.strip()
        match = DESIGNATION_SEARCH_RE.search(stem)
        if match and not is_gost_reference(match.group(0)):
            return match.group(0), "low", [f"file_name_fallback:{file_name}"]

    return "Не указано в чертеже", "low", []
