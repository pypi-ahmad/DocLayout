"""Pure, conservative Sol/V3 alignment used before document block construction.

Inputs must describe the same uncropped, identically oriented page. Geometry is
compared in page pixels and returned in Sol's 0–1000 space. Thresholds require
evaluation on representative pages; this module supplies no production defaults.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from numbers import Real
from types import MappingProxyType
from typing import Literal

from doclayout.schema.extraction import ExtractedBlock
from doclayout.services.layout import LayoutRegion, LayoutResult

_TEXT = frozenset(
    {
        "Text",
        "SectionHeader",
        "Code",
        "ListGroup",
        "Bibliography",
        "TableOfContents",
        "Equation",
        "ChemicalBlock",
    }
)
_GRAPHIC = frozenset({"Picture", "Figure", "Diagram"})
# ID/label pairs from the pinned ONNX inference.yml, not a replacement taxonomy.
# Values permit geometry alignment only: Sol types and HTML are never rewritten.
CLASS_COMPATIBILITY = MappingProxyType(
    {
        (0, "abstract"): _TEXT,
        (1, "algorithm"): frozenset({"Code", "Text", "ListGroup"}),
        (2, "aside_text"): _TEXT,
        (3, "chart"): _GRAPHIC,
        (4, "content"): frozenset({"TableOfContents", "Text", "ListGroup"}),
        (5, "display_formula"): frozenset({"Equation", "ChemicalBlock"}),
        (6, "doc_title"): frozenset({"SectionHeader", "Text"}),
        (7, "figure_title"): frozenset({"Caption", "Text"}),
        (8, "footer"): frozenset({"PageFooter"}),
        (9, "footer_image"): _GRAPHIC,
        (10, "footnote"): frozenset({"Footnote", "Caption", "Text"}),
        (11, "formula_number"): frozenset({"Text"}),
        (12, "header"): frozenset({"PageHeader"}),
        (13, "header_image"): _GRAPHIC,
        (14, "image"): _GRAPHIC,
        (15, "inline_formula"): frozenset({"Equation", "Text"}),
        (16, "number"): frozenset({"PageHeader", "PageFooter", "Text"}),
        (17, "paragraph_title"): frozenset({"SectionHeader", "Text"}),
        (18, "reference"): frozenset({"Bibliography", "SectionHeader", "Text"}),
        (19, "reference_content"): frozenset({"Bibliography", "SectionHeader", "Text"}),
        (20, "seal"): _GRAPHIC,
        (21, "table"): frozenset({"Table", "Form", "TableOfContents"}),
        (22, "text"): _TEXT,
        (23, "vertical_text"): _TEXT,
        (24, "vision_footnote"): frozenset({"Footnote", "Caption", "Text"}),
    }
)

Reason = Literal[
    "invalid_region",
    "unsupported_class",
    "class_conflict",
    "low_score",
    "ambiguous",
    "split",
    "merge",
    "tie",
    "order_ambiguous",
    "no_candidate",
    "policy_not_configured",
    "layout_unavailable",
]


@dataclass(frozen=True, slots=True)
class AlignmentPolicy:
    """Required evaluation parameters, all in [0, 1].

    Containment is intersection / smaller area; area ratio is smaller / larger
    area. Center distance is the maximum axis displacement divided by the larger
    width or height on that axis. These gates bound the below-IoU fallback only.
    """

    min_iou: float
    min_score: float
    min_containment: float
    min_area_ratio: float
    max_center_distance: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not _unit_interval(value):
                raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True, slots=True)
class AlignmentCandidate:
    sol_index: int
    region_order: int
    iou: float
    containment: float
    area_ratio: float
    center_distance: float
    score: float
    compatible: bool
    proposed: bool = False
    applied: bool = False
    reasons: tuple[Reason, ...] = ()


@dataclass(frozen=True, slots=True)
class SolAlignment:
    sol_index: int
    status: Literal["matched", "sol_only"]
    region_order: int | None
    reasons: tuple[Reason, ...]


@dataclass(frozen=True, slots=True)
class RegionAlignment:
    region: LayoutRegion
    status: Literal["matched", "v3_only"]
    sol_index: int | None
    reasons: tuple[Reason, ...]


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    """Blocks in output order, Sol diagnostics in original zero-based index order.

    ``source_indices`` maps each output block back to its input. Layout and region
    diagnostics are in V3 order; candidates are in deterministic proposal rank.
    Frozen diagnostics do not make the independent Pydantic block copies frozen.
    """

    blocks: tuple[ExtractedBlock, ...]
    source_indices: tuple[int, ...]
    layout: LayoutResult
    policy: AlignmentPolicy | None
    candidates: tuple[AlignmentCandidate, ...]
    sol: tuple[SolAlignment, ...]
    regions: tuple[RegionAlignment, ...]


def _unit_interval(value: float) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def _valid_box(box: Sequence[float], width: float, height: float) -> bool:
    return (
        len(box) == 4
        and all(
            isinstance(v, Real) and not isinstance(v, bool) and math.isfinite(v)
            for v in box
        )
        and 0 <= box[0] < box[2] <= width
        and 0 <= box[1] < box[3] <= height
    )


def _metrics(a: Sequence[float], b: Sequence[float]) -> tuple[float, ...]:
    aw, ah, bw, bh = a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1]
    area_a, area_b = aw * ah, bw * bh
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    distance = max(
        abs((a[0] + a[2] - b[0] - b[2]) / 2) / max(aw, bw),
        abs((a[1] + a[3] - b[1] - b[3]) / 2) / max(ah, bh),
    )
    return (
        intersection / (area_a + area_b - intersection),
        intersection / min(area_a, area_b),
        min(area_a, area_b) / max(area_a, area_b),
        distance,
    )


def _center_contained(a: Sequence[float], b: Sequence[float]) -> bool:
    if (a[2] - a[0]) * (a[3] - a[1]) > (b[2] - b[0]) * (b[3] - b[1]):
        a, b = b, a
    return b[0] <= (a[0] + a[2]) / 2 <= b[2] and b[1] <= (a[1] + a[3]) / 2 <= b[3]


def _quality(c: AlignmentCandidate) -> tuple[float, ...]:
    return (-c.iou, -c.containment, c.center_distance, -c.score)


def _anchored_order(
    count: int,
    matches: dict[int, int],
    reasons: list[set[Reason]],
) -> tuple[int, ...]:
    if not matches:
        return tuple(range(count))
    anchors = sorted(matches)
    bundles = {anchor: [anchor] for anchor in anchors}
    bundles[anchors[0]][:0] = range(anchors[0])
    for pos, anchor in enumerate(anchors):
        following = anchors[pos + 1] if pos + 1 < len(anchors) else count
        run = range(anchor + 1, following)
        bundles[anchor].extend(run)
        if following < count and matches[anchor] > matches[following]:
            for index in run:
                reasons[index].add("order_ambiguous")
    return tuple(
        i
        for anchor in sorted(anchors, key=matches.__getitem__)
        for i in bundles[anchor]
    )


def align_blocks(
    blocks: Sequence[ExtractedBlock],
    layout: LayoutResult,
    *,
    policy: AlignmentPolicy | None,
) -> AlignmentResult:
    """Align validated Sol blocks without inference, mutation, or text synthesis.

    Sol indices are zero-based; region order indices retain V3's one-based values.
    Diagnostics are separate from rendered blocks and include every V3 region.
    Proposals are deterministic greedy reservations, not optimal assignments.
    Only isolated compatible, score-qualified pairs are applied. All geometrical
    candidates (including class conflicts/low scores) count towards ambiguity.
    Split means one Sol block to multiple candidate regions; merge means the
    inverse. These are possible cases within the configured candidate gates, not
    a semantic diagnosis of text. Rectangles rejected by the gates stay unmatched.
    """
    width, height = layout.image_size
    if any(
        not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in (width, height)
    ):
        raise ValueError("layout.image_size must contain positive integer dimensions")
    orders = [r.order_index for r in layout.regions]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in orders):
        raise ValueError("V3 order indices must be positive integers")
    if len(set(orders)) != len(orders):
        raise ValueError("V3 order indices must be unique")
    regions = sorted(layout.regions, key=lambda r: r.order_index)
    if policy is None:
        for i, block in enumerate(blocks):
            if not _valid_box(block.bbox, 1000, 1000):
                raise ValueError(f"Sol block {i} must have a validated normalized box")
        return AlignmentResult(
            tuple(block.model_copy(deep=True) for block in blocks),
            tuple(range(len(blocks))),
            replace(layout, regions=tuple(regions)),
            None,
            (),
            tuple(
                SolAlignment(
                    i,
                    "sol_only",
                    None,
                    (
                        "layout_unavailable"
                        if layout.error_code
                        else "policy_not_configured",
                    ),
                )
                for i in range(len(blocks))
            ),
            tuple(
                RegionAlignment(r, "v3_only", None, ("policy_not_configured",))
                for r in regions
            ),
        )
    region_map = {r.order_index: r for r in regions}
    sol_reasons: list[set[Reason]] = [set() for _ in blocks]
    region_reasons: dict[int, set[Reason]] = {r.order_index: set() for r in regions}
    valid_regions = []
    for r in regions:
        reasons = region_reasons[r.order_index]
        if not _valid_box(r.bbox, width, height) or not _unit_interval(r.score):
            reasons.add("invalid_region")
            continue
        if (
            not isinstance(r.class_id, int)
            or isinstance(r.class_id, bool)
            or (r.class_id, r.label) not in CLASS_COMPATIBILITY
        ):
            reasons.add("unsupported_class")
        if r.score < policy.min_score:
            reasons.add("low_score")
        valid_regions.append(r)

    candidates: list[AlignmentCandidate] = []
    by_sol: list[list[int]] = [[] for _ in blocks]
    by_region: dict[int, list[int]] = {r.order_index: [] for r in regions}
    # ponytail: O(S*R) per page; spatial indexing only if dense pages warrant it.
    for i, block in enumerate(blocks):
        if not _valid_box(block.bbox, 1000, 1000):
            raise ValueError(f"Sol block {i} must have a validated normalized box")
        box = [
            v * (width if j % 2 == 0 else height) / 1000
            for j, v in enumerate(block.bbox)
        ]
        for r in valid_regions:
            iou, containment, ratio, distance = _metrics(box, r.bbox)
            fallback = (
                containment >= policy.min_containment
                and ratio >= policy.min_area_ratio
                and distance <= policy.max_center_distance
                and _center_contained(box, r.bbox)
            )
            if iou <= 0 or not (iou >= policy.min_iou or fallback):
                continue
            reasons = region_reasons[r.order_index].copy()
            compatible = (
                block.block_type
                in CLASS_COMPATIBILITY.get((r.class_id, r.label), frozenset())
                and "unsupported_class" not in reasons
            )
            if not compatible:
                reasons.add("class_conflict")
            by_sol[i].append(len(candidates))
            by_region[r.order_index].append(len(candidates))
            candidates.append(
                AlignmentCandidate(
                    i,
                    r.order_index,
                    iou,
                    containment,
                    ratio,
                    distance,
                    r.score,
                    compatible,
                    reasons=tuple(sorted(reasons)),
                )
            )

    # Connected components propagate split/merge flags across many-to-many cases.
    seen: set[int] = set()
    for start in range(len(candidates)):
        if start in seen:
            continue
        pending, component = [start], set()
        flags: set[Reason] = set()
        while pending:
            index = pending.pop()
            if index in component:
                continue
            component.add(index)
            c = candidates[index]
            for neighbors, flag in (
                (by_sol[c.sol_index], "split"),
                (by_region[c.region_order], "merge"),
            ):
                if len(neighbors) > 1:
                    flags.add("split" if flag == "split" else "merge")
                    if len({_quality(candidates[n]) for n in neighbors}) < len(
                        neighbors
                    ):
                        flags.add("tie")
                pending.extend(n for n in neighbors if n not in component)
        seen.update(component)
        if len(component) > 1:
            flags.add("ambiguous")
        for index in component:
            c = candidates[index]
            reasons = tuple(sorted(set(c.reasons) | flags))
            candidates[index] = replace(c, reasons=reasons, applied=not reasons)

    ranked = sorted(
        candidates, key=lambda c: (*_quality(c), c.sol_index, c.region_order)
    )
    reserved_sol: set[int] = set()
    reserved_regions: set[int] = set()
    matches: dict[int, int] = {}
    for index, c in enumerate(ranked):
        if (
            c.compatible
            and c.score >= policy.min_score
            and c.sol_index not in reserved_sol
            and c.region_order not in reserved_regions
        ):
            ranked[index] = replace(c, proposed=True)
            reserved_sol.add(c.sol_index)
            reserved_regions.add(c.region_order)
        if c.applied:
            matches[c.sol_index] = c.region_order
        sol_reasons[c.sol_index].update(c.reasons)
        region_reasons[c.region_order].update(c.reasons)
    for i, edges in enumerate(by_sol):
        if not edges:
            sol_reasons[i].add("no_candidate")
    for order, edges in by_region.items():
        if not edges:
            region_reasons[order].add("no_candidate")

    indices = _anchored_order(len(blocks), matches, sol_reasons)
    output = []
    for i in indices:
        block = blocks[i].model_copy(deep=True)
        if i in matches:
            block.bbox = [
                v / (width if j % 2 == 0 else height) * 1000
                for j, v in enumerate(region_map[matches[i]].bbox)
            ]
            ExtractedBlock.valid_bbox(block.bbox)
        output.append(block)
    reverse_matches = {order: i for i, order in matches.items()}
    return AlignmentResult(
        tuple(output),
        indices,
        replace(layout, regions=tuple(regions)),
        policy,
        tuple(ranked),
        tuple(
            SolAlignment(
                i,
                "matched" if i in matches else "sol_only",
                matches.get(i),
                tuple(sorted(sol_reasons[i])),
            )
            for i in range(len(blocks))
        ),
        tuple(
            RegionAlignment(
                r,
                "matched" if r.order_index in reverse_matches else "v3_only",
                reverse_matches.get(r.order_index),
                tuple(sorted(region_reasons[r.order_index])),
            )
            for r in regions
        ),
    )
