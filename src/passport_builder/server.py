import os
import shutil
import tempfile
import urllib.error
import urllib.request
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .workflow import generate_passport_outputs, process_input_asset, render_png_from_json


app = FastAPI(title="DXF Passport Agent")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
SERVER_OUTPUT_DIR = Path("server_output")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _send_to_n8n(webhook_url: str, payload: dict) -> dict:
    if not webhook_url:
        return {"status": "skipped", "message": "Webhook URL не указан"}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return {"status": "sent", "http_status": response.status, "response": body[:1000]}
    except urllib.error.HTTPError as exc:
        return {"status": "error", "http_status": exc.code, "message": str(exc)}
    except urllib.error.URLError as exc:
        return {"status": "error", "message": str(exc)}


def _artifact_url(request: Request, path: Optional[Path]) -> str:
    if not path:
        return ""
    return str(request.url_for("artifact_file", filename=path.name))


@app.get("/artifacts/{filename}", name="artifact_file")
def artifact_file(filename: str) -> FileResponse:
    path = (SERVER_OUTPUT_DIR / filename).resolve()
    base = SERVER_OUTPUT_DIR.resolve()
    if base not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path)


@app.get("/", response_class=HTMLResponse)
def demo_page() -> str:
    return """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>DXF -> Паспорт (Demo)</title>
    <style>
      :root {
        --bg: #f7f8fc;
        --card: #ffffff;
        --text: #0f172a;
        --muted: #475569;
        --border: #dbe2ee;
        --accent: #2563eb;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Inter, Arial, sans-serif;
        color: var(--text);
        background: radial-gradient(circle at top, #eef4ff 0%, var(--bg) 40%);
      }
      .container {
        max-width: 980px;
        margin: 32px auto;
        padding: 0 18px;
      }
      .hero {
        background: linear-gradient(135deg, #1d4ed8, #3b82f6);
        color: #fff;
        border-radius: 14px;
        padding: 20px;
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.25);
      }
      .hero h1 { margin: 0 0 8px; font-size: 26px; }
      .hero p { margin: 0; opacity: 0.96; }
      .steps {
        margin-top: 14px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .step {
        border: 1px solid rgba(255, 255, 255, 0.35);
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 13px;
      }
      .card {
        margin-top: 18px;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: var(--card);
        padding: 18px;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
      }
      form { display: grid; gap: 12px; }
      label { display: grid; gap: 6px; font-size: 14px; color: var(--muted); }
      input[type=file], input[type=text], input[type=number] {
        padding: 10px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: #fff;
        font-size: 14px;
      }
      .help { font-size: 12px; color: #64748b; }
      button {
        width: fit-content;
        border: none;
        border-radius: 10px;
        background: var(--accent);
        color: #fff;
        padding: 11px 16px;
        font-weight: 600;
        cursor: pointer;
      }
      button:hover { filter: brightness(1.06); }
    </style>
  </head>
  <body>
    <div class="container">
      <section class="hero">
        <h1>Демонстрация конвейера паспорта</h1>
        <p>Мини-MVP для коллег: загружаете файл и получаете все артефакты по шагам.</p>
        <div class="steps">
          <span class="step">1. DXF/PDF/IMG</span>
          <span class="step">2. JSON</span>
          <span class="step">3. PNG из JSON</span>
          <span class="step">4. n8n Webhook</span>
          <span class="step">5. Паспорт изделия</span>
        </div>
      </section>

      <section class="card">
        <form action="/demo/run" method="post" enctype="multipart/form-data">
          <label>Файл чертежа/документа
            <input type="file" name="file" required />
          </label>
          <label>Имя результата
            <input type="text" name="name" value="demo_result" />
          </label>
          <label>Путь к эталонному DOCX (для генерации паспорта)
            <input type="text" name="example_docx_path" placeholder="/absolute/path/to/example.docx" />
          </label>
          <label>Webhook n8n (опционально)
            <input type="text" name="n8n_webhook_url" placeholder="https://.../webhook/..." />
          </label>
          <label>PNG DPI
            <input type="number" name="png_dpi" value="300" min="72" max="1200" />
            <span class="help">Больше DPI = лучше детализация PNG, но тяжелее файл и дольше обработка.</span>
          </label>
          <button type="submit">Запустить демо</button>
        </form>
      </section>
    </div>
  </body>
</html>
"""


