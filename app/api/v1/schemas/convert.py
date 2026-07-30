from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.responses import BaseResponse


class ValidationGateData(BaseModel):
    status: str = "unknown"
    ready_for_llm: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConvertData(BaseModel):
    """Payload returned inside BaseResponse.data for convert."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "abc123",
                "name": "drawing",
                "source_file": "drawing.dxf",
                "designation": "54-24",
                "product_name": "Проставка",
                "part_type": "Проставка",
                "validation_gate": {
                    "status": "pass",
                    "ready_for_llm": True,
                    "errors": [],
                    "warnings": [],
                },
                "llm_context": "# LLM Engineering Context\n...",
                "files": {"json": "drawing.json", "png": "drawing.png"},
                "download_urls": {
                    "json": "http://localhost:8000/api/v1/artifacts/.../drawing.json",
                    "png": "http://localhost:8000/api/v1/artifacts/.../drawing.png",
                },
            }
        }
    )

    job_id: str
    name: str
    source_file: str
    designation: str = ""
    product_name: str = ""
    part_type: str = ""
    validation_gate: ValidationGateData
    llm_context: str = Field(
        description="LLM Engineering Context в Markdown (текст)"
    )
    files: dict[str, str]
    download_urls: dict[str, str]


class ConvertResponse(BaseResponse[ConvertData]):
    """Unified convert response."""


class ArtifactItem(BaseModel):
    name: str
    size_bytes: int
    url: str


class JobData(BaseModel):
    job_id: str
    artifacts: list[ArtifactItem] = Field(default_factory=list)


class JobResponse(BaseResponse[JobData]):
    """Unified job status response."""
