# Туториал для коллеги: запуск DXF/PDF/IMG -> JSON/PNG/паспорт

Этот проект принимает чертежи в форматах `DXF`, `PDF`, `PNG/JPG/TIFF` и формирует нормализованный JSON. Для `DXF` дополнительно строится PNG-превью чертежа. Также можно запустить веб-страницу с формой загрузки файла и кнопками.

## 1. Что должно быть установлено

Нужен Python 3.9+ и терминал.

На macOS/Linux команды ниже выполняются из корня проекта:

```bash
cd "/Users/mixa-root/Desktop/Работа"
```

Если проект лежит в другой папке, нужно перейти именно в нее.

## 2. Первичная установка

Создать виртуальное окружение:

```bash
python3 -m venv .venv
```

Активировать окружение:

```bash
source .venv/bin/activate
```

Установить зависимости:

```bash
pip install -r requirements.txt
```

Проверить, что скрипт запускается:

```bash
python main.py --help
```

Если команда `python main.py --help` выводит список параметров, установка прошла успешно.

## 3. Важное правило запуска

Запускать нужно именно через Python:

```bash
python main.py ...
```

Не нужно запускать так:

```bash
main.py
```

Если виртуальное окружение не активировано, можно запускать напрямую через `.venv/bin/python`:

```bash
.venv/bin/python main.py --help
```

Такой вариант надежнее, потому что точно используется Python из проекта со всеми установленными библиотеками.

## 4. Генерация JSON и PNG из DXF

Базовая команда:

```bash
python main.py \
  --dxf "42-2 - Штифтодержатель.dxf" \
  --out-dir output \
  --name "42-2"
```

Результат появится в папке `output`:

```text
output/42-2.json
output/42-2.png
```

Что это значит:

- `output/42-2.json` — нормализованный JSON с геометрией, текстами, размерами, semantic_candidates, engineering_features и audit-информацией.
- `output/42-2.png` — PNG-превью исходного DXF.

## 5. Только JSON без PNG

Если нужен только JSON, а PNG рендерить не нужно:

```bash
python main.py \
  --dxf "42-2 - Штифтодержатель.dxf" \
  --out-dir output \
  --name "42-2_only_json" \
  --skip-png
```

Результат:

```text
output/42-2_only_json.json
```

## 6. Настройки качества PNG

Можно увеличить DPI:

```bash
python main.py \
  --dxf "42-2 - Штифтодержатель.dxf" \
  --out-dir output \
  --name "42-2_400dpi" \
  --png-dpi 400
```

Можно явно задать путь к PNG:

```bash
python main.py \
  --dxf "42-2 - Штифтодержатель.dxf" \
  --out-dir output \
  --name "42-2_custom_png" \
  --png-out "output/preview_42-2.png"
```

Доступные настройки DXF-рендера:

```bash
python main.py \
  --dxf "42-2 - Штифтодержатель.dxf" \
  --out-dir output \
  --name "42-2_render_tuned" \
  --png-dpi 400 \
  --dxf-text-policy filling \
  --dxf-lineweight-scaling 1.0 \
  --dxf-text-scale 1.0 \
  --dxf-letter-spacing 1.0 \
  --dxf-render-backend classic
```

Пояснения:

- `--png-dpi` — качество PNG, обычно `300` или `400`.
- `--dxf-text-policy` — режим обработки текста DXF. Обычно оставить `filling`.
- `--dxf-lineweight-scaling` — масштаб толщины линий.
- `--dxf-text-scale` — масштаб текста.
- `--dxf-letter-spacing` — межсимвольный интервал.
- `--dxf-render-backend classic` — стандартный рендер через Python/ezdxf.
- `--dxf-render-backend auto` — попробовать выбрать backend автоматически.
- `--dxf-render-backend librecad` — использовать LibreCAD-подход, если он установлен и настроен.

## 7. Генерация PNG из уже готового JSON

Это нужно для проверки, насколько JSON можно визуально восстановить в картинку.

```bash
python main.py \
  --render-json-png \
  --json-in "output/42-2.json" \
  --out-dir output \
  --name "42-2_from_json"
```

