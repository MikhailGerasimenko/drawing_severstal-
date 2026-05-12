from .models import NormalizedDrawing


SYSTEM_PROMPT = """Ты инженер-конструктор и технический писатель.
Сформируй паспорт изделия по нормализованным данным чертежа.
Не выдумывай критичные параметры: если данных нет, помечай "Не указано в чертеже".
Сначала используй semantic_candidates.engineering_features и validation_gate, затем explicit_dimensions, и только потом сырую геометрию.
Никогда не меняй тип классифицированного размера: pitch_diameter не является central_hole, keyway не является отверстием.
Если semantic_candidates.extraction_audit.critical_unclassified не пустой, не скрывай эти размеры: включи их как "требует проверки" или не используй без подтверждения.
Геометрические диаметры из inferred_geometry считаются слабой подсказкой и не дают права добавлять посадки/допуски.
Соблюдай структуру и нумерацию разделов:
1. ОБЩИЕ ДАННЫЕ
2. ГЕОМЕТРИЯ (ЧИСТОВАЯ)
3. ГДТ
4. ПРИМЕЧАНИЯ

Верни ответ строго в Markdown.
"""


def build_user_prompt(normalized: NormalizedDrawing, reference_passport_text: str) -> str:
    source = normalized.source
    drawing_facts = normalized.drawing_facts
    semantic = normalized.semantic_candidates
    engineering_features = semantic.get("engineering_features", {})
    extraction_audit = semantic.get("extraction_audit", {})
    validation_gate = semantic.get("validation_gate", {})
    return f"""Ниже сводка извлеченных данных из чертежа:

Тип входа: {source.input_type}
Файл: {source.file_name}
MIME: {source.mime_type}
Единицы: {drawing_facts.get("units", "Не определено")}
Габаритный прямоугольник: {drawing_facts.get("bounding_box")}

Слои (фрагмент):
{drawing_facts.get("layers", [])[:40]}

Типы сущностей:
{drawing_facts.get("entity_counts", {})}

Извлеченные размерные значения (фрагмент):
{drawing_facts.get("dimensions", [])[:80]}

Извлеченный текст с чертежа (фрагмент):
{drawing_facts.get("extracted_texts", [])[:120]}

Семантические кандидаты:
{semantic}

Инженерные признаки (используй в первую очередь):
{engineering_features}

Аудит извлечения:
{extraction_audit}

Validation gate:
{validation_gate}

Evidence:
{normalized.evidence}

Эталон структуры и стиля (используй как шаблон, но заполняй данными из DXF):
{reference_passport_text}

Требования:
- Пиши кратко, техническим языком.
- Если значение отсутствует в чертеже, явно укажи "Не указано в чертеже".
- Не добавляй вымышленные ГОСТ/допуски/материалы.
- Не превращай делительный диаметр группы отверстий в центральное отверстие.
- Не пропускай critical_unclassified: если они не вошли в разделы, добавь предупреждение "требует проверки по чертежу".
"""
