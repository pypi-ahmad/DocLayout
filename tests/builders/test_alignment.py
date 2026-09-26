"""Synthetic alignment contracts; fixture thresholds are not calibration evidence."""

import subprocess
import sys
from dataclasses import replace
from itertools import permutations
from typing import Any, cast
from unittest.mock import Mock

import pytest
from PIL import Image

from doclayout.builders.alignment import (
    CLASS_COMPATIBILITY,
    AlignmentPolicy,
    AlignmentResult,
    align_blocks,
)
from doclayout.builders.structure import StructureBuilder
from doclayout.processors.footnote import FootnoteProcessor
from doclayout.processors.page_header import PageHeaderProcessor
from doclayout.processors.sectionheader import SectionHeaderProcessor
from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.json import JSONRenderer
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import SectionHeader
from doclayout.schema.document import Document
from doclayout.schema.extraction import ExtractedBlock
from doclayout.schema.groups.page import PageGroup
from doclayout.schema.polygon import PolygonBox
from doclayout.schema.registry import get_block_class
from doclayout.services.layout import (
    MODEL_ID,
    MODEL_REVISION,
    LayoutRegion,
    LayoutResult,
)
from doclayout.ui.exports import annotations

# Deliberately explicit, synthetic values. Production callers must evaluate theirs.
POLICY = AlignmentPolicy(
    min_iou=0.6,
    min_score=0.5,
    min_containment=0.8,
    min_area_ratio=0.25,
    max_center_distance=0.4,
)
BOX = (100.0, 100.0, 300.0, 200.0)


def sol(box=BOX, kind="Text", html="<p>Unique words</p>") -> ExtractedBlock:
    return ExtractedBlock.model_validate(
        {"bbox": list(box), "block_type": kind, "html": html}
    )


def region(box=BOX, order=1, class_id=22, label="text", score=0.9) -> LayoutRegion:
    return LayoutRegion(class_id, label, score, tuple(box), order)


def layout(*regions: LayoutRegion, size=(1000, 1000)) -> LayoutResult:
    return LayoutResult(
        MODEL_ID, MODEL_REVISION, "cpu", "CPUExecutionProvider", 0.1, size, regions
    )


def aligned(blocks, *regions, policy=POLICY, size=(1000, 1000)) -> AlignmentResult:
    return align_blocks(blocks, layout(*regions, size=size), policy=policy)


def document_from(result: AlignmentResult) -> Document:
    """Mirror DocumentBuilder's insertion contract, without activating alignment."""
    image = Image.new("RGB", result.layout.image_size, "white")
    page = PageGroup(
        page_id=0,
        polygon=PolygonBox.from_bbox([0, 0, 500, 800]),
        children=[],
        structure=[],
        lowres_image=image,
        highres_image=image,
    )
    for item in result.blocks:
        block = page.add_block(
            get_block_class(BlockTypes[item.block_type]),
            PolygonBox.from_bbox(item.bbox).rescale((1000, 1000), page.polygon.size),
        )
        # Registry subclasses expose HTML; their common Block base does not.
        cast(Any, block).html = item.html
        block.text_extraction_method = "openai"
        page.add_structure(block)
    return Document(filepath="synthetic.pdf", pages=[page])


def test_non_square_pixel_conversion_and_no_mutation():
    original = sol()
    before = original.model_dump()
    r = region((202.5, 50.5, 599.5, 99.5))
    result = aligned([original], r, size=(2000, 500))
    assert result.sol[0].status == result.regions[0].status == "matched"
    assert result.blocks[0].bbox == pytest.approx([101.25, 101, 299.75, 199])
    assert original.model_dump() == before
    assert result.blocks[0].html == original.html
    assert result.blocks[0] is not original
    assert result.blocks[0].bbox is not original.bbox
    assert result.layout.model_id == MODEL_ID
    assert result.layout.revision == MODEL_REVISION
    assert result.regions[0].region is r
    assert r.as_polygon_box().polygon == [
        [202.5, 50.5],
        [599.5, 50.5],
        [599.5, 99.5],
        [202.5, 99.5],
    ]
    assert not hasattr(r, "polygon")


