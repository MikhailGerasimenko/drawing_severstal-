from .models import NormalizedDrawing


SYSTEM_PROMPT = """Ты инженер-конструктор и технический писатель.
Сформируй паспорт изделия по нормализованным данным чертежа.
Не выдумывай критичные параметры: если данных нет, помечай "Не указано в чертеже".
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

Evidence:
{normalized.evidence}

Эталон структуры и стиля (используй как шаблон, но заполняй данными из DXF):
{reference_passport_text}

Требования:
- Пиши кратко, техническим языком.
- Если значение отсутствует в чертеже, явно укажи "Не указано в чертеже".
- Не добавляй вымышленные ГОСТ/допуски/материалы.
"""
