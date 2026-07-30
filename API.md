# DXF Converter API

Базовый URL: `http://<host>:8000`

Все JSON-ответы бизнес-методов (кроме скачивания файлов и `/`) используют обёртку:

```json
{
  "request_id": "uuid",
  "timestamp": "ISO+tz",
  "data": { }
}
```

Ошибки:

```json
{
  "request_id": "uuid",
  "timestamp": "ISO+tz",
  "error": { "code": "HTTP_422", "message": "..." }
}
```

Header: `X-Request-ID`.

## Endpoints

### `GET /api/v1/health`

```json
{ "status": "healthy", "timestamp": "...", "service": "DXF Converter" }
```

### `POST /api/v1/convert`

`multipart/form-data`:

| Поле | Тип | Default |
|------|-----|---------|
| file | file (.dxf) | required |
| name | string | "" |
| part_type | string | "" |
| png_dpi | int | 300 |
| render_png | bool | true |
| dxf_text_policy | string | filling |
| dxf_lineweight_scaling | float | 1.0 |
| dxf_text_scale | float | 1.0 |
| dxf_letter_spacing | float | 1.0 |
| dxf_render_backend | string | classic |

`data` содержит: `job_id`, `name`, `source_file`, `designation`, `product_name`, `part_type`, `validation_gate`, `llm_context`, `files`, `download_urls`.

### `GET /api/v1/jobs/{job_id}`

Список артефактов в `data.artifacts`.

### `GET /api/v1/artifacts/{job_id}/{filename}`

Скачивание файла (без BaseResponse).