@pytest.mark.parametrize("box", [(301, 100, 500, 200), (300, 100, 500, 200)])
def test_disjoint_and_touching_never_match_even_with_zero_thresholds(box):
    result = aligned([sol()], region(box), policy=AlignmentPolicy(0, 0, 0, 0, 1))
    assert result.candidates == ()
    assert result.sol[0].status == "sol_only"
    assert result.regions[0].status == "v3_only"
    assert result.blocks[0] == sol()


def test_threshold_is_required_and_changes_candidate_acceptance():
    with pytest.raises(TypeError, match="policy"):
        # Check the public call boundary, including its required keyword.
        sys.modules[align_blocks.__module__].align_blocks([sol()], layout(region()))
    a, b = sol((0, 0, 100, 100)), region((50, 0, 150, 100))
    strict = replace(POLICY, min_containment=1, min_area_ratio=1, max_center_distance=0)
    assert not aligned([a], b, policy=strict).candidates
    assert (
        aligned([a], b, policy=replace(strict, min_iou=0.3)).sol[0].status == "matched"
    )


def test_containment_fallback_is_bounded_by_area_and_center():
    a = sol((200, 200, 400, 400))
    b = region((100, 100, 500, 500))
    assert aligned([a], b).sol[0].status == "matched"  # IoU .25, coverage 1.
    assert not aligned([a], b, policy=replace(POLICY, min_area_ratio=0.3)).candidates
    assert not aligned([a], region((0, 0, 1000, 1000))).candidates
    off_center = region((200, 200, 600, 600))
    assert not aligned(
        [a], off_center, policy=replace(POLICY, max_center_distance=0.1)
    ).candidates


def test_fallback_requires_smaller_center_inside_larger():
    a = sol((0, 0, 100, 100))
    b = region((90, 0, 200, 100))
    permissive = AlignmentPolicy(1, 0, 0, 0, 1)
    assert not aligned([a], b, policy=permissive).candidates


def test_two_column_order_is_not_top_left_sort_and_is_permutation_stable():
    boxes = [
        (100, 100, 400, 200),
        (600, 100, 900, 200),
        (100, 300, 400, 400),
        (600, 300, 900, 400),
    ]
    blocks = [sol(box, html=f"<p>Token{i}</p>") for i, box in enumerate(boxes)]
    regions = [region(box, order) for box, order in zip(boxes, [1, 3, 2, 4])]
    result = aligned(blocks, *regions)
    assert result.source_indices == (0, 2, 1, 3)
    assert [b.html for b in result.blocks] == [blocks[i].html for i in [0, 2, 1, 3]]
    for shuffled in permutations(regions):
        assert aligned(blocks, *shuffled) == result
    assert len({c.sol_index for c in result.candidates if c.applied}) == 4
    assert len({c.region_order for c in result.candidates if c.applied}) == 4


def test_split_retains_sol_and_diagnostic_proposal_does_not_duplicate_words():
    a = sol((0, 0, 400, 100))
    result = aligned([a], region((0, 0, 200, 100), 2), region((200, 0, 400, 100), 1))
    assert result.blocks == (a,)
    assert {"split", "ambiguous", "tie"} <= set(result.sol[0].reasons)
    assert [c.region_order for c in result.candidates if c.proposed] == [1]
    assert not any(c.applied for c in result.candidates)
    assert all(r.status == "v3_only" for r in result.regions)


def test_merge_retains_both_sol_blocks_and_stable_sol_tie_break():
    blocks = [sol((0, 0, 200, 100)), sol((200, 0, 400, 100), html="<p>Other words</p>")]
    result = aligned(blocks, region((0, 0, 400, 100)))
    assert result.blocks == tuple(blocks)
    assert all({"merge", "ambiguous", "tie"} <= set(s.reasons) for s in result.sol)
    assert [c.sol_index for c in result.candidates if c.proposed] == [0]


def test_many_to_many_is_explicit_and_proposals_are_one_to_one():
    blocks = [sol(), sol(html="<p>Second block</p>")]
    result = aligned(blocks, region(order=2), region(order=1))
    assert result.blocks == tuple(blocks)
    assert all(
        {"split", "merge", "ambiguous", "tie"} <= set(s.reasons) for s in result.sol
    )
    assert [(c.sol_index, c.region_order) for c in result.candidates if c.proposed] == [
        (0, 1),
        (1, 2),
    ]
    assert not any(c.applied for c in result.candidates)


