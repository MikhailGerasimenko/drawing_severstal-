#!/usr/bin/env python3
"""Пакетная оценка: DXF → конвертер → OpenRouter → сравнение с эталоном."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from lib.compare import HEADER_FIELDS, ComparisonReport, PassportFields, compare_passports
from lib.converter import run_converter
from lib.golden import load_golden_passport, parse_passport_markdown
from lib.openrouter import OpenRouterError, chat_completion
from lib.pairs import discover_pairs
from lib.prompt import load_system_prompt
from lib.semantic_compare import SemanticComparisonReport, compare_passports_semantic


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        import os

        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _write_report_md(
    path: Path,
    reports: list[ComparisonReport],
    semantic_reports: list[SemanticComparisonReport],
    meta: dict,
) -> None:
    lines = [
        "# Отчёт eval: паспорта",
        "",
        f"- Дата: {meta['started_at']}",
        f"- Кейсов: {meta['case_count']}",
        f"- LLM: {meta.get('model') or '— (converter-only)'}",
        f"- simulate drawing.dxf: {meta.get('simulate_drawing_upload')}",
        "",
        "## Сводка",
        "",
        "| Кейс | gate | conv. обозн. | conv. тип | header exact | text sim | semantic |",
        "|------|------|--------------|-----------|--------------|----------|----------|",
    ]
    semantic_by_case = {item.case_id: item for item in semantic_reports}
    for report in reports:
        semantic = semantic_by_case.get(report.case_id)
        semantic_score = f"{semantic.weighted_score:.0%}" if semantic else "—"
        lines.append(
            f"| {report.case_id} | {report.converter_gate_status} | "
            f"{report.converter_designation or '—'} | {report.converter_part_type or '—'} | "
            f"{report.header_exact_rate:.0%} | {report.average_similarity:.0%} | {semantic_score} |"
        )

    lines.extend(["", "## Детали по полям", ""])
    for report in reports:
        semantic = semantic_by_case.get(report.case_id)
        lines.append(f"### {report.case_id}")
        lines.append("")
        for item in report.fields:
            mark = "✓" if item.exact_match else ("~" if item.similarity >= 0.6 else "✗")
            semantic_item = next((field for field in semantic.fields if field.name == item.name), None)
            semantic_suffix = (
                f", semantic {semantic_item.score:.0%}" if semantic_item else ""
            )
            lines.append(
                f"- {mark} **{item.name}** — text {item.similarity:.0%}{semantic_suffix}"
            )
            if not item.exact_match and item.similarity < 0.95:
                if item.expected:
                    lines.append(f"  - эталон: {item.expected[:200]}")
                if item.actual:
                    lines.append(f"  - модель: {item.actual[:200]}")
        if report.converter_gate_warnings:
            lines.append(f"- warnings: {', '.join(report.converter_gate_warnings)}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Прогон эталонных DXF через конвертер и OpenRouter")
    parser.add_argument("--golden", type=Path, default=ROOT / "dxf+паспорт")
    parser.add_argument("--out", type=Path, default=None, help="Каталог run (по умолчанию eval/runs/TIMESTAMP)")
    parser.add_argument("--prompt", type=Path, default=None, help="Файл системного промпта")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--model", default=None, help="Модель OpenRouter")
    parser.add_argument("--api-key", default=None, help="OPENROUTER_API_KEY")
    parser.add_argument("--converter-only", action="store_true", help="Только конвертер, без LLM")
    parser.add_argument(
        "--as-drawing-upload",
        action="store_true",
        help="Имитировать загрузку как drawing.dxf (сценарий коллеги)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Ограничить число кейсов")
    args = parser.parse_args()

    _load_env_file(args.env_file)

    pairs = discover_pairs(args.golden)
    if not pairs:
        print(f"Нет пар DXF+паспорт в {args.golden}", file=sys.stderr)
        print("Положите файлы в eval/golden/drawings/ и eval/golden/passports/", file=sys.stderr)
        return 1

    if args.limit > 0:
        pairs = pairs[: args.limit]

    run_dir = args.out or (ROOT / "eval" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = load_system_prompt(args.prompt)
    (run_dir / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")

    reports: list[ComparisonReport] = []
    semantic_reports: list[SemanticComparisonReport] = []
    errors: list[dict[str, str]] = []

    for pair in pairs:
        case_dir = run_dir / pair.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{pair.case_id}] конвертер…", flush=True)

        try:
            converted = run_converter(pair.drawing, simulate_drawing_upload=args.as_drawing_upload)
        except Exception as exc:
            errors.append({"case_id": pair.case_id, "stage": "converter", "error": str(exc)})
            print(f"  ошибка конвертера: {exc}", file=sys.stderr)
            continue

        (case_dir / "llm_context.md").write_text(converted.llm_context, encoding="utf-8")
        (case_dir / "converter.json").write_text(
            json.dumps(
                {
                    "designation": converted.designation,
                    "part_type": converted.part_type,
                    "gate_status": converted.gate_status,
                    "gate_warnings": converted.gate_warnings,
                    "gate_errors": converted.gate_errors,
                    "file_name_used": converted.file_name_used,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        golden = load_golden_passport(pair.passport)
        shutil.copy2(pair.passport, case_dir / f"golden{pair.passport.suffix}")

        generated_text = ""
        if not args.converter_only:
            print(f"[{pair.case_id}] OpenRouter…", flush=True)
            try:
                generated_text = chat_completion(
                    system_prompt=system_prompt,
                    user_message=converted.llm_context,
                    model=args.model,
                    api_key=args.api_key,
                )
            except OpenRouterError as exc:
                errors.append({"case_id": pair.case_id, "stage": "openrouter", "error": str(exc)})
                print(f"  ошибка LLM: {exc}", file=sys.stderr)
                continue
            (case_dir / "generated.md").write_text(generated_text, encoding="utf-8")

        if args.converter_only:
            actual = PassportFields(
                part_type=converted.part_type,
                designation=converted.designation,
            )
        else:
            actual = parse_passport_markdown(generated_text)

        field_results = compare_passports(golden, actual)
        if args.converter_only:
            field_results = [item for item in field_results if item.name in HEADER_FIELDS]
        report = ComparisonReport(
            case_id=pair.case_id,
            fields=field_results,
            converter_designation=converted.designation,
            converter_part_type=converted.part_type,
            converter_gate_status=converted.gate_status,
            converter_gate_warnings=converted.gate_warnings,
        )
        reports.append(report)
        (case_dir / "comparison.json").write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        semantic_report = compare_passports_semantic(golden, actual)
        semantic_report.case_id = pair.case_id
        semantic_reports.append(semantic_report)
        (case_dir / "semantic_comparison.json").write_text(
            json.dumps(semantic_report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if args.converter_only:
            des_match = normalize_header(golden.designation, converted.designation)
            type_match = normalize_header(golden.part_type, converted.part_type)
            print(
                f"  gate={converted.gate_status} "
                f"des={'✓' if des_match else '✗'} ({converted.designation}) "
                f"type={'✓' if type_match else '✗'} ({converted.part_type})"
            )
        else:
            print(
                f"  header {report.header_exact_rate:.0%}, "
                f"text {report.average_similarity:.0%}, "
                f"semantic {semantic_report.weighted_score:.0%}"
            )

    meta = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(pairs),
        "completed": len(reports),
        "errors": errors,
        "model": args.model,
        "converter_only": args.converter_only,
        "simulate_drawing_upload": args.as_drawing_upload,
        "golden_dir": str(args.golden),
    }
    if reports:
        meta["avg_header_exact"] = sum(r.header_exact_rate for r in reports) / len(reports)
        meta["avg_similarity"] = sum(r.average_similarity for r in reports) / len(reports)
    if semantic_reports:
        meta["avg_semantic_score"] = sum(r.weighted_score for r in semantic_reports) / len(semantic_reports)

    (run_dir / "summary.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report_md(run_dir / "report.md", reports, semantic_reports, meta)

    print(f"\nГотово: {run_dir}")
    if errors:
        print(f"Ошибок: {len(errors)}", file=sys.stderr)
        return 2
    return 0


def normalize_header(expected: str, actual: str) -> bool:
    from lib.compare import normalize_text

    left = normalize_text(expected)
    right = normalize_text(actual)
    if not left:
        return True
    return left == right or left in right or right in left


if __name__ == "__main__":
    raise SystemExit(main())
