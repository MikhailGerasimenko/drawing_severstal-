"""Тесты eval: парсер markdown и смысловое сравнение."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from lib.golden import parse_passport_markdown
from lib.semantic_compare import compare_passports_semantic
from lib.compare import PassportFields


GENERATED_SAMPLE = """# Паспорт изделия

## 1. ОБЩИЕ ДАННЫЕ
- Тип: Фланец
- Обозначение: 07-54-105
- Габариты (Макс): ∅70e8 x 105
- Материал/Твердость: Сталь 6ХВ2С ГОСТ 5950-2000 / 40...45 HRC.

## 2. ГЕОМЕТРИЯ (ЧИСТОВАЯ)
Наружный контур:
- ∅70e8(-0,060-0,106)

Внутренняя система:
- ∅8H11(+0,09)

Спец. элементы:
- 3 отверстия ∅8H11

## 3. ГДТ
- Шероховатость: Ra 0,80, Ra 1,6, Ra 3,2
- Допуск формы: 0,03 мм относительно ∅70e8

## 4. ПРИМЕЧАНИЯ
- Маркировать ударным способом
- H14, h14, IT14
"""


def test_parse_generated_markdown_sections_with_double_hash():
    passport = parse_passport_markdown(GENERATED_SAMPLE)
    assert passport.part_type == "фланец"
    assert passport.designation == "07-54-105"
    assert "ra 0,80" in passport.gdt
    assert "0,03" in passport.gdt
    assert "маркировать" in passport.notes


def test_semantic_compare_gdt_recognizes_key_facts():
    expected = PassportFields(
        gdt="полное радиальное биение ø70e8 не более 0,03 мм шероховатость ra 0,80 ra 1,6 ra 3,2",
        part_type="Фланец",
        designation="07-54-105",
    )
    actual = PassportFields(
        gdt="шероховатость ra 0,80 ra 1,6 ra 3,2 допуск формы 0,03 мм",
        part_type="Фланец",
        designation="07-54-105",
    )
    report = compare_passports_semantic(expected, actual)
    scores = {item.name: item.score for item in report.fields}
    assert scores["part_type"] == 1.0
    assert scores["designation"] == 1.0
    assert scores["gdt"] >= 0.6
