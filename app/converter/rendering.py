import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, Optional

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache").resolve()))

import ezdxf
from ezdxf.addons.drawing import matplotlib as ezdxf_matplotlib
from ezdxf.addons.drawing.config import Configuration, TextPolicy


TextPolicyName = Literal["filling", "outline", "replace_rect", "replace_fill", "ignore"]
RenderBackendName = Literal["classic", "librecad", "auto"]


def _to_text_policy(name: TextPolicyName) -> TextPolicy:
    mapping = {
        "filling": TextPolicy.FILLING,
        "outline": TextPolicy.OUTLINE,
        "replace_rect": TextPolicy.REPLACE_RECT,
        "replace_fill": TextPolicy.REPLACE_FILL,
        "ignore": TextPolicy.IGNORE,
    }
    return mapping.get(name, TextPolicy.FILLING)


def _tune_text_entities(doc: ezdxf.document.Drawing, text_scale: float, letter_spacing: float) -> None:
    if text_scale == 1.0 and letter_spacing == 1.0:
        return

    def _apply(entities: object) -> None:
        for entity in entities:
            t = entity.dxftype()
            if t in {"TEXT", "ATTRIB"}:
                if hasattr(entity.dxf, "height") and text_scale != 1.0:
                    entity.dxf.height = float(entity.dxf.height) * text_scale
                if hasattr(entity.dxf, "width") and letter_spacing != 1.0:
                    width = float(getattr(entity.dxf, "width", 1.0))
                    entity.dxf.width = width * letter_spacing
            elif t == "MTEXT":
                if hasattr(entity.dxf, "char_height") and text_scale != 1.0:
                    entity.dxf.char_height = float(entity.dxf.char_height) * text_scale
                if hasattr(entity.dxf, "width") and letter_spacing != 1.0:
                    width = float(getattr(entity.dxf, "width", 0.0))
                    if width > 0:
                        entity.dxf.width = width * letter_spacing

    _apply(doc.modelspace())
    for block in doc.blocks:
        _apply(block)


def _find_librecad() -> Optional[str]:
    for candidate in (
        shutil.which("librecad"),
        shutil.which("LibreCAD"),
        "/Applications/LibreCAD.app/Contents/MacOS/LibreCAD",
        "/Applications/LibreCAD.app/Contents/MacOS/librecad",
    ):
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _rasterize_pdf_to_png(pdf_path: Path, png_path: Path, dpi: int) -> None:
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        prefix = png_path.with_suffix("")
        subprocess.run(
            [pdftoppm, "-png", "-singlefile", "-r", str(dpi), str(pdf_path), str(prefix)],
            check=True,
            capture_output=True,
            text=True,
        )
        return

    ghostscript = shutil.which("gs")
    if ghostscript:
        subprocess.run(
            [
                ghostscript,
                "-sDEVICE=png16m",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                f"-r{dpi}",
                f"-sOutputFile={png_path}",
                str(pdf_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return

    sips = shutil.which("sips")
    if sips:
        subprocess.run(
            [sips, "-s", "format", "png", str(pdf_path), "--out", str(png_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return

    raise RuntimeError("Не найден инструмент для PDF->PNG: нужен pdftoppm, gs или sips")


def _render_dxf_to_png_librecad(dxf_path: str, png_path: str, dpi: int) -> None:
    librecad = _find_librecad()
    if not librecad:
        raise RuntimeError("LibreCAD не найден. Установите LibreCAD или используйте classic backend.")

    out_path = Path(png_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="librecad-render-") as tmp_dir:
        pdf_path = Path(tmp_dir) / f"{out_path.stem}.pdf"
        subprocess.run(
            [
                librecad,
                "dxf2pdf",
                "-a",
                "-m",
                "-r",
                str(dpi),
                "-o",
                str(pdf_path),
                str(Path(dxf_path).resolve()),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        _rasterize_pdf_to_png(pdf_path, out_path, dpi=dpi)


def _render_dxf_to_png_classic(
    dxf_path: str,
    png_path: str,
    dpi: int,
    text_policy: TextPolicyName,
    lineweight_scaling: float,
    text_scale: float,
    letter_spacing: float,
) -> None:
    doc = ezdxf.readfile(dxf_path)
    _tune_text_entities(doc, text_scale=text_scale, letter_spacing=letter_spacing)
    msp = doc.modelspace()
    out_path = Path(png_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    config = Configuration.defaults().with_changes(
        text_policy=_to_text_policy(text_policy),
        lineweight_scaling=lineweight_scaling,
        custom_bg_color="#FFFFFF",
        custom_fg_color="#000000",
    )
    ezdxf_matplotlib.qsave(
        msp,
        str(out_path),
        dpi=dpi,
        bg="#FFFFFF",
        fg="#000000",
        config=config,
    )


def render_dxf_to_png(
    dxf_path: str,
    png_path: str,
    dpi: int = 300,
    text_policy: TextPolicyName = "filling",
    lineweight_scaling: float = 1.0,
    text_scale: float = 1.0,
    letter_spacing: float = 1.0,
    backend: RenderBackendName = "classic",
    auto_rotate_portrait: bool = True,
    dedupe_text_entities: bool = False,
) -> None:
    # Keep compatibility with previous best-looking output:
    # default rendering path uses ezdxf qsave.
    del auto_rotate_portrait
    del dedupe_text_entities

    if backend == "librecad":
        _render_dxf_to_png_librecad(dxf_path, png_path, dpi=dpi)
        return
    if backend == "auto" and _find_librecad():
        _render_dxf_to_png_librecad(dxf_path, png_path, dpi=dpi)
        return
    _render_dxf_to_png_classic(
        dxf_path,
        png_path,
        dpi=dpi,
        text_policy=text_policy,
        lineweight_scaling=lineweight_scaling,
        text_scale=text_scale,
        letter_spacing=letter_spacing,
    )
