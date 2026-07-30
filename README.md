# DXF Converter

Микросервис конвертации чертежей DXF в PNG, normalized JSON и LLM Markdown-контекст для генерации паспорта изделия.

Каркас — корпоративный FastAPI Template (Poetry, Gunicorn, OpenTelemetry, Helm, GitLab CI).

## Структура

```
app/
  main.py                 # FastAPI entrypoint
  core/                   # config, middleware, handlers, exceptions
  api/v1/                 # /api/v1 health, convert, artifacts
  converter/              # DXF parse → semantic → PNG/JSON/llm_context
config/gunicorn_conf.py
.helm/                    # Kubernetes chart
.gitlab-ci.yml
```

## API

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/convert` | Multipart DXF → `BaseResponse[ConvertData]` |
| GET | `/api/v1/jobs/{job_id}` | Список артефактов |
| GET | `/api/v1/artifacts/{job_id}/{filename}` | Скачивание файла |

Успешный ответ convert:

```json
{
  "request_id": "...",
  "timestamp": "...",
  "data": {
    "job_id": "...",
    "llm_context": "# LLM Engineering Context\\n...",
    "validation_gate": {"status": "pass", "ready_for_llm": true, "errors": [], "warnings": []},
    "files": {"json": "...", "png": "..."},
    "download_urls": {"json": "...", "png": "..."}
  }
}
```

Подробнее: [API.md](API.md). Системный промпт для LLM: `docs/system_prompt_passport_markdown.md`.

## Локальный запуск

```bash
poetry install --no-root --with dev
make run
# либо
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# CLI
python -m app.converter.cli --dxf samples/some.dxf --out-dir output --skip-png
python -m app.converter.cli --serve
```

## Тесты

```bash
pytest tests/ -q
```

DXF в `samples/` опциональны — связанные тесты делают `skip`, если файлов нет.

## Docker / Helm

- `Dockerfile` — corp Python image, OTEL via `opentelemetry-instrument`
- Healthcheck: `GET /api/v1/health`
- `.helm/` — стандартный chart контура