@app.post("/demo/run", response_class=HTMLResponse)
async def demo_run(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form("demo_result"),
    png_dpi: int = Form(300),
    example_docx_path: str = Form(""),
    n8n_webhook_url: str = Form(""),
) -> str:
    suffix = Path(file.filename or "input").suffix.lower()
    with tempfile.TemporaryDirectory(prefix="passport-demo-") as tmp_dir:
        temp_input = Path(tmp_dir) / (file.filename or f"input{suffix}")
        with temp_input.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        kwargs: dict[str, Optional[str]] = {
            "dxf_path": str(temp_input) if suffix == ".dxf" else None,
            "pdf_path": str(temp_input) if suffix == ".pdf" else None,
            "image_path": str(temp_input)
            if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
            else None,
        }

        out_dir = SERVER_OUTPUT_DIR
        normalized, json_path, preview_path = process_input_asset(
            out_dir=out_dir,
            name=name,
            png_dpi=png_dpi,
            render_png=True,
            **kwargs,
        )

        json_png_path = out_dir / f"{name}_from_json.png"
        render_png_from_json(str(json_path), str(json_png_path), dpi=png_dpi)

        passport_outputs: dict[str, Path] = {}
        if example_docx_path:
            passport_outputs = generate_passport_outputs(
                normalized,
                example_docx=example_docx_path,
                out_dir=out_dir,
                name=name,
            )

        payload = {
            "pipeline": "dxf-json-png-n8n-passport",
            "name": name,
            "input_type": normalized.source.input_type,
            "normalized_json": asdict(normalized),
            "files": {
                "json_path": str(json_path),
                "preview_path": str(preview_path) if preview_path else "",
                "json_png_path": str(json_png_path),
                "passport_outputs": {key: str(value) for key, value in passport_outputs.items()},
            },
            "urls": {
                "json_url": _artifact_url(request, json_path),
                "preview_url": _artifact_url(request, preview_path),
                "json_png_url": _artifact_url(request, json_png_path),
                "passport_urls": {
                    key: _artifact_url(request, value) for key, value in passport_outputs.items()
                },
            },
        }

        n8n_result = _send_to_n8n(
            n8n_webhook_url or N8N_WEBHOOK_URL,
            payload,
        )

        passport_block = '<p class="warn">Паспорт не сгенерирован (не указан эталонный DOCX).</p>'
        if passport_outputs:
            passport_lines = "".join(
                f"<li><b>{key}</b>: <code>{value}</code> | <a href='{_artifact_url(request, value)}' target='_blank'>скачать</a></li>"
                for key, value in passport_outputs.items()
            )
            passport_block = f'<ul>{passport_lines}</ul>'

    steps = [
        f"<li class='ok'>1) Входной файл принят: <code>{file.filename or 'input'}</code></li>",
        f"<li class='ok'>2) Сформирован JSON: <code>{json_path}</code> | <a href='{_artifact_url(request, json_path)}' target='_blank'>открыть</a></li>",
        f"<li class='ok'>3) Сформирован PNG из JSON: <code>{json_png_path}</code> | <a href='{_artifact_url(request, json_png_path)}' target='_blank'>открыть</a></li>",
        f"<li class='{'ok' if n8n_result.get('status') == 'sent' else 'warn'}'>4) n8n: <code>{n8n_result}</code></li>",
    ]
    steps_html = "".join(steps)

    n8n_css_class = "ok" if n8n_result.get("status") == "sent" else "warn"
    n8n_title = "Webhook отправлен" if n8n_result.get("status") == "sent" else "Webhook пропущен/ошибка"

    return f"""
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Результат демо</title>
    <style>
      :root {{
        --bg: #f7f8fc;
        --card: #ffffff;
        --border: #dbe2ee;
        --text: #0f172a;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Inter, Arial, sans-serif;
        background: var(--bg);
        color: var(--text);
      }}
      .container {{
        max-width: 980px;
        margin: 24px auto;
        padding: 0 16px;
      }}
      .card {{
        border: 1px solid var(--border);
        border-radius: 14px;
        background: var(--card);
        padding: 16px;
        margin-bottom: 14px;
      }}
      h2, h3 {{ margin: 0 0 10px; }}
      ol {{ margin: 0; padding-left: 20px; }}
      li {{ margin-bottom: 8px; }}
      code {{
        background: #f1f5f9;
        padding: 2px 6px;
        border-radius: 5px;
      }}
      .ok {{ color: #0b7a0b; }}
      .warn {{ color: #b26a00; }}
      a {{
        text-decoration: none;
        color: #2563eb;
        font-weight: 600;
      }}
    </style>
  </head>
  <body>
    <div class="container">
      <div class="card">
        <h2>Результат пайплайна</h2>
        <ol>{steps_html}</ol>
      </div>
      <div class="card">
        <h3>Статус n8n: <span class="{n8n_css_class}">{n8n_title}</span></h3>
        <code>{n8n_result}</code>
      </div>
      <div class="card">
        <h3>Паспорт изделия</h3>
        {passport_block}
      </div>
      <p><a href="/">Запустить еще раз</a></p>
    </div>
  </body>
</html>
"""