Результат:

```text
output/42-2_from_json_from_json.png
```

Если нужен конкретный путь:

```bash
python main.py \
  --render-json-png \
  --json-in "output/42-2.json" \
  --png-out "output/42-2_json_check.png"
```

## 8. Обработка PDF или изображения

PDF:

```bash
python main.py \
  --pdf "drawing.pdf" \
  --out-dir output \
  --name "drawing_pdf"
```

Изображение:

```bash
python main.py \
  --image "drawing.png" \
  --out-dir output \
  --name "drawing_image"
```

Результат будет похожий:

```text
output/drawing_pdf.json
output/drawing_pdf.png
```

Для PDF/картинок сейчас создается контейнер под OCR/Vision и PNG-превью. Основная инженерная семантика лучше всего работает для DXF.

## 9. Генерация паспорта изделия через CLI

Если есть эталонный DOCX с примером структуры паспорта, можно сгенерировать паспорт:

```bash
python main.py \
  --dxf "42-2 - Штифтодержатель.dxf" \
  --example-docx "Паспорт эталон 42-2-.docx" \
  --out-dir output \
  --name "passport_42-2"
```

Результат:

```text
output/passport_42-2.json
output/passport_42-2.png
output/passport_42-2.md
output/passport_42-2.docx
output/passport_42-2_report.json
```

Можно генерировать паспорт из уже готового JSON:

```bash
python main.py \
  --json-in "output/42-2.json" \
  --example-docx "Паспорт эталон 42-2-.docx" \
  --out-dir output \
  --name "passport_from_json"
```

## 10. Запуск веб-страницы с кнопками

Запустить сервер:

```bash
python main.py \
  --serve \
  --host 127.0.0.1 \
  --port 8000
```

После запуска открыть в браузере:

```text
http://127.0.0.1:8000
```

На странице будет форма:

- загрузка файла чертежа/документа;
- имя результата;
- путь к эталонному DOCX для генерации паспорта;
- webhook n8n;
- настройка PNG DPI;
- кнопка запуска.

## 11. Как пользоваться веб-страницей

1. Открыть `http://127.0.0.1:8000`.
2. В поле файла выбрать `DXF`, `PDF` или изображение.
3. В поле "Имя результата" указать короткое имя, например `demo_42_2`.
4. Если нужен паспорт, указать абсолютный путь к эталонному DOCX, например:

```text
/Users/mixa-root/Desktop/Работа/Паспорт эталон 42-2-.docx
```

5. Если нужен n8n webhook, указать URL webhook.
6. Нажать кнопку запуска.
7. После обработки страница покажет ссылки на артефакты.

Артефакты сохраняются в папку:

```text
server_output/
```

Обычно там появляются:

```text
server_output/demo_42_2.json
server_output/demo_42_2.png
server_output/demo_42_2_from_json.png
```

Если был указан эталонный DOCX:

```text
server_output/demo_42_2.md
server_output/demo_42_2.docx
server_output/demo_42_2_report.json
```

## 12. API endpoints

Проверка, что сервер жив:

```text
GET http://127.0.0.1:8000/health
```

Основной API для загрузки файла:

```text
POST http://127.0.0.1:8000/convert
```

Поля формы для `/convert`:

- `file` — файл чертежа.
- `name` — имя результата.
- `render_png` — рендерить PNG (`true/false`).
- `png_dpi` — DPI PNG.
- `generate_passport` — генерировать паспорт (`true/false`).
- `example_docx_path` — путь к эталонному DOCX.
- `send_to_n8n` — отправить результат в n8n (`true/false`).
- `n8n_webhook_url` — webhook URL.
- `include_normalized_json` — включать ли полный JSON в payload.

## 13. n8n webhook

Webhook можно задать двумя способами.

Способ 1: через веб-страницу, в поле `Webhook n8n`.

Способ 2: через переменную окружения:

```bash
export N8N_WEBHOOK_URL="https://your-n8n-host/webhook/your-path"
python main.py --serve --host 127.0.0.1 --port 8000
```

