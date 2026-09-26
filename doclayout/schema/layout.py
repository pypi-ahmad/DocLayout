"""Local layout evidence; never included in the Sol response schema."""

from typing import Literal

from pydantic import BaseModel, Field


class LayoutRegion(BaseModel):
    """A retained detection in the original rendered-image coordinate frame."""

    row: int
    class_id: int
    label: str
    score: float
    geometry_kind: Literal["rectangle_with_mask"] = "rectangle_with_mask"
    raw_bbox_px: list[float]
    bbox_px: list[float]
    order_key: float
    observed_rank: int = 0
    mask_size: tuple[int, int] = (200, 200)
    mask_rle: list[int] = Field(default_factory=list)
    eligible: bool = True
    issues: list[str] = Field(default_factory=list)


class PageRegions(BaseModel):
    """Layout output and runtime provenance for one rendered page."""

    page_id: int
    image_size: tuple[int, int]
    provider: str
    candidate_count: int = 0
    filtered_count: int = 0
    regions: list[LayoutRegion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LayoutAnalysis(BaseModel):
    """Page-independent runtime result, separate from legacy export metadata.

    ``order_key`` is model output; ``observed_rank`` is a derived stable sort
    rank, not another prediction. Elapsed time includes preparation and waiting
    for the engine lock, not just execution of model kernels.
    """

    image_size: tuple[int, int]
    model_id: str
    model_revision: str
    actual_device: Literal["cuda", "cpu"] | None
    provider: str
    elapsed_ms: float = Field(ge=0)
    candidate_count: int
    filtered_count: int
    regions: list[LayoutRegion]
    status: Literal["available", "sol_fallback"] = "available"
    failure_stage: Literal["preparation", "inference"] | None = None
    order_key_source: Literal["model_output"] | None = "model_output"
    observed_rank_source: Literal["derived_sort"] | None = "derived_sort"
    warnings: list[str] = Field(default_factory=list)


class SourceRegion(BaseModel):
    """An original block footprint, retained through processor merges."""

    block_id: str
    page_id: int
    bbox: list[float]
    region_row: int | None = None


class BlockLayout(BaseModel):
    """Local reconciliation and lineage, independent of usage counters."""

    status: Literal["matched", "sol_only", "processor"]
    sol_ordinal: int | None = None
    sol_bbox: list[float] | None = None
    initial_bbox: list[float] | None = None
    region_row: int | None = None
    iou: float | None = None
    issues: list[str] = Field(default_factory=list)
    sources: list[SourceRegion] = Field(default_factory=list)


class PageLayoutRuntime(BaseModel):
    """Runtime provenance and initial reconciliation counts, before processors."""

    model_id: str
    model_revision: str
    actual_device: Literal["cuda", "cpu"] | None
    provider: str
    elapsed_ms: float = Field(ge=0)
    counts_stage: Literal["initial_reconciliation"] = "initial_reconciliation"
    status: Literal["available", "sol_fallback"] = "available"
    failure_stage: Literal["preparation", "inference"] | None = None
    order_key_source: Literal["model_output"] | None = "model_output"
    observed_rank_source: Literal["derived_sort"] | None = "derived_sort"
    retained_region_count: int = Field(ge=0)
    prior_region_count: int = Field(ge=0)
    matched_count: int = Field(ge=0)
    sol_only_count: int = Field(ge=0)
    unmatched_v3_count: int = Field(ge=0)


class LayoutAudit(BaseModel):
    """Versioned pipeline manifest and original page detections."""

    manifest: dict
    pages: list[PageRegions] = Field(default_factory=list)
    page_runtime: dict[int, PageLayoutRuntime] = Field(default_factory=dict)