@app.post("/convert")
async def convert(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form("result"),
    render_png: bool = Form(True),
    png_dpi: int = Form(300),
    generate_passport: bool = Form(False),
    example_docx_path: str = Form(""),
    n8n_webhook_url: str = Form(""),
    send_to_n8n: bool = Form(False),
    include_normalized_json: bool = Form(True),
) -> dict:
    suffix = Path(file.filename or "input").suffix.lower()
    with tempfile.TemporaryDirectory(prefix="passport-agent-") as tmp_dir:
        temp_input = Path(tmp_dir) / (file.filename or f"input{suffix}")
        with temp_input.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        kwargs: dict[str, Optional[str]] = {
            "dxf_path": str(temp_input) if suffix == ".dxf" else None,
            "pdf_path": str(temp_input) if suffix == ".pdf" else None,
            "image_path": str(temp_input) if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"} else None,
        }

        out_dir = SERVER_OUTPUT_DIR
        normalized, json_path, preview_path = process_input_asset(
            out_dir=out_dir,
            name=name,
            png_dpi=png_dpi,
            render_png=render_png,
            **kwargs,
        )

        response: dict = {
            "json_path": str(json_path),
            "preview_path": str(preview_path) if preview_path else "",
            "input_type": normalized.source.input_type,
            "json_url": _artifact_url(request, json_path),
            "preview_url": _artifact_url(request, preview_path),
        }
        if generate_passport and example_docx_path:
            outputs = generate_passport_outputs(
                normalized,
                example_docx=example_docx_path,
                out_dir=out_dir,
                name=name,
            )
            response["passport_outputs"] = {key: str(value) for key, value in outputs.items()}
            response["passport_urls"] = {key: _artifact_url(request, value) for key, value in outputs.items()}
        if send_to_n8n:
            webhook_payload: dict = {
                "pipeline": "convert-api",
                "name": name,
                "input_type": normalized.source.input_type,
                "response": response,
            }
            if include_normalized_json:
                webhook_payload["normalized_json"] = asdict(normalized)
            response["n8n_result"] = _send_to_n8n(
                n8n_webhook_url or N8N_WEBHOOK_URL,
                webhook_payload,
            )
        return response
