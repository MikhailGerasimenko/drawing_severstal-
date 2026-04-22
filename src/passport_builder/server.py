import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile

from .workflow import generate_passport_outputs, process_input_asset


app = FastAPI(title="DXF Passport Agent")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    name: str = Form("result"),
    render_png: bool = Form(True),
    png_dpi: int = Form(300),
    generate_passport: bool = Form(False),
    example_docx_path: str = Form(""),
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

        out_dir = Path("server_output")
        normalized, json_path, preview_path = process_input_asset(
            out_dir=out_dir,
            name=name,
            png_dpi=png_dpi,
            render_png=render_png,
            **kwargs,
        )

        response = {
            "json_path": str(json_path),
            "preview_path": str(preview_path) if preview_path else "",
            "input_type": normalized.source.input_type,
        }
        if generate_passport and example_docx_path:
            outputs = generate_passport_outputs(
                normalized,
                example_docx=example_docx_path,
                out_dir=out_dir,
                name=name,
            )
            response["passport_outputs"] = {key: str(value) for key, value in outputs.items()}
        return response
