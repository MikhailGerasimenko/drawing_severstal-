from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.api.v1.endpoints.helpers import (
    artifact_url,
    resolve_artifact,
    resolve_job_dir,
)
from app.api.v1.schemas.convert import ArtifactItem, JobData, JobResponse
from app.core.utils import get_current_timestamp

router = APIRouter()


@router.get(
    "/artifacts/{job_id}/{filename}",
    name="download_artifact",
)
def download_artifact(job_id: str, filename: str) -> FileResponse:
    """Download a conversion artifact (json/png/md/dxf)."""
    path = resolve_artifact(job_id, filename)
    media = "application/json" if path.suffix == ".json" else None
    if path.suffix == ".png":
        media = "image/png"
    elif path.suffix == ".md":
        media = "text/markdown; charset=utf-8"
    return FileResponse(path, media_type=media, filename=filename)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: str, request: Request) -> JobResponse:
    """List artifacts produced for a conversion job."""
    job_dir = resolve_job_dir(job_id)
    artifacts: list[ArtifactItem] = []
    for path in sorted(job_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {
            ".json",
            ".png",
            ".md",
            ".dxf",
        }:
            artifacts.append(
                ArtifactItem(
                    name=path.name,
                    size_bytes=path.stat().st_size,
                    url=artifact_url(request, job_id, path.name),
                )
            )
    return JobResponse(
        request_id=request.state.request_id,
        timestamp=get_current_timestamp(),
        data=JobData(job_id=job_id, artifacts=artifacts),
    )