def test_ambiguous_component_does_not_prevent_an_independent_match():
    blocks = [sol(), sol((600, 600, 800, 800), html="<p>Independent</p>")]
    result = aligned(
        blocks, region(order=1), region(order=2), region((601, 601, 799, 799), 3)
    )
    assert result.sol[0].status == "sol_only"
    assert result.sol[1].status == "matched"
    assert result.blocks[0] == blocks[0]
    assert result.blocks[1].bbox == [601, 601, 799, 799]


def test_split_merge_flags_propagate_through_component():
    blocks = [sol((0, 0, 200, 100)), sol((200, 0, 400, 100))]
    result = aligned(blocks, region((0, 0, 400, 100), 1), region((200, 0, 400, 100), 2))
    assert all({"split", "merge", "ambiguous"} <= set(s.reasons) for s in result.sol)
    assert not any(c.applied for c in result.candidates)


def test_proposal_uses_score_after_equal_geometry():
    result = aligned([sol()], region(order=1, score=0.8), region(order=2, score=0.9))
    assert [c.region_order for c in result.candidates if c.proposed] == [2]
    assert "tie" not in result.sol[0].reasons
    assert result.sol[0].status == "sol_only"


def test_low_score_and_class_conflict_competitors_still_flag_ambiguity():
    for competitor in [
        region(order=2, score=0.1),
        region(order=2, class_id=21, label="table"),
    ]:
        result = aligned([sol()], region(), competitor)
        assert result.blocks == (sol(),)
        assert "ambiguous" in result.sol[0].reasons
        assert not any(c.applied for c in result.candidates)


@pytest.mark.parametrize(
    "r,reason",
    [
        (region(score=0.1), "low_score"),
        (region(class_id=21, label="table"), "class_conflict"),
        (region(class_id=99, label="future"), "unsupported_class"),
        (region(class_id=22, label="image"), "unsupported_class"),
        (region(class_id=22.0), "unsupported_class"),
    ],
)
def test_rejected_pair_preserves_both_sources(r, reason):
    result = aligned([sol()], r)
    assert result.blocks == (sol(),)
    assert result.sol[0].status == "sol_only"
    assert result.regions[0].status == "v3_only"
    assert reason in result.sol[0].reasons
    assert reason in result.regions[0].reasons
    assert result.regions[0].region == r


def test_source_anchors_include_prefix_suffix_and_conflicting_internal_run():
    boxes = [(100, i * 100, 300, i * 100 + 50) for i in range(5)]
    blocks = [sol(b, html=f"<p>Token{i}</p>") for i, b in enumerate(boxes)]
    result = aligned(blocks, region(boxes[1], 2), region(boxes[3], 1))
    assert result.source_indices == (3, 4, 0, 1, 2)
    assert "order_ambiguous" in result.sol[2].reasons
    assert all(
        result.blocks[j] == blocks[i] for j, i in enumerate(result.source_indices)
    )
    assert len(result.blocks) == len(blocks)


@pytest.mark.parametrize(
    "blocks,regions,expected",
    [
        ([], [], 0),
        ([], [region(class_id=14, label="image")], 0),
        ([sol(kind="Picture", html="")], [], 1),
        ([sol(kind="Picture", html="")], [region(class_id=14, label="image")], 1),
    ],
)
def test_blank_and_graphic_only_pages(blocks, regions, expected):
    result = aligned(blocks, *regions)
    assert len(result.blocks) == expected
    assert len(result.regions) == len(regions)
    assert len(result.sol) == len(blocks)
    assert len(result.source_indices) == expected


@pytest.mark.parametrize(
    "box",
    [
        (0, 0, 0, 1),
        (2, 0, 1, 2),
        (-1, 0, 1, 1),
        (0, 0, 1001, 1),
        (0, 0, float("nan"), 1),
        (0, 0, float("inf"), 1),
    ],
)
def test_invalid_region_geometry_remains_diagnostic_only(box):
    r = region(box)
    result = aligned([sol()], r)
    assert result.blocks == (sol(),)
    assert result.candidates == ()
    assert "invalid_region" in result.regions[0].reasons
    assert result.regions[0].region is r


