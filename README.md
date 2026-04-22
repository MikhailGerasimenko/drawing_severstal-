# Мультиформатный агент чертежей

Проект принимает чертежи в форматах `DXF`, `PDF`, `PNG/JPG/TIFF` и формирует единый `normalized_drawing_json`.  
Для `DXF` дополнительно сохраняется превью `PNG`, а для `PDF/изображений` строится контейнер под OCR/Vision.  
Опционально может дополнительно формировать паспорт изделия в `Markdown` и `DOCX`.

## 1) Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Настройка API

```bash
cp .env.example .env
```

Заполни в `.env`:
- `QWEN_API_KEY`
- при необходимости `QWEN_BASE_URL`
- модель `QWEN_MODEL`

### Вариант A: Qwen (как раньше)

```env
LLM_PROVIDER=qwen
QWEN_API_KEY=...
QWEN_BASE_URL=...
QWEN_MODEL=qwen-plus
```

### Вариант B: OpenRouter

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
OPENROUTER_SITE_URL=
OPENROUTER_APP_NAME=dxf-passport-builder
```

`OPENROUTER_MODEL` можешь заменить на любую доступную у тебя модель OpenRouter.

## 3) Базовый запуск

### DXF -> normalized JSON + PNG

```bash
python3 main.py \
  --dxf "534 - Толкатель (dxf).dxf" \
  --out-dir output \
  --name "drawing_534"
```

Результат:
- `output/drawing_534.json`
- `output/drawing_534.png`

### PDF -> normalized JSON + PNG-preview

```bash
python3 main.py \
  --pdf "drawing.pdf" \
  --out-dir output \
  --name "drawing_pdf"
```

### Изображение -> normalized JSON + PNG-preview

```bash
python3 main.py \
  --image "drawing_scan.tiff" \
  --out-dir output \
  --name "drawing_scan"
```

## 4) Запуск генерации паспорта (опционально)

```bash
python3 main.py \
  --dxf "534 - Толкатель (dxf).dxf" \
  --example-docx "Паспорт эталон 42-2-.docx" \
  --out-dir output \
  --name "passport_534"
```

Результат:
- `output/passport_534.json` (normalized drawing json)
- `output/passport_534.png`
- `output/passport_534.md`
- `output/passport_534.docx`
- `output/passport_534_report.json`

### Генерация паспорта из готового JSON

```bash
python3 main.py \
  --json-in "output/drawing_534.json" \
  --example-docx "Паспорт эталон 42-2-.docx" \
  --out-dir output \
  --name "passport_from_json"
```

## 5) Строгий режим проверки

Если нужен контроль обязательных полей перед выпуском `docx`, используй `--strict`:

```bash
python3 main.py \
  --dxf "534 - Толкатель (dxf).dxf" \
  --example-docx "Паспорт эталон 42-2-.docx" \
  --out-dir output \
  --name "passport_534_strict" \
  --strict
```

Что делает строгий режим:
- Всегда сохраняет `md` и `report.json`.
- Проверяет обязательные поля: `тип`, `обозначение`, `габариты`, `материал/твердость`, `основные размеры`, `ГДТ`.
- Если чего-то не хватает, `docx` не создается и в консоль выводится список проблемных полей.

## 6) Проверка: PNG из JSON

Чтобы проверить, насколько normalized JSON близок к исходному чертежу, можно отрендерить PNG прямо из JSON:

```bash
python3 main.py \
  --render-json-png \
  --json-in "output/drawing_534.json" \
  --out-dir output \
  --name "drawing_534_check"
```

Результат: `output/drawing_534_check_from_json.png`

## 7) Проверка достоверности JSON

```bash
python3 validate_json_fidelity.py \
  --dxf "22 - нож (dxf).dxf" \
  --json "output/final_22.json" \
  --out "output/final_22_fidelity_report.json"
```

Скрипт сравнивает DXF и JSON по:
- единицам,
- bbox,
- типам сущностей,
- длинам массивов,
- контрольным fingerprint для геометрии, текстов и feature collection.

## 8) Настройки PNG рендера

Быстрый рендер только изображения чертежа:

```bash
python3 main.py \
  --dxf "22 - нож (dxf).dxf" \
  --out-dir output \
  --name "drawing_22" \
  --render-png
```

Результат: `output/drawing_22.png`

Можно явно указать файл и DPI:

```bash
python3 main.py \
  --dxf "22 - нож (dxf).dxf" \
  --render-png \
  --png-out "output/knife_preview.png" \
  --png-dpi 400
```

Отключить PNG совсем:

```bash
python3 main.py \
  --dxf "22 - нож (dxf).dxf" \
  --out-dir output \
  --name "only_json" \
  --skip-png
```

## 9) Серверный режим

Запуск API:

```bash
python3 main.py \
  --serve \
  --host 0.0.0.0 \
  --port 8000
```

Доступные endpoints:
- `GET /health`
- `POST /convert`

## Как работает

1. `InputRouter` определяет тип входа (`dxf/pdf/image/json`).
2. Для DXF формируется полный `normalized_drawing_json`.
3. Для PDF/изображений создается preview и контейнер под OCR/Vision.
4. При наличии `--example-docx` строится паспорт по нормализованным данным.

## Если API ключ не задан

Скрипт все равно отработает и создаст fallback-версию паспорта (с пометками о недостающих данных).
