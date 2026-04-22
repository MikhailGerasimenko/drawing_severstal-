from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SourceManifest:
    input_type: str
    file_name: str
    original_path: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str


@dataclass
class PreviewArtifact:
    path: str
    format: str = "png"
    width: Optional[int] = None
    height: Optional[int] = None
    dpi: Optional[int] = None


@dataclass
class OcrBlock:
    text: str
    raw_text: str
    bbox: list[float] = field(default_factory=list)
    confidence: float = 0.0
    page: int = 1


@dataclass
class VisionBlock:
    block_type: str
    label: str
    bbox: list[float] = field(default_factory=list)
    confidence: float = 0.0
    page: int = 1


@dataclass
class SemanticCandidate:
    value: str
    confidence: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class SemanticPassportJson:
    product_name: SemanticCandidate
    designation: SemanticCandidate
    units: SemanticCandidate
    material_hardness: SemanticCandidate
    overall_dimensions: SemanticCandidate
    geometry_facts: list[str] = field(default_factory=list)
    gdt_facts: list[str] = field(default_factory=list)
    notes_facts: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class DxfSummary:
    file_name: str
    designation_guess: Optional[str]
    title_guess: Optional[str]
    units: str
    entity_counts: dict[str, int]
    dimensions: list[float]
    layers: list[str]
    bounding_box: Optional[dict[str, float]]
    extracted_texts: list[str]
    geometry: dict[str, Any] = field(default_factory=dict)
    feature_collection: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedDrawing:
    source: SourceManifest
    preview: Optional[PreviewArtifact]
    drawing_facts: dict[str, Any] = field(default_factory=dict)
    ocr_blocks: list[OcrBlock] = field(default_factory=list)
    vision_blocks: list[VisionBlock] = field(default_factory=list)
    semantic_candidates: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    legacy_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class PassportSection:
    title: str
    content: str


@dataclass
class PassportData:
    product_name: str
    designation: str
    sections: list[PassportSection] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