В webhook отправляется payload с:

- `pipeline`;
- `name`;
- `input_type`;
- `normalized_json`;
- путями к файлам;
- ссылками на артефакты.

## 14. Настройка LLM для генерации паспорта

Если нужно генерировать паспорт через LLM, создать `.env`:

```bash
cp .env.example .env
```

Вариант Qwen:

```env
LLM_PROVIDER=qwen
QWEN_API_KEY=...
QWEN_BASE_URL=...
QWEN_MODEL=qwen-plus
```

Вариант OpenRouter:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
OPENROUTER_SITE_URL=
OPENROUTER_APP_NAME=dxf-passport-builder
```

Если ключи не заданы, скрипт все равно создаст JSON/PNG. Паспорт будет сформирован fallback-режимом или не будет полноценным.

## 15. Что проверять в JSON

Главные поля в JSON:

```text
source
drawing_facts
semantic_candidates
evidence
legacy_summary
```

Особенно важны:

```text
semantic_candidates.engineering_features
semantic_candidates.extraction_audit
semantic_candidates.validation_gate
```

`engineering_features` содержит инженерные признаки:

- наружный контур;
- внутреннюю систему;
- спецэлементы;
- ГДТ;
- техтребования;
- таблицы исполнений;
- группы отверстий;
- пазы/канавки.

`extraction_audit` показывает, что распознано и что осталось неразобранным.

`validation_gate` показывает, можно ли отдавать данные в LLM:

- `pass` — можно генерировать паспорт;
- `warn` — можно делать черновик, нужна проверка;
- `fail` — лучше остановиться и проверить данные.

## 16. Частые ошибки

### Ошибка: `command not found: main.py`

Причина: скрипт запущен как команда.

Правильно:

```bash
python main.py --help
```

Или:

```bash
.venv/bin/python main.py --help
```

### Ошибка: `ModuleNotFoundError: No module named 'ezdxf'`

Причина: не активировано виртуальное окружение или не установлены зависимости.

Решение:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Или запускать так:

```bash
.venv/bin/python main.py ...
```

### Порт 8000 занят

Запустить на другом порту:

```bash
python main.py --serve --host 127.0.0.1 --port 8001
```

Открыть:

```text
http://127.0.0.1:8001
```

### Веб-страница открывается, но паспорт не создается

Проверь:

- указан ли путь к эталонному DOCX;
- существует ли этот файл;
- настроены ли LLM-ключи в `.env`;
- появился ли файл `server_output/<name>_report.json`.

### PNG выглядит плохо

Попробовать:

```bash
python main.py \
  --dxf "drawing.dxf" \
  --out-dir output \
  --name "drawing_test" \
  --png-dpi 400 \
  --dxf-text-scale 0.9 \
  --dxf-letter-spacing 1.08
```

## 17. Минимальный сценарий для коллеги

Если нужно просто получить JSON и PNG из DXF:

```bash
cd "/Users/mixa-root/Desktop/Работа"
source .venv/bin/activate
python main.py --dxf "42-2 - Штифтодержатель.dxf" --out-dir output --name "42-2"
```

Если нужно открыть страницу:

```bash
cd "/Users/mixa-root/Desktop/Работа"
source .venv/bin/activate
python main.py --serve --host 127.0.0.1 --port 8000
```

Потом открыть:

```text
http://127.0.0.1:8000
```

## 18. Что отправлять в n8n

Для n8n лучше использовать не сырой фрагмент из DXF, а нормализованный JSON, который создает проект:

```text
output/<name>.json
```

В нем уже есть:

- очищенные тексты;
- размерные блоки;
- `semantic_candidates`;
- `engineering_features`;
- `extraction_audit`;
- `validation_gate`.

Системный промпт для n8n находится здесь:

```text
output/system_prompt_n8n_passport_universal.md
```

Он специально требует читать:

```text
semantic_candidates.engineering_features
semantic_candidates.validation_gate
semantic_candidates.extraction_audit
```

И запрещает модели менять смысл классифицированных размеров, например превращать `pitch_diameter` в центральное отверстие.
