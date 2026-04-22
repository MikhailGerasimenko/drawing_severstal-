import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

import uvicorn

from passport_builder.server import app
from passport_builder.workflow import (
    generate_passport_outputs,
    process_input_asset,
    render_png_from_json,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Мультиформатный агент: DXF/PDF/изображение -> JSON/PNG/паспорт")
    parser.add_argument("--dxf", required=False, help="Путь к входному DXF")
    parser.add_argument("--pdf", required=False, help="Путь к входному PDF")
    parser.add_argument("--image", required=False, help="Путь к входному изображению (PNG/JPG/TIFF)")
    parser.add_argument(
        "--json-in",
        required=False,
        help="Путь к входному нормализованному JSON",
    )
    parser.add_argument(
        "--example-docx",
        required=False,
        help="Путь к эталонному DOCX паспорта (для структуры/стиля)",
    )
    parser.add_argument(
        "--out-dir",
        default="output",
        help="Каталог для результата (default: output)",
    )
    parser.add_argument(
        "--name",
        default="result",
        help="Базовое имя выходных файлов без расширения",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Не создавать DOCX, если не заполнены обязательные поля",
    )
    parser.add_argument(
        "--render-png",
        action="store_true",
        help="Принудительно рендерить PNG (по умолчанию PNG уже создается)",
    )
    parser.add_argument(
        "--skip-png",
        action="store_true",
        help="Не рендерить PNG",
    )
    parser.add_argument(
        "--png-out",
        default=None,
        help="Путь к PNG (по умолчанию: <out-dir>/<name>.png)",
    )
    parser.add_argument(
        "--png-dpi",
        type=int,
        default=300,
        help="DPI для PNG рендера (default: 300)",
    )
    parser.add_argument(
        "--render-json-png",
        action="store_true",
        help="Рендерить PNG из JSON (для проверки корректности экспорта)",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Запустить серверный API-режим",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host для серверного режима")
    parser.add_argument("--port", type=int, default=8000, help="Port для серверного режима")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.serve:
        uvicorn.run(app, host=args.host, port=args.port)
        return

    if args.render_json_png:
        if not args.json_in:
            parser.error("Для --render-json-png нужен --json-in")
        png_path = Path(args.png_out) if args.png_out else out_dir / f"{args.name}_from_json.png"
        render_png_from_json(args.json_in, str(png_path), dpi=args.png_dpi)
        print(f"Готово: {png_path}")
        return

    if not any([args.dxf, args.pdf, args.image, args.json_in]):
        parser.error("Нужен один из входов: --dxf, --pdf, --image или --json-in")

    normalized, json_path, preview_path = process_input_asset(
        out_dir=out_dir,
        name=args.name,
        dxf_path=args.dxf,
        pdf_path=args.pdf,
        image_path=args.image,
        json_in=args.json_in,
        png_dpi=args.png_dpi,
        render_png=not args.skip_png or args.render_png,
    )
    if args.json_in:
        print(f"Загружен: {args.json_in}")
    else:
        print(f"Готово: {json_path}")
        if preview_path:
            print(f"Готово: {preview_path}")

    if not args.example_docx:
        return

    outputs = generate_passport_outputs(
        normalized,
        example_docx=args.example_docx,
        out_dir=out_dir,
        name=args.name,
        strict=args.strict,
    )
    for path in outputs.values():
        print(f"Готово: {path}")


if __name__ == "__main__":
    main()