@pytest.mark.parametrize("score", [-1, 1.01, float("nan"), float("inf"), True])
def test_invalid_score_is_not_used(score):
    result = aligned([sol()], region(score=score))
    assert not result.candidates
    assert "invalid_region" in result.regions[0].reasons


@pytest.mark.parametrize("size", [(0, 1000), (-1, 1000), (True, 1000), (1000.0, 1000)])
def test_invalid_dimensions_fail_clearly(size):
    with pytest.raises(ValueError, match="dimensions"):
        aligned([], size=size)


def test_duplicate_and_invalid_order_fail_clearly():
    with pytest.raises(ValueError, match="unique"):
        aligned([], region(), region())
    for order in [0, -1, True, 1.5]:
        with pytest.raises(ValueError, match="positive integers"):
            aligned([], region(order=order))


@pytest.mark.parametrize("field", list(AlignmentPolicy.__dataclass_fields__))
@pytest.mark.parametrize(
    "value", [-0.01, 1.01, float("inf"), float("nan"), True, "0.5"]
)
def test_policy_values_are_validated(field, value):
    with pytest.raises(ValueError, match=field):
        replace(POLICY, **{field: value})


def test_mutated_sol_box_is_rejected_without_mutating_html():
    a = sol()
    a.bbox[0] = float("nan")
    with pytest.raises(ValueError, match="Sol block 0"):
        aligned([a], region())
    assert a.html == "<p>Unique words</p>"


RICH = "Text SectionHeader Code ListGroup Bibliography TableOfContents Equation ChemicalBlock"
GRAPHICS = "Picture Figure Diagram"
EXPECTED_CLASSES = [
    ("abstract", RICH),
    ("algorithm", "Code Text ListGroup"),
    ("aside_text", RICH),
    ("chart", GRAPHICS),
    ("content", "TableOfContents Text ListGroup"),
    ("display_formula", "Equation ChemicalBlock"),
    ("doc_title", "SectionHeader Text"),
    ("figure_title", "Caption Text"),
    ("footer", "PageFooter"),
    ("footer_image", GRAPHICS),
    ("footnote", "Footnote Caption Text"),
    ("formula_number", "Text"),
    ("header", "PageHeader"),
    ("header_image", GRAPHICS),
    ("image", GRAPHICS),
    ("inline_formula", "Equation Text"),
    ("number", "PageHeader PageFooter Text"),
    ("paragraph_title", "SectionHeader Text"),
    ("reference", "Bibliography SectionHeader Text"),
    ("reference_content", "Bibliography SectionHeader Text"),
    ("seal", GRAPHICS),
    ("table", "Table Form TableOfContents"),
    ("text", RICH),
    ("vertical_text", RICH),
    ("vision_footnote", "Footnote Caption Text"),
]


def test_all_25_class_permissions_are_explicit():
    assert dict(CLASS_COMPATIBILITY) == {
        (i, label): frozenset(kinds.split())
        for i, (label, kinds) in enumerate(EXPECTED_CLASSES)
    }


@pytest.mark.parametrize(
    "class_id,label,kind",
    [
        (i, label, kind)
        for i, (label, kinds) in enumerate(EXPECTED_CLASSES)
        for kind in kinds.split()
    ],
)
def test_every_allowed_pair_keeps_original_sol_type(class_id, label, kind):
    a = sol(kind=kind)
    result = aligned([a], region(class_id=class_id, label=label))
    assert result.sol[0].status == "matched"
    assert result.blocks[0].block_type == kind
    assert result.blocks[0].html == a.html
    assert result.regions[0].region.class_id == class_id
    assert result.regions[0].region.label == label
    assert result.regions[0].region.score == 0.9


