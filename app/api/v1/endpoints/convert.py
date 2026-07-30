import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.api.v1.endpoints.helpers import (
    artifact_url,
    artifacts_root,
    part_type_field,
    semantic_field,
    validation_gate,
)
from app.api.v1.schemas.convert import ConvertData, ConvertResponse
from app.converter.workflow import convert_dxf
from app.core.exceptions import ValidationError
from app.core.utils import get_current_timestamp

router = APIRouter()


@router.post("/convert", response_model=ConvertResponse)
async def convert_endpoint(
    request: Request,
    file: UploadFile = File(..., description="Файл чертежа .dxf"),
    name: str = Form("", description="Базовое имя артефактов (без расширения)"),
    part_type: str = Form(
        "",
        description="Тип детали (опционально, если не извлекается из имени файла)",
    ),
    png_dpi: int = Form(300, ge=72, le=1200),
    render_png: bool = Form(True),
    dxf_text_policy: str = Form("filling"),
    dxf_lineweight_scaling: float = Form(1.0),
    dxf_text_scale: float = Form(1.0),
    dxf_letter_spacing: float = Form(1.0),
    dxf_render_backend: str = Form("classic"),
) -> ConvertResponse:
    """Convert DXF drawing into PNG, normalized JSON and LLM Markdown context."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".dxf":
        raise ValidationError(detail="Поддерживается только формат .dxf")

    job_id = uuid.uuid4().hex
    job_dir = artifacts_root() / job_id
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
            part_type_override=part_type.strip() or None,
        )
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise ValidationError(detail=f"Ошибка конвертации: {exc}") from exc

    files: dict[str, str] = {"json": result.json_path.name}
    download_urls: dict[str, str] = {
        "json": artifact_url(request, job_id, result.json_path.name),
    }
    if result.png_path:
        files["png"] = result.png_path.name
        download_urls["png"] = artifact_url(
            request, job_id, result.png_path.name
        )

    data = ConvertData(
        job_id=job_id,
        name=result.json_path.stem,
        source_file=input_name,
        designation=semantic_field(result.normalized, "designation"),
        product_name=semantic_field(result.normalized, "product_name"),
        part_type=part_type_field(result.normalized),
        validation_gate=validation_gate(result.normalized),
        llm_context=result.llm_markdown_text,
        files=files,
        download_urls=download_urls,
    )
    return ConvertResponse(
        request_id=request.state.request_id,
        timestamp=get_current_timestamp(),
        data=data,
    )
