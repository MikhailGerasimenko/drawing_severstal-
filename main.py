#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

from dxf_converter.workflow import convert_dxf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DXF Converter: DXF → PNG + JSON + LLM Markdown context",
    )
    parser.add_argument("--dxf", required=False, help="Путь к входному .dxf")
    parser.add_argument("--out-dir", default="output", help="Каталог результатов")
    parser.add_argument("--name", default=None, help="Базовое имя файлов (без расширения)")
    parser.add_argument("--skip-png", action="store_true", help="Не рендерить PNG")
    parser.add_argument("--png-dpi", type=int, default=300, help="DPI для PNG (default: 300)")
    parser.add_argument(
        "--dxf-text-policy",
        choices=["filling", "outline", "replace_rect", "replace_fill", "ignore"],
        default="filling",
    )
    parser.add_argument("--dxf-lineweight-scaling", type=float, default=1.0)
    parser.add_argument("--dxf-text-scale", type=float, default=1.0)
    parser.add_argument("--dxf-letter-spacing", type=float, default=1.0)
    parser.add_argument(
        "--dxf-render-backend",
        choices=["classic", "librecad", "auto"],
        default="classic",
    )
    parser.add_argument(
        "--llm-out",
        default=None,
        help="Сохранить LLM Markdown в файл (по умолчанию выводится в stdout)",
    )
    parser.add_argument("--serve", action="store_true", help="Запустить HTTP API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.serve:
        uvicorn.run("dxf_converter.api:app", host=args.host, port=args.port, reload=False)
        return

    if not args.dxf:
        parser.error("Укажите --dxf или запустите API через --serve")

    result = convert_dxf(
        args.dxf,
        out_dir=args.out_dir,
        name=args.name,
        png_dpi=args.png_dpi,
        render_png=not args.skip_png,
        dxf_text_policy=args.dxf_text_policy,
        dxf_lineweight_scaling=args.dxf_lineweight_scaling,
        dxf_text_scale=args.dxf_text_scale,
        dxf_letter_spacing=args.dxf_letter_spacing,
        dxf_render_backend=args.dxf_render_backend,
    )

    if args.llm_out:
        Path(args.llm_out).write_text(result.llm_markdown_text, encoding="utf-8")
        print(f"LLM Markdown saved: {args.llm_out}", file=sys.stderr)

    print(result.llm_markdown_text)

    print(f"JSON: {result.json_path}", file=sys.stderr)
    if result.png_path:
        print(f"PNG:  {result.png_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
