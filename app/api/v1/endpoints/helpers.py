"""Shared helpers for artifact storage and convert response fields."""

from pathlib import Path

from fastapi import Request

from app.api.v1.schemas.convert import ValidationGateData
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError


def artifacts_root() -> Path:
    path = Path(settings.artifacts_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_url(request: Request, job_id: str, filename: str) -> str:
    return str(
        request.url_for("download_artifact", job_id=job_id, filename=filename)
    )


def resolve_artifact(job_id: str, filename: str) -> Path:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValidationError(detail="Недопустимое имя файла")
    path = (artifacts_root() / job_id / filename).resolve()
    base = (artifacts_root() / job_id).resolve()
    if base not in path.parents or not path.is_file():
        raise NotFoundError(detail="Файл не найден")
    return path


def resolve_job_dir(job_id: str) -> Path:
    job_dir = (artifacts_root() / job_id).resolve()
    base = artifacts_root().resolve()
    if base not in job_dir.parents or not job_dir.is_dir():
        raise NotFoundError(detail="Задача не найдена")
    return job_dir


def semantic_field(normalized, key: str, default: str = "") -> str:
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


def part_type_field(normalized) -> str:
    semantic = normalized.semantic_candidates or {}
    if isinstance(semantic, dict):
        features = semantic.get("engineering_features", {})
        if isinstance(features, dict):
            part = features.get("part_type", {})
            if isinstance(part, dict) and part.get("value"):
                return str(part["value"])
    return semantic_field(normalized, "product_name")


def validation_gate(normalized) -> ValidationGateData:
    semantic = normalized.semantic_candidates or {}
    gate = (
        semantic.get("validation_gate", {})
        if isinstance(semantic, dict)
        else getattr(semantic, "validation_gate", {}) or {}
    )
    errors = gate.get("errors") or []
    warnings = gate.get("warnings") or []
    if isinstance(errors, str):
        errors = [errors] if errors else []
    if isinstance(warnings, str):
        warnings = [warnings] if warnings else []
    return ValidationGateData(
        status=str(gate.get("status") or "unknown"),
        ready_for_llm=bool(gate.get("ready_for_llm")),
        errors=list(errors),
        warnings=list(warnings),
    )
