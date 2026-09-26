"""Layout guidance, provenance and invariants shared by conversion and exports."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from doclayout.builders.alignment import AlignmentPolicy, AlignmentResult
from doclayout.services.layout import (
    LayoutConfigurationError,
    LayoutInferenceError,
    LayoutInvariantError,
    LayoutPromptLimitError,
    LayoutResult,
)
from doclayout.settings import settings

if TYPE_CHECKING:
    from doclayout.schema.blocks import Block
    from doclayout.schema.document import Document
    from doclayout.schema.groups.page import PageGroup

MAX_GUIDE_REGIONS = 512
MAX_GUIDE_BYTES = 64 * 1024


def alignment_policy(config=None) -> AlignmentPolicy | None:
    """Absent policy retains Sol geometry; supplied policies must be complete."""
    value = (config or {}).get("alignment_policy", settings.DOCLAYOUT_ALIGNMENT_POLICY)
    try:
        if isinstance(value, str):
            value = json.loads(value)
        if value is None:
            return None
        if isinstance(value, AlignmentPolicy):
            return value
        if not isinstance(value, dict):
            raise TypeError("missing policy")
        return AlignmentPolicy(**value)
    except (TypeError, ValueError) as exc:
        raise LayoutConfigurationError(
            "A configured alignment_policy must be complete (min_iou, min_score, "
            "min_containment, min_area_ratio, max_center_distance), each finite "
            "and in [0, 1]. Set DOCLAYOUT_ALIGNMENT_POLICY or converter config."
        ) from exc


def given_layout(layout: LayoutResult, image_size: tuple[int, int]) -> str:
    """Bound the complete guide, never silently truncate or filter regions."""
    if layout.image_size != image_size or min(image_size) <= 0:
        raise LayoutInferenceError("Layout image dimensions do not match the page.")
    if len(layout.regions) > MAX_GUIDE_REGIONS:
        raise LayoutPromptLimitError("Layout guide exceeds 512 regions per page.")
    width, height = image_size
    regions = []
    seen = set()
    for region in sorted(layout.regions, key=lambda r: r.order_index):
        x0, y0, x1, y1 = region.bbox
        if (
            not all(math.isfinite(v) for v in (*region.bbox, region.score))
            or not 0 <= x0 < x1 <= width
            or not 0 <= y0 < y1 <= height
            or not 0 <= region.score <= 1
            or region.order_index in seen
            or region.order_index < 1
        ):
            raise LayoutInferenceError("Layout returned invalid regions or order.")
        seen.add(region.order_index)
        regions.append(
            {
                "class_id": region.class_id,
                "label": region.label,
                "score": round(region.score, 4),
                "bbox": [
                    round(v * 1000 / size, 2)
                    for v, size in zip(
                        region.bbox, (width, height, width, height), strict=True
                    )
                ],
                "order": region.order_index,
            }
        )
    guide = json.dumps(
        {
            "model_id": layout.model_id,
            "revision": layout.revision,
            "image_size": image_size,
            "coordinate_space": "normalized_0_1000",
            "regions": regions,
        },
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(guide.encode("utf-8")) > MAX_GUIDE_BYTES:
        raise LayoutPromptLimitError("Layout guide exceeds 64 KiB per page.")
    return "\n\ngiven_layout=" + guide


@dataclass(frozen=True)
class SourceBinding:
    id: str
    block_index: int
    sol_index: int
    polygon: tuple[tuple[float, float], ...]


@dataclass
class PageLayout:
    alignment: AlignmentResult
    sources: tuple[SourceBinding, ...]
    page_polygon: tuple[tuple[float, float], ...]
    filtered: dict[str, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    def metadata(self) -> dict:
        result = self.alignment
        return {
            "model": asdict(result.layout),
            # Alignment-time counts; later filtering is recorded separately.
            "counts": {
                "regions": len(result.layout.regions),
                "matched": sum(item.status == "matched" for item in result.sol),
                "sol_only": sum(item.status == "sol_only" for item in result.sol),
                "v3_only": sum(item.status == "v3_only" for item in result.regions),
            },
            "policy": asdict(result.policy) if result.policy is not None else None,
            "alignment_mode": "sol_fallback"
            if result.layout.error_code
            else "sol_geometry"
            if result.policy is None
            else "v3_matching",
            "sources": [asdict(source) for source in self.sources],
            "page_polygon": self.page_polygon,
            "sol": [asdict(item) for item in result.sol],
            "regions": [asdict(item) for item in result.regions],
            "candidates": [asdict(item) for item in result.candidates],
            "filtered": dict(self.filtered),
            "events": list(self.events),
        }


def source_blocks(page: PageGroup) -> list[Block]:
    """Flatten groups in structure order, stopping at extracted source blocks."""
    sources = {s.id for s in page.layout.sources} if page.layout else None
    blocks = []
    seen = set()

    def resolve(block_id):
        try:
            block = page.get_block(block_id)
        except (IndexError, TypeError, AttributeError, AssertionError) as exc:
            raise LayoutInvariantError(
                "Layout structure contains an invalid block ID."
            ) from exc
        if block is None or (sources is not None and block.id != block_id):
            raise LayoutInvariantError("Layout structure contains a missing block.")
        return block

    def visit(ids):
        for block_id in ids or []:
            key = str(block_id)
            if key in seen:
                raise LayoutInvariantError("Duplicate or cyclic layout structure.")
            seen.add(key)
            block = resolve(block_id)
            if sources is not None and key in sources:
                blocks.append(block)
            elif block.structure:
                visit(block.structure)
                if sources is not None:
                    children = []
                    for child_id in block.structure:
                        child = resolve(child_id)
                        children.append(child)
                    union = children[0].polygon.merge(
                        [child.polygon for child in children[1:]]
                    )
                    if block.polygon.polygon != union.polygon:
                        raise LayoutInvariantError(
                            "Group geometry is not its members' derived union."
                        )
            elif sources is None:
                blocks.append(block)
            else:
                raise LayoutInvariantError(
                    "Processor inserted an unbound layout block."
                )

    visit(page.structure)
    return blocks


def check_layout(document: Document, *, filter_reason: str | None = None) -> None:
    """Permit grouping and explicit filtering, never silent source mutation."""
    for page in document.pages:
        state = page.layout
        if state is None:
            raise LayoutInvariantError(
                "Conversion lost its authoritative layout state."
            )
        if tuple(tuple(point) for point in page.polygon.polygon) != state.page_polygon:
            raise LayoutInvariantError(
                "Processor changed the authoritative page coordinate space."
            )
        for source in state.sources:
            children = page.children or []
            if not 0 <= source.block_index < len(children):
                raise LayoutInvariantError(
                    "Processor deleted authoritative source storage."
                )
            block = children[source.block_index]
            polygon = tuple(tuple(point) for point in block.polygon.polygon)
            if str(block.id) != source.id or polygon != source.polygon:
                raise LayoutInvariantError(
                    "Processor changed authoritative layout geometry or identity."
                )
        actual = [str(block.id) for block in source_blocks(page)]
        expected = [s.id for s in state.sources if s.id not in state.filtered]
        missing = set(expected) - set(actual)
        if filter_reason:
            for key in expected:
                if key in missing:
                    state.filtered[key] = filter_reason
            expected = [key for key in expected if key not in missing]
        if actual != expected or any(block.removed for block in source_blocks(page)):
            raise LayoutInvariantError(
                "Processor changed authoritative layout order or membership."
            )


def visible_source_blocks(page: PageGroup, config=None) -> list[Block]:
    config = config or {}
    visible = []
    for block in source_blocks(page):
        if block.removed:
            continue
        kind = block.block_type
        if kind is None:
            raise LayoutInvariantError("Source block has no type.")
        if kind.name in {"PageHeader", "PageFooter"}:
            if not config.get(f"keep_{kind.name.lower()}_in_output", False):
                continue
        elif block.ignore_for_output:
            continue
        visible.append(block)
    return visible
