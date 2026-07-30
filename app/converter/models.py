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
class SemanticCandidate:
    value: str
    confidence: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class DrawingSemantics:
    product_name: SemanticCandidate
    designation: SemanticCandidate
    units: SemanticCandidate
    material_hardness: SemanticCandidate
    overall_dimensions: SemanticCandidate
    geometry_facts: list[str] = field(default_factory=list)
    gdt_facts: list[str] = field(default_factory=list)
    notes_facts: list[str] = field(default_factory=list)
    engineering_features: dict[str, Any] = field(default_factory=dict)
    extraction_audit: dict[str, Any] = field(default_factory=dict)
    validation_gate: dict[str, Any] = field(default_factory=dict)
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
    raw_entities: list[dict[str, Any]] = field(default_factory=list)
    raw_virtual_entities: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    dimension_entities: list[dict[str, Any]] = field(default_factory=list)
    hatch_entities: list[dict[str, Any]] = field(default_factory=list)
    conversion_coverage: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedDrawing:
    source: SourceManifest
    preview: Optional[PreviewArtifact]
    drawing_facts: dict[str, Any] = field(default_factory=dict)
    semantic_candidates: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