@pytest.mark.parametrize(
    "kind,html,class_id,label",
    [
        ("SectionHeader", "<h4>Fourth level</h4>", 17, "paragraph_title"),
        ("ListGroup", '<ol start="3"><li>Three</li><li>Four</li></ol>', 22, "text"),
        (
            "Table",
            '<table><tr><th colspan="2">Title</th></tr><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>',
            21,
            "table",
        ),
        ("Equation", '<math display="block">x^2</math>', 5, "display_formula"),
        ("Code", "<pre><code>print(1)</code></pre>", 1, "algorithm"),
        ("Text", '<p>Text <math display="inline">x</math></p>', 15, "inline_formula"),
    ],
)
def test_rich_html_is_byte_preserved(kind, html, class_id, label):
    a = sol(kind=kind, html=html)
    result = aligned([a], region((101, 101, 299, 199), class_id=class_id, label=label))
    assert result.sol[0].status == "matched"
    assert result.blocks[0].html == a.html
    assert result.blocks[0].block_type == kind
    assert result.blocks[0].bbox != a.bbox


def test_import_and_alignment_do_not_require_layout_extra():
    code = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'onnxruntime', 'paddleocr', 'paddlex', 'huggingface_hub'}:
            raise AssertionError('Optional inference dependency imported: ' + fullname)
