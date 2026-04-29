import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Union

from .input_router import route_input
from .io_utils import extract_docx_text, save_docx_from_markdown, save_markdown
from .json_rendering import render_json_to_png
from .models import NormalizedDrawing
from .qwen_client import QwenPassportGenerator
from .rendering import render_dxf_to_png
from .validation import build_report, save_report, validate_passport


def save_normalized_json(normalized: NormalizedDrawing, path: Union[str, Path]) -> Path:
    output_path = Path(path)
    output_path.write_text(json.dumps(asdict(normalized), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def process_input_asset(
    *,
    out_dir: Union[str, Path],
    name: str,
    dxf_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
    image_path: Optional[str] = None,
    json_in: Optional[str] = None,
    png_dpi: int = 300,
    render_png: bool = True,
    dxf_text_policy: str = "filling",
    dxf_lineweight_scaling: float = 1.0,
    dxf_text_scale: float = 1.0,
    dxf_letter_spacing: float = 1.0,
    dxf_render_backend: str = "classic",
) -> tuple[NormalizedDrawing, Path, Optional[Path]]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    preview_path = out_path / f"{name}.png"
    normalized = route_input(
        dxf_path=dxf_path,
        pdf_path=pdf_path,
        image_path=image_path,
        json_path=json_in,
        preview_path=str(preview_path),
        png_dpi=png_dpi,
    )

    if dxf_path and render_png:
        render_dxf_to_png(
            dxf_path,
            str(preview_path),
            dpi=png_dpi,
            text_policy=dxf_text_policy,
            lineweight_scaling=dxf_lineweight_scaling,
            text_scale=dxf_text_scale,
            letter_spacing=dxf_letter_spacing,
            backend=dxf_render_backend,
        )
    elif json_in:
        preview_path = Path(normalized.preview.path) if normalized.preview and normalized.preview.path else None
    elif not render_png:
        preview_path = None

    if preview_path is not None and normalized.preview:
        normalized.preview.path = str(preview_path)

    json_path = out_path / f"{name}.json"
    save_normalized_json(normalized, json_path)
    return normalized, json_path, preview_path


def render_png_from_json(json_path: str, output_path: str, dpi: int = 300) -> Path:
    render_json_to_png(json_path, output_path, dpi=dpi)
    return Path(output_path)


def generate_passport_outputs(
    normalized: NormalizedDrawing,
    *,
    example_docx: str,
    out_dir: Union[str, Path],
    name: str,
    strict: bool = False,
) -> dict[str, Path]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    reference = extract_docx_text(example_docx)
    markdown = QwenPassportGenerator().generate(normalized, reference)

    md_path = out_path / f"{name}.md"
    docx_path = out_path / f"{name}.docx"
    report_path = out_path / f"{name}_report.json"

    validation = validate_passport(markdown)
    report = build_report(
        dxf_file=normalized.source.file_name,
        passport_name=name,
        validation=validation,
        metadata={
            "strict_mode": strict,
            "example_docx": Path(example_docx).name,
            "input_type": normalized.source.input_type,
        },
    )

    save_markdown(markdown, md_path)
    save_report(report, report_path)

    outputs = {"markdown": md_path, "report": report_path}
    if not (strict and not validation["is_valid"]):
        save_docx_from_markdown(markdown, docx_path)
        outputs["docx"] = docx_path
    return outputs
