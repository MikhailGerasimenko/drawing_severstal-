"""Регрессии для сценария интеграции: файл всегда загружается как drawing.dxf."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from dxf_converter.input_router import load_dxf
from dxf_converter.part_identity import is_gost_reference, pick_designation

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"

EXPECTED = {
    "42-2 - Штифтодержатель.dxf": {"designation": "42-2", "part_type": "Штифтодержатель"},
    "07-54-105 - сложность 3 Фланец.dxf": {"designation": "07-54-105", "part_type": "Фланец"},
    "07-54-511 - сложность 1 Компенсатор.dxf": {"designation": "07-54-511", "part_type": "Компенсатор"},
    "08-02-02. сложность 4.dxf": {"designation": "08-02-02", "part_type": "Ролик"},
    "22 - нож (dxf).dxf": {"designation": "22/02", "part_type": "Нож"},
}


def _load_as_drawing_upload(sample_name: str):
    src = SAMPLES_DIR / sample_name
    if not src.is_file():
        pytest.skip(f"sample missing: {sample_name}")
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "drawing.dxf"
        shutil.copy(src, dst)
        return load_dxf(dst)


@pytest.mark.parametrize("sample_name,expected", EXPECTED.items())
def test_designation_from_stamp_when_filename_is_generic(sample_name: str, expected: dict[str, str]):
    normalized = _load_as_drawing_upload(sample_name)
    designation = normalized.semantic_candidates["designation"]["value"]
    features = normalized.semantic_candidates["engineering_features"]
    part_type = features["part_type"]["value"]

    assert designation == expected["designation"]
    assert part_type == expected["part_type"]
    assert designation != "0"
    assert designation != "Не указано в чертеже"


def test_pick_designation_ignores_tolerance_tokens():
    value, confidence, evidence = pick_designation(
        file_name="drawing.dxf",
        text_evidence=["T 0,05", "Ra 0,8"],
        blocks=None,
        designation_guess=None,
    )
    assert value == "Не указано в чертеже"
    assert confidence == "low"


def test_gost_reference_filter():
    assert is_gost_reference("5950-2000")
    assert is_gost_reference("4543-71")
    assert not is_gost_reference("42-2")
    assert not is_gost_reference("22/02")