sys.meta_path.insert(0, BlockOptional())
import doclayout
from doclayout.builders.alignment import AlignmentPolicy, align_blocks
from doclayout.services.layout import LayoutResult
r = LayoutResult('test', 'test', 'cpu', 'CPUExecutionProvider', 0, (100, 100), ())
assert not align_blocks([], r, policy=AlignmentPolicy(.5, .5, .8, .25, .4)).blocks
"""
    process = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_ids_json_chunks_and_annotations_consume_aligned_leaf_geometry():
    blocks = [sol(), sol((600, 100, 900, 200), html="<p>Right column</p>")]
    result = aligned(
        blocks, region((101, 101, 299, 199), 2), region((601, 101, 899, 199), 1)
    )
    doc = document_from(result)
    page = doc.pages[0]
    StructureBuilder()(doc)
    assert page.children is not None and page.structure is not None
    for i, block in enumerate(page.children):
        assert block.block_id == i
        assert page.get_block(block.id) is block
    json_blocks = JSONRenderer()(doc).children[0].children
    assert json_blocks is not None
    chunks = ChunkRenderer()(doc).blocks
    for i, item in enumerate(result.blocks):
        expected = PolygonBox.from_bbox(item.bbox).rescale(
            (1000, 1000), page.polygon.size
        )
        assert json_blocks[i].bbox == pytest.approx(expected.bbox)
        assert chunks[i].bbox == pytest.approx(expected.bbox)
        assert chunks[i].id == str(page.structure[i])
        assert item.html in chunks[i].html
    drawn = annotations(doc)
    assert drawn["drawn"] == 2 and drawn["skipped"] == 0
    assert drawn["pages"][1].getpixel((601, 150)) == (220, 30, 30)


def test_caption_group_changes_chunk_box_but_not_v3_leaf_boxes():
    figure = sol((100, 100, 400, 400), "Figure", "")
    caption = sol((100, 405, 400, 450), "Caption", "<p>Distinct caption</p>")
    result = aligned(
        [figure, caption],
        region(figure.bbox, 1, 14, "image"),
        region(caption.bbox, 2, 7, "figure_title"),
    )
    doc = document_from(result)
    page = doc.pages[0]
    assert page.children is not None
    leaves = list(page.children)
    before = [b.polygon.bbox[:] for b in leaves]
    StructureBuilder()(doc)
    assert [b.polygon.bbox for b in leaves] == before
    assert page.structure is not None and len(page.structure) == 1
    group = page.get_block(page.structure[0])
    assert group is not None
    assert group.polygon.bbox == pytest.approx([50, 80, 200, 360])
    chunks = ChunkRenderer()(doc).blocks
    assert len(chunks) == 1 and chunks[0].bbox == group.polygon.bbox
    assert chunks[0].html.count("Distinct caption") == 1
    assert annotations(doc)["drawn"] == 2


def test_furniture_processors_override_v3_order_without_renumbering_ids():
    kinds = ["Footnote", "Text", "PageHeader", "PageFooter"]
    classes = [(10, "footnote"), (22, "text"), (12, "header"), (8, "footer")]
    blocks = [
        sol((100, 100 + i * 100, 400, 150 + i * 100), k) for i, k in enumerate(kinds)
    ]
    result = aligned(
        blocks, *(region(b.bbox, i + 1, *classes[i]) for i, b in enumerate(blocks))
    )
    assert all(s.status == "matched" for s in result.sol)
    doc = document_from(result)
    page = doc.pages[0]
    assert page.structure is not None
    original = list(page.structure)
    FootnoteProcessor()(doc)
    PageHeaderProcessor()(doc)
    assert page.structure == [original[2], original[1], original[3], original[0]]
    assert page.children is not None
    assert [b.id for b in page.children] == original


def test_heading_level_and_html_lists_survive_structure_processing():
    blocks = [
        sol(kind="SectionHeader", html="<h4>Keep level</h4>"),
        sol((100, 300, 400, 400), "ListGroup", "<ul><li>Keep list</li></ul>"),
    ]
    result = aligned(blocks, region(), region(blocks[1].bbox, 2))
    doc = document_from(result)
    StructureBuilder()(doc)
    SectionHeaderProcessor()(doc)
    page = doc.pages[0]
    assert page.children is not None
    assert isinstance(page.children[0], SectionHeader)
    assert page.children[0].heading_level == 4
    assert [getattr(b, "html", None) for b in page.children] == [b.html for b in blocks]


def test_optional_page_correction_can_override_aligned_order():
    from doclayout.processors.llm.llm_page_correction import LLMPageCorrectionProcessor

    blocks = [sol(), sol((100, 300, 400, 400), html="<p>Second</p>")]
    result = aligned(blocks, region(), region(blocks[1].bbox, 2))
    doc = document_from(result)
    page = doc.pages[0]
    assert page.structure is not None
    original = list(page.structure)
    service = Mock(
        return_value={
            "correction_type": "reorder",
            "blocks": [{"id": str(b)} for b in reversed(original)],
        }
    )
    processor = LLMPageCorrectionProcessor(
        service, {"use_llm": True, "block_correction_prompt": "Reorder"}
    )
    processor.process_rewriting(doc, page)
    assert page.structure == list(reversed(original))
    service.assert_called_once()
    assert result.source_indices == (0, 1)


def test_optional_table_merge_combines_html_without_expanding_rectangle():
    from doclayout.processors.llm.llm_table_merge import LLMTableMergeProcessor

    blocks = [
        sol(
            (100, 100, 400, 300), "Table", "<table><tr><td>First row</td></tr></table>"
        ),
        sol(
            (100, 310, 400, 500), "Table", "<table><tr><td>Second row</td></tr></table>"
        ),
    ]
    result = aligned(
        blocks, *(region(b.bbox, i + 1, 21, "table") for i, b in enumerate(blocks))
    )
    doc = document_from(result)
    page = doc.pages[0]
    assert page.children is not None
    before = [b.polygon.bbox[:] for b in page.children]
    service = Mock(return_value={"merge": "true", "direction": "bottom"})
    processor = LLMTableMergeProcessor(service, {"use_llm": True})
    processor.process_rewriting(doc, page.children)
    service.assert_called_once()
    assert [b.polygon.bbox for b in page.children] == before
    assert page.children[1].ignore_for_output
    merged_html = getattr(page.children[0], "html", "")
    assert merged_html.count("First row") == merged_html.count("Second row") == 1
    assert "Second row" not in result.blocks[0].html
    # Annotations now follow rendered membership, including ignored leaves.
    assert annotations(doc)["drawn"] == 1


def test_blank_and_v3_only_graphic_results_are_safe_for_consumers():
    result = aligned([], region(class_id=14, label="image"))
    doc = document_from(result)
    StructureBuilder()(doc)
    assert JSONRenderer()(doc).children[0].children == []
    assert ChunkRenderer()(doc).blocks == []
    assert annotations(doc)["drawn"] == 0
    assert result.regions[0].status == "v3_only"


def test_result_copies_are_independent_of_each_other_and_inputs():
    block = sol()
    result = aligned([block, block])
    result.blocks[0].bbox[0] = 101
    assert result.blocks[1].bbox == block.bbox == list(BOX)
