# Эталонный набор: DXF + паспорт

Папка для регрессионной оценки конвертера и (позже) LLM-паспорта.

## Как положить 10 пар

Два варианта — выберите любой.

### Вариант A — по имени (проще)

```
eval/golden/drawings/07-54-105.dxf
eval/golden/passports/07-54-105.md
```

Имя файла паспорта **должно совпадать** со stem DXF (без расширения).

### Вариант B — через manifest

Скопируйте `manifest.example.json` → `manifest.json` и перечислите пары явно.
Удобно, если имена DXF и паспорта не совпадают.

## Формат паспорта

Поддерживаемые расширения:

| Файл | Содержимое |
|------|------------|
| `.md` | Markdown-паспорт (как в `docs/system_prompt_passport_markdown.md`) |
| `.json` | JSON v2.0 (`designation`, `part_type`, `outer_geometry`, …) |
| `.txt` | Произвольный текст — для ручной сверки |

Если паспорт в Word — экспортируйте в `.md` или `.txt`.

## Что проверяем

1. **Конвертер** (без LLM): DXF → `llm_context` / поля `designation`, `part_type`, `validation_gate`.
2. **Полный пайплайн** (с LLM): сравнение с эталонным паспортом по полям.

PNG к этим парам **не обязателен** — для DXF-ветки достаточно `.dxf` + паспорт.

## Прогон оценки (OpenRouter)

1. Положите пары в `drawings/` и `passports/` (см. выше).
2. Добавьте ключ в `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-...
   ```
3. Установите зависимости: `pip install -r requirements.txt`
4. **Фаза 1** — только конвертер (бесплатно, быстро):
   ```bash
   PYTHONPATH=src python eval/run_passport_eval.py --converter-only
   ```
5. **Фаза 2** — полный пайплайн с LLM:
   ```bash
   PYTHONPATH=src python eval/run_passport_eval.py
   ```
6. Сценарий коллеги (`drawing.dxf`):
   ```bash
   PYTHONPATH=src python eval/run_passport_eval.py --converter-only --as-drawing-upload
   ```

Отчёт: `eval/runs/<timestamp>/report.md` и `summary.json`.
По каждому кейсу: `llm_context.md`, `generated.md`, `comparison.json`.


Если чертежи закрытые — добавьте `eval/golden/drawings/` в `.gitignore` локально
или храните набор отдельно; структура папок остаётся той же.
