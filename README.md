# DXF Converter

Микросервис и CLI для конвертации инженерных чертежей **DXF** в три артефакта:

1. **PNG** — визуальное превью чертежа  
2. **JSON** — нормализованные факты чертежа (размеры, семантика, audit)  
3. **Markdown** — компактный **LLM Engineering Context** для n8n / Gemini / Qwen  

```
DXF ──► [Converter] ──►  drawing.png
                      ├── drawing.json
                      └── drawing_llm_context.md
```

## Быстрый старт (CLI)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py \
  --dxf "samples/42-2 - Штифтодержатель.dxf" \
  --name "42-2" \
  --out-dir output
```

Результат в `output/`:

- `42-2.png`
- `42-2.json`
- `42-2_llm_context.md`

## HTTP API (микросервис)

```bash
python main.py --serve --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs  
- ReDoc: http://localhost:8000/redoc  
- Документация для коллег: **[API.md](./API.md)** — эндпоинты, ветки **PNG** и **LLM Markdown**, сценарии n8n

### Docker

```bash
docker compose up --build
```

Сервис слушает порт **8000**, артефакты сохраняются в volume `converter-artifacts`.

## Структура проекта

```
├── main.py                 # CLI и точка входа API
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── API.md                  # Документация REST для коллег
├── samples/                # Примеры DXF
├── output/                 # Результаты CLI (gitignore, не коммитить)
└── src/dxf_converter/
    ├── api.py              # FastAPI микросервис
    ├── workflow.py         # Оркестрация конвертации
    ├── dxf_parser.py       # Парсинг DXF → summary
    ├── semantic_schema.py  # Summary → normalized JSON + классификация
    ├── markdown_context.py # JSON → LLM Markdown
    └── rendering.py        # DXF → PNG (ezdxf / LibreCAD)
```

## Параметры рендера PNG

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--png-dpi` | 300 | Разрешение превью |
| `--dxf-text-policy` | filling | Режим отрисовки текста |
| `--dxf-render-backend` | classic | `classic` (ezdxf), `librecad`, `auto` |
| `--skip-png` | — | Только JSON + Markdown |

## Интеграция с n8n

1. `POST /v1/convert` — загрузить DXF, получить `download_urls.llm_context_md`  
2. Скачать Markdown или передать URL в LLM-ноду  
3. Использовать промпт «паспорт изделия» поверх `*_llm_context.md`  

Подробные примеры `curl` — в [API.md](./API.md).
