import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .workflow import convert_dxf

app = FastAPI(
    title="DXF Converter Service",
    description="Микросервис: DXF → PNG + normalized JSON + LLM Markdown context",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "data/artifacts"))


class ValidationGateResponse(BaseModel):
    status: str = "unknown"
    ready_for_llm: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConvertResponse(BaseModel):
    job_id: str
    name: str
    source_file: str
    designation: str = ""
    product_name: str = ""
    validation_gate: ValidationGateResponse
    llm_context: str = Field(description="LLM Engineering Context в Markdown (текст)")
    files: dict[str, str]
    download_urls: dict[str, str]


def _artifact_url(request: Request, job_id: str, filename: str) -> str:
    return str(request.url_for("download_artifact", job_id=job_id, filename=filename))


def _resolve_artifact(job_id: str, filename: str) -> Path:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
    path = (ARTIFACTS_DIR / job_id / filename).resolve()
    base = (ARTIFACTS_DIR / job_id).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return path


def _semantic_field(normalized, key: str, default: str = "") -> str:
    semantic = normalized.semantic_candidates or {}
    if isinstance(semantic, dict):
        raw = semantic.get(key) or {}
        if isinstance(raw, dict):
            return str(raw.get("value") or default)
        return str(raw or default)
    value = getattr(semantic, key, None)
    if hasattr(value, "value"):
        return str(value.value or default)
    return default


def _validation_gate(normalized) -> ValidationGateResponse:
    semantic = normalized.semantic_candidates or {}
    gate = semantic.get("validation_gate", {}) if isinstance(semantic, dict) else getattr(semantic, "validation_gate", {}) or {}
    errors = gate.get("errors") or []
    warnings = gate.get("warnings") or []
    if isinstance(errors, str):
        errors = [errors] if errors else []
    if isinstance(warnings, str):
        warnings = [warnings] if warnings else []
    return ValidationGateResponse(
        status=str(gate.get("status") or "unknown"),
        ready_for_llm=bool(gate.get("ready_for_llm")),
        errors=list(errors),
        warnings=list(warnings),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dxf-converter"}


@app.get("/v1/artifacts/{job_id}/{filename}", name="download_artifact")
def download_artifact(job_id: str, filename: str) -> FileResponse:
    path = _resolve_artifact(job_id, filename)
    media = "application/json" if path.suffix == ".json" else None
    if path.suffix == ".png":
        media = "image/png"
    elif path.suffix == ".md":
        media = "text/markdown; charset=utf-8"
    return FileResponse(path, media_type=media, filename=filename)


@app.post("/v1/convert", response_model=ConvertResponse)
async def convert_endpoint(
    request: Request,
    file: UploadFile = File(..., description="Файл чертежа .dxf"),
    name: str = Form("", description="Базовое имя артефактов (без расширения)"),
    png_dpi: int = Form(300, ge=72, le=1200),
    render_png: bool = Form(True),
    dxf_text_policy: str = Form("filling"),
    dxf_lineweight_scaling: float = Form(1.0),
    dxf_text_scale: float = Form(1.0),
    dxf_letter_spacing: float = Form(1.0),
    dxf_render_backend: str = Form("classic"),
) -> ConvertResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".dxf":
        raise HTTPException(status_code=400, detail="Поддерживается только формат .dxf")

    job_id = uuid.uuid4().hex
    job_dir = ARTIFACTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_name = file.filename or "input.dxf"
    input_path = job_dir / input_name
    with input_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    base_name = name.strip() or Path(input_name).stem
    try:
        result = convert_dxf(
            str(input_path),
            out_dir=job_dir,
            name=base_name,
            png_dpi=png_dpi,
            render_png=render_png,
            dxf_text_policy=dxf_text_policy,  # type: ignore[arg-type]
            dxf_lineweight_scaling=dxf_lineweight_scaling,
            dxf_text_scale=dxf_text_scale,
            dxf_letter_spacing=dxf_letter_spacing,
            dxf_render_backend=dxf_render_backend,  # type: ignore[arg-type]
        )
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"Ошибка конвертации: {exc}") from exc

    files: dict[str, str] = {"json": result.json_path.name}
    download_urls: dict[str, str] = {
        "json": _artifact_url(request, job_id, result.json_path.name),
    }
    if result.png_path:
        files["png"] = result.png_path.name
        download_urls["png"] = _artifact_url(request, job_id, result.png_path.name)

    gate = _validation_gate(result.normalized)
    return ConvertResponse(
        job_id=job_id,
        name=result.json_path.stem,
        source_file=input_name,
        designation=_semantic_field(result.normalized, "designation"),
        product_name=_semantic_field(result.normalized, "product_name"),
        validation_gate=gate,
        llm_context=result.llm_markdown_text,
        files=files,
        download_urls=download_urls,
    )


@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str, request: Request) -> dict:
    job_dir = (ARTIFACTS_DIR / job_id).resolve()
    base = ARTIFACTS_DIR.resolve()
    if base not in job_dir.parents or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Задача не найдена")

    artifacts = []
    for path in sorted(job_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {".json", ".png", ".md", ".dxf"}:
            artifacts.append(
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "url": _artifact_url(request, job_id, path.name),
                }
            )
    return {"job_id": job_id, "artifacts": artifacts}
