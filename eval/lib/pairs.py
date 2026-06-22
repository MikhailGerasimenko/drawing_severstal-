from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

PASSPORT_SUFFIXES = (".md", ".json", ".txt", ".docx")
DESIGNATION_KEY_RE = re.compile(r"\b(\d{1,4}(?:-\d+){1,4})\b")


@dataclass(frozen=True)
class GoldenPair:
    case_id: str
    drawing: Path
    passport: Path
    notes: str = ""


def _designation_key(name: str) -> str | None:
    match = DESIGNATION_KEY_RE.search(name)
    return match.group(1) if match else None


def _drawing_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith(".dxf"):
            files.append(path)
            continue
        if "dxf" in lower and not lower.endswith(".docx"):
            files.append(path)
    return files


def _passport_files(folder: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".json", ".txt", ".docx"}:
            continue
        if path.suffix.lower() == ".docx" and not path.name.lower().startswith("паспорт"):
            continue
        key = _designation_key(path.stem)
        if key:
            result[key] = path
    return result


def discover_mixed_folder(folder: Path) -> list[GoldenPair]:
    passports = _passport_files(folder)
    pairs: list[GoldenPair] = []
    for drawing in _drawing_files(folder):
        key = _designation_key(drawing.stem)
        if not key or key not in passports:
            continue
        pairs.append(
            GoldenPair(
                case_id=key,
                drawing=drawing,
                passport=passports[key],
                notes=drawing.name,
            )
        )
    return pairs


def _passport_for_stem(passports_dir: Path, stem: str) -> Path | None:
    for suffix in PASSPORT_SUFFIXES:
        candidate = passports_dir / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def discover_pairs(golden_dir: Path) -> list[GoldenPair]:
    manifest = golden_dir / "manifest.json"
    if manifest.is_file():
        return _pairs_from_manifest(golden_dir, manifest)

    mixed = discover_mixed_folder(golden_dir)
    if mixed:
        return mixed

    drawings_dir = golden_dir / "drawings"
    passports_dir = golden_dir / "passports"
    if not drawings_dir.is_dir():
        return []

    pairs: list[GoldenPair] = []
    for drawing in sorted(drawings_dir.glob("*.dxf")):
        passport = _passport_for_stem(passports_dir, drawing.stem)
        if passport is None:
            continue
        pairs.append(GoldenPair(case_id=drawing.stem, drawing=drawing, passport=passport))
    return pairs


def _pairs_from_manifest(golden_dir: Path, manifest: Path) -> list[GoldenPair]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    pairs: list[GoldenPair] = []
    for item in payload.get("pairs", []):
        drawing = golden_dir / item["drawing"]
        passport = golden_dir / item["passport"]
        if not drawing.is_file() or not passport.is_file():
            continue
        pairs.append(
            GoldenPair(
                case_id=str(item.get("id") or drawing.stem),
                drawing=drawing,
                passport=passport,
                notes=str(item.get("notes") or ""),
            )
        )
    return pairs
