import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Union

from .input_router import load_dxf
from .markdown_context import render_llm_markdown_context
from .models import NormalizedDrawing
from .rendering import RenderBackendName, TextPolicyName, render_dxf_to_png

RenderBackend = RenderBackendName
TextPolicy = TextPolicyName


@dataclass(frozen=True)
class ConvertArtifacts:
    normalized: NormalizedDrawing
    json_path: Path
    png_path: Optional[Path]
    llm_markdown_text: str
    llm_markdown_path: Optional[Path] = None


def _slugify_name(value: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE).strip("._")
    return slug or "drawing"


def save_normalized_json(normalized: NormalizedDrawing, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(normalized), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_llm_markdown_context(normalized: NormalizedDrawing, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_llm_markdown_context(normalized), encoding="utf-8")
    return path


def convert_dxf(
    dxf_path: str,
    *,
    out_dir: Union[str, Path],
    name: Optional[str] = None,
    png_dpi: int = 300,
    render_png: bool = True,
    dxf_text_policy: TextPolicy = "filling",
    dxf_lineweight_scaling: float = 1.0,
    dxf_text_scale: float = 1.0,
    dxf_letter_spacing: float = 1.0,
    dxf_render_backend: RenderBackend = "classic",
    save_llm_markdown_file: bool = False,
) -> ConvertArtifacts:
    """DXF → normalized JSON + PNG preview + компактный LLM Markdown (текст)."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    base_name = _slugify_name(name or Path(dxf_path).stem)
    png_path = out_path / f"{base_name}.png"
    json_path = out_path / f"{base_name}.json"
    llm_path = out_path / f"{base_name}_llm_context.md"

    normalized = load_dxf(dxf_path, preview_path=str(png_path) if render_png else None)

    if render_png:
        render_dxf_to_png(
            dxf_path,
            str(png_path),
            dpi=png_dpi,
            text_policy=dxf_text_policy,
            lineweight_scaling=dxf_lineweight_scaling,
            text_scale=dxf_text_scale,
            letter_spacing=dxf_letter_spacing,
            backend=dxf_render_backend,
        )
        if normalized.preview:
            normalized.preview.path = str(png_path)
            normalized.preview.dpi = png_dpi
    elif normalized.preview:
        normalized.preview.path = ""

    save_normalized_json(normalized, json_path)
    llm_markdown_text = render_llm_markdown_context(normalized)
    llm_markdown_path = None
    if save_llm_markdown_file:
        llm_markdown_path = save_llm_markdown_context(normalized, llm_path)

    return ConvertArtifacts(
        normalized=normalized,
        json_path=json_path,
        png_path=png_path if render_png else None,
        llm_markdown_text=llm_markdown_text,
        llm_markdown_path=llm_markdown_path,
    )
