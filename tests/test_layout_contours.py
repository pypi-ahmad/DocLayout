"""Independent contour fixtures and offline end-to-end ownership regressions."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from doclayout import layout
from doclayout.builders.document import DocumentBuilder
from doclayout.builders.structure import StructureBuilder
from doclayout.layout_geometry import (
    mask_from_rle,
    polygon_parts,
    region_geometry,
    transform_points,
)
from doclayout.processors.block_relabel import BlockRelabelProcessor
from doclayout.processors.list import ListProcessor
from doclayout.processors.llm.llm_page_correction import LLMPageCorrectionProcessor
from doclayout.processors.llm.llm_table import LLMTableProcessor
from doclayout.processors.llm.llm_table_merge import LLMTableMergeProcessor
from doclayout.processors.marginalia import MarginaliaProcessor
from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.schema.extraction import PAGE_PROMPT
from doclayout.schema.layout import (
    BlockLayout,
    LayoutAnalysis,
    LayoutRegion,
    SourceRegion,
)
from doclayout.schema.polygon import PolygonBox
from doclayout.schema.text.line import Line
from doclayout.schema.text.span import Span
from doclayout.ui.exports import annotations

FIXTURES = json.loads(
    (Path(__file__).parent / "data/layout_v3_contours.json").read_text()
)["cases"]
L_SHAPE = [[0, 0], [60, 0], [60, 20], [20, 20], [20, 60], [0, 60]]


def region(bbox=(0, 0, 60, 60), *, contour=L_SHAPE, row=0, kind=22, order=7, score=0.9):
    return LayoutRegion(
        row=row,
        class_id=kind,
        label=layout.LABELS[kind],
        score=score,
        raw_bbox_px=list(bbox),
        bbox_px=list(bbox),
        order_key=order,
        contour_px=contour,
        contour_status="valid" if contour else "not_decoded",
    )


def analysis(regions, size=(100, 100)):
    return LayoutAnalysis(
        image_size=size,
        model_id=layout.REPO,
        model_revision=layout.REVISION,
        actual_device="cpu",
        provider="CPUExecutionProvider",
        elapsed_ms=0,
        candidate_count=len(regions),
        filtered_count=0,
        regions=regions,
    )


def block(bbox=(0, 0, 600, 600), *, kind="Text", html="<p>Keep all wording</p>"):
    return {"bbox": list(bbox), "block_type": kind, "html": html}


@pytest.fixture
def build():
    images = []

    def make(
        regions,
        blocks,
        *,
        bounds=(10, 20, 210, 320),
        page_ids=(0,),
        size=(100, 100),
        engine=None,
    ):
        image = Image.new("RGB", size, "white")
        images.append(image)
        provider = SimpleNamespace(
            filepath="fixture.pdf",
            page_range=page_ids,
            get_images=lambda *_: [image],
            get_page_bbox=lambda _: PolygonBox.from_bbox(list(bounds)),
            get_page_refs=lambda _: [],
        )
        service = Mock(return_value={"blank": not blocks, "blocks": blocks})
        engine = engine or SimpleNamespace(
            analyze=Mock(return_value=analysis(regions, size))
        )
        document = DocumentBuilder({"page_concurrency": 1})(provider, service, engine)
        return document, service

    yield make
    for image in images:
        image.close()


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda case: case["name"])
def test_decode_matches_independent_paddlex_reference(fixture):
    masks = np.zeros((1, 200, 200), dtype=np.int32)
    for x0, y0, x1, y1 in fixture["rects"]:
        masks[0, y0:y1, x0:x1] = 1
    boxes = np.array([[22, 0.9, *fixture["bbox"], -12.75]], dtype=np.float32)
    result = layout.decode_outputs(
        [boxes, np.array([1], dtype=np.int32), masks], tuple(fixture["size"]), 3, "test"
    )
    item = result.regions[0]
    assert item.contour_px == fixture["expected"]
    assert item.contour_status == "valid" and item.order_key == -12.75
    assert item.observed_rank == 0 and item.raw_bbox_px == fixture["bbox"]
    assert np.array_equal(mask_from_rle(item.mask_rle, item.mask_size), masks[0])
    if fixture["name"] == "outside_page":
        assert "contour_outside_page_vertices" in item.issues
        assert item.bbox_px[0] == 0 and item.contour_px[0][0] == -40


@pytest.mark.parametrize(
    "runs", [[], [39999], [40001], [-1, 40001], [True, 39999], [40000.0]]
)
def test_reject_malformed_rle(runs):
    with pytest.raises(ValueError, match="RLE"):
        mask_from_rle(runs)


def test_empty_mask_keeps_bbox_and_tensor_errors_are_typed():
    boxes = np.array([[22, 0.9, -10, 10, 80, 90, 120.5]], dtype=np.float32)
    outputs = [
        boxes,
        np.array([1], dtype=np.int32),
        np.zeros((1, 200, 200), dtype=np.int32),
    ]
    decoded = layout.decode_outputs(outputs, (100, 200), 0, "test").regions[0]
    assert decoded.eligible and decoded.contour_status == "bbox_fallback"
    assert decoded.bbox_px == [0, 10, 80, 90] and "contour_empty_mask" in decoded.issues
    outputs[2] = np.zeros((2, 200, 200), dtype=np.int32)
    with pytest.raises(layout.LayoutContractError):
        layout.decode_outputs(outputs, (100, 200), 0, "test")


def test_frames_round_trip_nonzero_origin():
    pixels = [[5, 30], [180, 470]]
    page = transform_points(pixels, [0, 0, 200, 500], [10, -20, 410, 1480])
    assert page == [[20, 70], [370, 1390]]
    assert transform_points(page, [10, -20, 410, 1480], [0, 0, 200, 500]) == pixels
    assert transform_points(pixels, [0, 0, 200, 500], [0, 0, 1000, 1000]) == [
        [25, 60],
        [900, 940],
    ]


def test_multirow_evidence_survives_filter_and_order():
    fixture = FIXTURES[0]
    masks = np.zeros((3, 200, 200), dtype=np.int32)
    for x0, y0, x1, y1 in fixture["rects"]:
        masks[2, y0:y1, x0:x1] = 1
    masks[1] = 1
    rows = np.array(
        [
            [22, 0.8, *fixture["bbox"], 91.5],
            [14, 0.4, *fixture["bbox"], 0],
            [6, 0.9, *fixture["bbox"], -12.75],
        ],
        dtype=np.float32,
    )
    result = layout.decode_outputs(
        [rows, np.array([3], dtype=np.int32), masks], tuple(fixture["size"]), 0, "test"
    )
    assert result.filtered_count == 1
    assert [r.row for r in result.regions] == [0, 2]
    assert [r.observed_rank for r in result.regions] == [1, 0]
    for item in result.regions:
        assert np.array_equal(mask_from_rle(item.mask_rle), masks[item.row])
        assert item.class_id == rows[item.row, 0]
        assert item.label == layout.LABELS[item.class_id]
        assert item.score == rows[item.row, 1]
        assert item.raw_bbox_px == rows[item.row, 2:6].tolist()
        assert item.order_key == rows[item.row, 6]
    assert result.regions[0].contour_status == "bbox_fallback"
    assert result.regions[1].contour_px == fixture["expected"]


def test_clipping_keeps_disconnected_components_and_raw_evidence():
    contour = [[-2, 1], [3, 1], [3, 3], [-1, 3], [-1, 5], [3, 5], [3, 7], [-2, 7]]
    item = region((0, 1, 3, 7), contour=contour)
    geometry, source, reason = region_geometry(item, (10, 10))
    assert source == "v3_contour" and reason is None and geometry.area == 12
    assert len(polygon_parts(geometry)) == 2
    result = analysis([item], (10, 10))
    payload = json.loads(layout.extraction_prompt("prompt", result).split("\n\n")[1])[
        "given_layout"
    ]
    assert len(payload["regions"][0]["contours"]) == 2
    assert item.contour_px == contour
    assert all(
        0 <= value <= 1000
        for part in payload["regions"][0]["contours"]
        for point in part
        for value in point
    )


def test_payload_has_no_invented_caps_or_masks():
    result = analysis([region(row=i, order=1000 - i) for i in range(600)])
    payload_text = layout.extraction_prompt("prompt", result).removeprefix("prompt\n\n")
    payload = json.loads(payload_text)["given_layout"]
    assert len(payload["regions"]) == 600 and result.guide_bytes > 65536
    assert (
        result.guide_bytes == len(payload_text.encode())
        and result.guide_vertex_count == 3600
    )
    assert payload["regions"][0]["id"] == "r599"
    assert payload["regions"][0]["order_key"] == 401
    assert "mask" not in payload_text and "rle" not in payload_text


def test_concave_iou_and_text_family_preserve_html(build):
    document, _ = build(
        [region()], [block(kind="SectionHeader", html="<h2>Keep heading</h2>")]
    )
    item = document.pages[0].children[0]
    assert item.layout.iou == pytest.approx(2000 / 3600)
    assert item.layout.match_metric == "contour_iou"
    assert item.layout.geometry_source == "v3_contour"
    assert (
        item.layout.layout_label == "text" and str(item.block_type) == "SectionHeader"
    )
    assert item.html == "<h2>Keep heading</h2>"
    assert "compatible_class_disagreement" in item.layout.issues
    assert item.layout.sources[0].contours == item.layout.contours
    assert item.polygon.bbox == [10, 20, 130, 200]


def test_invalid_contour_falls_back_to_v3_not_sol(build):
    crossed = [[0, 0], [60, 60], [0, 60], [60, 0]]
    document, _ = build([region(contour=crossed)], [block((0, 0, 550, 550))])
    item = document.pages[0].children[0]
    assert item.layout.status == "matched" and item.layout.geometry_source == "v3_bbox"
    assert item.layout.match_metric == "aabb_iou" and item.layout.contours == []
    assert "contour_invalid_polygon" in item.layout.issues
    assert item.polygon.bbox == [10, 20, 130, 200]


def test_greedy_reserves_endpoints_and_keeps_all_text(build):
    document, _ = build(
        [
            region(contour=None, row=9, score=0.8),
            region(contour=None, row=2, score=0.9),
        ],
        [
            block(html="<p>First</p>"),
            block(html="<p>Second</p>"),
            block(html="<p>Third</p>"),
        ],
    )
    a, b, c = document.pages[0].children
    assert [a.layout.region_row, b.layout.region_row, c.layout.region_row] == [
        2,
        9,
        None,
    ]
    assert "qualified_region_reserved" in c.layout.issues
    assert "matching_score_tie" in a.layout.issues
    assert "merged_sol_content_may_extend_beyond_assigned_region" in a.layout.issues
    text = MarkdownRenderer()(document).markdown
    assert all(text.count(word) == 1 for word in ("First", "Second", "Third"))


def test_family_guard_keeps_incompatible_content(build):
    document, _ = build([region(kind=21)], [block()])
    item = document.pages[0].children[0]
    assert (
        item.layout.status == "sol_only"
        and "no_compatible_v3_class" in item.layout.issues
    )
    assert document.layout.pages[0].regions[0].issues == [
        "unmatched_v3",
        "no_compatible_sol_class",
    ]
    assert "Keep all wording" in MarkdownRenderer()(document).markdown


def test_replacement_retains_html_and_source_geometry(build):
    document, _ = build([region()], [block()])
    original = document.pages[0].children[0]
    source = original.layout.sources[0].model_dump()
    BlockRelabelProcessor({"block_relabel_str": "Text:Caption:0.9"})(document)
    layout.finalize_layout(document)
    replacement = document.get_block(document.pages[0].structure[0])
    assert replacement.html == original.html and original.removed
    assert replacement.layout.sources[0].model_dump() == source
    assert replacement.layout.geometry_source == "source_footprints"


def test_processor_geometry_reversion_cannot_override_v3(build):
    document, _ = build([region()], [block()])
    item = document.pages[0].children[0]
    item.polygon = PolygonBox.from_bbox([12, 23, 50, 70])
    layout.finalize_layout(document)
    assert item.polygon.bbox == item.layout.initial_bbox
    assert "processor_geometry_change_ignored" in item.layout.issues


def test_optional_reordering_cannot_override_matched_order(build):
    document, _ = build([region()], [block(), block((700, 700, 900, 900))])
    page = document.pages[0]
    before = page.structure.copy()
    processor = LLMPageCorrectionProcessor(Mock(), {"use_llm": True})
    processor.handle_reorder([{"id": str(bid)} for bid in reversed(before)], page)
    assert page.structure == before


def test_visibility_uses_v3_furniture_without_state_leaks(build):
    document, _ = build([region(kind=12)], [block()])
    item = document.pages[0].children[0]
    original = item.model_dump()
    assert "Keep all wording" not in MarkdownRenderer()(document).markdown
    assert (
        "Keep all wording"
        in MarkdownRenderer({"keep_pageheader_in_output": True})(document).markdown
    )
    assert "Keep all wording" not in MarkdownRenderer()(document).markdown
    assert item.model_dump() == original and str(item.block_type) == "Text"
    for keep in (False, True):
        output = annotations(document, {"keep_pageheader_in_output": keep})
        assert output["drawn"] == int(keep)
        for image in output["pages"].values():
            image.close()


def test_v3_body_not_hidden_by_sol_header_or_marginalia(build):
    document, _ = build([region()], [block(kind="PageHeader")])
    MarginaliaProcessor()(document)
    assert "Keep all wording" in MarkdownRenderer()(document).markdown


def test_contour_drawing_and_source_image_ownership(build, monkeypatch):
    document, _ = build([region()], [block()])
    lines, rectangles = [], []
    monkeypatch.setattr(
        ImageDraw.ImageDraw, "line", lambda self, xy, **kwargs: lines.append(xy)
    )
    monkeypatch.setattr(
        ImageDraw.ImageDraw,
        "rectangle",
        lambda self, xy, **kwargs: rectangles.append(xy),
    )
    result = annotations(document)
    assert result["drawn"] == 1 and not rectangles and len(lines[0]) == 7
    assert set(lines[0]) == {tuple(p) for p in L_SHAPE}
    assert document.pages[0].highres_image.getpixel((0, 0)) == (255, 255, 255)
    assert result["pdf"].startswith(b"%PDF")
    for image in result["pages"].values():
        image.close()


def test_cross_page_table_merge_preserves_two_source_contours(build):
    table = block(kind="Table", html="<table><tr><td>Cell</td></tr></table>")
    document, _ = build([region(kind=21)], [table], page_ids=(0, 1))
    tables = [page.children[0] for page in document.pages]
    original = [table.layout.sources[0].model_dump() for table in tables]
    service = Mock(return_value={"merge": "true", "direction": "bottom"})
    LLMTableMergeProcessor(service, {"use_llm": True}).process_rewriting(
        document, tables
    )
    layout.finalize_layout(document)
    assert service.call_count == 1 and tables[0].html.count("Cell") == 2
    assert [source.model_dump() for source in tables[0].layout.sources] == original
    chunks = ChunkRenderer()(document)
    assert chunks.metadata["layout"]["blocks"][str(tables[0].id)]["multi_page"]
    result = annotations(document)
    assert result["drawn"] == 2 and len(result["pages"]) == 2
    for image in result["pages"].values():
        image.close()


def test_success_empty_and_failure_pages_are_independent(build):
    engine = SimpleNamespace(
        analyze=Mock(
            side_effect=[
                analysis([region()]),
                analysis([]),
                layout.LayoutModelUnavailable("private backend details"),
            ]
        )
    )
    document, service = build([], [block()], engine=engine, page_ids=(0, 1, 2))
    runtime = document.layout.page_runtime
    assert [runtime[i].status for i in range(3)] == [
        "available",
        "available",
        "sol_fallback",
    ]
    assert runtime[0].matched_count == 1 and runtime[1].matched_count == 0
    assert runtime[1].guide_bytes > 0 and runtime[2].guide_bytes == 0
    assert service.call_args_list[2].args[0] == PAGE_PROMPT
    assert "empty_detection_result" in document.pages[1].children[0].layout.issues
    assert document.pages[2].children[0].layout.issues == [
        "layout_unavailable",
        "layout_inference_failed",
    ]


def test_saved_layout_records_without_contours_remain_readable():
    old_source = SourceRegion.model_validate(
        {"block_id": "/page/0/Text/0", "page_id": 0, "bbox": [1, 2, 3, 4]}
    )
    old_record = BlockLayout.model_validate(
        {"status": "sol_only", "sources": [old_source.model_dump()]}
    )
    assert (
        old_record.contours == []
        and old_record.sources[0].geometry_source == "legacy_bbox"
    )
    assert len(PolygonBox.from_bbox([0, 0, 10, 10]).polygon) == 4
    old_processor = BlockLayout.model_validate(
        {
            "status": "processor",
            "geometry_source": "processor",
            "sources": [old_source.model_dump()],
        }
    )
    assert old_processor.geometry_source == "source_footprints"
    old_region = LayoutRegion.model_validate(
        {
            "row": 0,
            "class_id": 22,
            "label": "text",
            "score": 0.9,
            "raw_bbox_px": [1, 2, 3, 4],
            "bbox_px": [1, 2, 3, 4],
            "order_key": 100.5,
            "mask_rle": [40000],
        }
    )
    assert old_region.contour_status == "not_decoded" and old_region.contour_px is None


def test_grouped_output_retains_multiple_contours(build):
    table = region((0, 0, 60, 60), kind=21)
    caption = region(
        (0, 61, 60, 70),
        contour=[[0, 61], [60, 61], [60, 70], [0, 70]],
        row=1,
        kind=7,
        order=8,
    )
    document, _ = build(
        [table, caption],
        [
            block(kind="Table", html="<table><tr><td>Cell</td></tr></table>"),
            block((0, 610, 600, 700), kind="Caption"),
        ],
    )
    StructureBuilder()(document)
    layout.finalize_layout(document)
    group = document.get_block(document.pages[0].structure[0])
    assert (
        group.layout.geometry_source == "source_footprints"
        and len(group.layout.sources) == 2
    )
    assert group.layout.contours == []
    final = layout.layout_metadata(document)["final_counts"][0]
    assert final["visible_blocks"] == final["processor_derived_blocks"] == 1
    assert final["geometry_counts"] == {"v3_contour": 2}
    result = annotations(document)
    assert result["drawn"] == 2
    for image in result["pages"].values():
        image.close()


def test_contour_native_failure_does_not_discard_aabb(monkeypatch):
    outputs = [
        np.array([[22, 0.9, 0, 0, 60, 60, 0]], dtype=np.float32),
        np.array([1], dtype=np.int32),
        np.ones((1, 200, 200), dtype=np.int32),
    ]
    monkeypatch.setattr(
        "cv2.findContours",
        Mock(side_effect=cv2.error("private detail")),
    )
    item = layout.decode_outputs(outputs, (100, 100), 0, "test").regions[0]
    assert item.contour_status == "bbox_fallback" and item.eligible
    assert item.bbox_px == [0, 0, 60, 60] and item.issues == ["contour_decode_error"]


def test_pathological_raw_box_has_bounded_contour_resize():
    outputs = [
        np.array([[22, 0.9, -10000, -10000, 10000, 10000, 0]], dtype=np.float32),
        np.array([1], dtype=np.int32),
        np.ones((1, 200, 200), dtype=np.int32),
    ]
    item = layout.decode_outputs(outputs, (100, 100), 0, "test").regions[0]
    assert item.bbox_px == [0, 0, 100, 100] and item.eligible
    assert item.issues == ["contour_resize_exceeds_four_page_pixels"]


def test_global_order_crosses_unmatched_and_records_raw_ties(build):
    detections = [
        region((0, 0, 60, 20), contour=None, row=9, order=81.25),
        region((0, 40, 60, 60), contour=None, row=3, order=-3.75),
        region((0, 80, 60, 100), contour=None, row=1, order=-3.75),
    ]
    blocks = [
        block((0, 0, 600, 200)),
        block((0, 250, 600, 350)),
        block((0, 400, 600, 600)),
        block((0, 800, 600, 1000)),
        block((700, 300, 900, 500)),
    ]
    document, _ = build(detections, blocks)
    page = document.pages[0]
    original_ids = [item.id for item in page.children]
    layout.finalize_layout(document)
    assert page.structure == [original_ids[i] for i in (3, 1, 2, 0, 4)]
    assert [item.id for item in page.children] == original_ids
    assert page.children[2].layout.order_key == -3.75
    assert all("ambiguous_order" in page.children[i].layout.issues for i in (2, 3))


def test_list_split_nesting_and_line_merge_retain_source_footprint(build):
    document, _ = build(
        [region()], [block(kind="ListGroup", html="<ul><li>One</li><li>Two</li></ul>")]
    )
    page = document.pages[0]
    group = page.children[0]
    source = group.layout.sources[0].model_dump()
    group.html, group.structure = None, []
    lines = []
    for bbox, text in [([20, 30, 70, 50], "- One"), ([30, 60, 70, 80], "- Two")]:
        polygon = PolygonBox.from_bbox(bbox)
        line = page.add_block(Line, polygon)
        span = page.add_full_block(
            Span(
                page_id=0,
                polygon=polygon,
                text=text,
                font="fixture",
                font_weight=400,
                font_size=10,
                minimum_position=0,
                maximum_position=len(text),
                formats=["plain"],
            )
        )
        line.add_structure(span)
        group.add_structure(line)
        lines.append(line)
    StructureBuilder().split_list_groups(document, page)
    ListProcessor({})(document)
    layout.finalize_layout(document)
    assert group.layout.sources[0].model_dump() == source
    first = page.get_block(group.structure[0])
    assert any(
        str(page.get_block(bid).block_type) == "ListItem" for bid in first.structure
    )
    assert first.layout.sources[0].model_dump() == source
    assert all(word in MarkdownRenderer()(document).markdown for word in ("One", "Two"))
    lines[0].layout = group.layout.model_copy(deep=True)
    lines[1].layout = group.layout.model_copy(deep=True)
    lines[0].merge(lines[1])
    assert lines[0].layout.sources[0].model_dump() == source
    assert len(lines[0].layout.sources) == 1


def test_generated_table_cells_inherit_evidence_not_cell_contours(build, monkeypatch):
    html = "<table><tr><td>One</td></tr><tr><td>Two</td></tr></table>"
    document, _ = build(
        [region(kind=21)], [block(kind="Table", html=html)], bounds=(0, 0, 100, 100)
    )
    page, table = document.pages[0], document.pages[0].children[0]
    source = table.layout.sources[0].model_dump()
    processor = LLMTableProcessor(Mock(), {"use_llm": True})
    cells = processor.parse_html_table(html, table, page)
    for cell in cells:
        page.add_full_block(cell)
        table.add_structure(cell)
    table.html = None
    replacement_cells = processor.parse_html_table(html, table, page)
    monkeypatch.setattr(
        processor, "rewrite_single_chunk", lambda *args: replacement_cells
    )
    processor.process_rewriting(document, page, table)
    for bid in table.structure:
        cell = page.get_block(bid)
        assert (
            cell.layout.geometry_source == "source_footprints"
            and cell.layout.contours == []
        )
        assert cell.layout.sources[0].model_dump() == source
        assert cell.layout.match_metric is None and cell.layout.order_key is None
    layout.finalize_layout(document)
    assert table.layout.sources[0].model_dump() == source


def test_merged_table_interleaving_is_reported_without_splitting_html(build):
    detections = [
        region((0, 0, 60, 20), contour=None, kind=21, order=0),
        region((0, 30, 60, 50), contour=None, row=1, order=1),
        region((0, 60, 60, 80), contour=None, row=2, kind=21, order=2),
    ]
    document, _ = build(
        detections,
        [
            block(
                (0, 0, 600, 200),
                kind="Table",
                html="<table><tr><td>First</td></tr></table>",
            ),
            block((0, 300, 600, 500), html="<p>Middle</p>"),
            block(
                (0, 600, 600, 800),
                kind="Table",
                html="<table><tr><td>Last</td></tr></table>",
            ),
        ],
    )
    first, _, last = document.pages[0].children
    LLMTableMergeProcessor(
        Mock(return_value={"merge": "true", "direction": "bottom"}), {"use_llm": True}
    ).process_rewriting(document, [first, last])
    layout.finalize_layout(document)
    assert "assembled_source_order_interleaves" in first.layout.issues
    assert (
        len(first.layout.sources) == 2
        and first.html.count("First") == first.html.count("Last") == 1
    )
    assert "Middle" in MarkdownRenderer()(document).markdown


def test_sol_fallback_does_not_require_contour_dependencies(build, monkeypatch):
    for name in ("cv2", "shapely", "shapely.geometry", "shapely.errors"):
        monkeypatch.setitem(sys.modules, name, None)
    document, service = build([], [block()], engine=layout.SolFallbackEngine())
    assert service.call_args.args[0] == PAGE_PROMPT
    assert "Keep all wording" in MarkdownRenderer()(document).markdown
    assert document.layout.page_runtime[0].failure_stage == "preparation"
    result = annotations(document)
    assert result["drawn"] == 1 and not result["geometry_fallbacks"]
    for image in result["pages"].values():
        image.close()


def test_export_invalid_saved_contour_uses_v3_bbox_with_reason(build, monkeypatch):
    document, _ = build([region()], [block((0, 0, 550, 550))])
    source = document.pages[0].children[0].layout.sources[0]
    source.contours = [[[10, 20], [130, 200], [10, 200], [130, 20]]]
    rectangles = []
    monkeypatch.setattr(
        ImageDraw.ImageDraw,
        "rectangle",
        lambda self, xy, **kwargs: rectangles.append(xy),
    )
    result = annotations(document)
    assert result["drawn"] == 1 and rectangles == [(0, 0, 60, 60)]
    assert result["geometry_fallbacks"] == [
        {
            "block_id": source.block_id,
            "reason": "export_contour_invalid",
            "fallback": "v3_bbox",
        }
    ]
    for image in result["pages"].values():
        image.close()


def test_annotation_keeps_both_page_clipped_components(build):
    contour = [[-2, 1], [3, 1], [3, 3], [-1, 3], [-1, 5], [3, 5], [3, 7], [-2, 7]]
    document, _ = build(
        [region((0, 1, 3, 7), contour=contour)],
        [block((0, 100, 300, 700))],
        size=(10, 10),
    )
    result = annotations(document)
    assert result["drawn"] == 2 and result["skipped"] == 0
    for image in result["pages"].values():
        image.close()


def test_hidden_group_child_is_evidence_but_not_drawn(build):
    table = region(kind=21)
    caption = region((0, 61, 60, 70), contour=None, row=1, kind=7, order=8)
    document, _ = build(
        [table, caption],
        [
            block(kind="Table", html="<table><tr><td>Cell</td></tr></table>"),
            block((0, 610, 600, 700), kind="Caption"),
        ],
    )
    StructureBuilder()(document)
    document.pages[0].children[1].ignore_for_output = True
    layout.finalize_layout(document)
    group = document.get_block(document.pages[0].structure[0])
    assert len(group.layout.sources) == 2
    result = annotations(document)
    assert result["drawn"] == 1
    for image in result["pages"].values():
        image.close()


def test_sol_processor_envelope_is_not_mislabeled_as_original_geometry(build):
    document, _ = build([], [block()])
    item = document.pages[0].children[0]
    source = item.layout.sources[0].model_dump()
    item.polygon = PolygonBox.from_bbox([12, 23, 50, 70])
    layout.finalize_layout(document)
    assert (
        item.layout.status == "processor"
        and item.layout.geometry_source == "source_footprints"
    )
    assert item.layout.sources[0].model_dump() == source
    assert "processor_derived_bounds" in item.layout.issues


def test_initial_final_and_annotation_counts_are_distinct(build):
    document, _ = build(
        [region()],
        [
            block(kind="ListGroup", html="<ul><li>One</li><li>Two</li></ul>"),
            block((700, 700, 900, 900), html="<p>Outside guide</p>"),
        ],
    )
    StructureBuilder()(document)
    layout.finalize_layout(document)
    metadata = layout.layout_metadata(document)
    runtime = metadata["page_runtime"][0]
    assert runtime["geometry_counts"] == {"v3_contour": 1, "sol": 1}
    assert runtime["sol_only_reasons"] == {"overlap_below_threshold": 1}
    final = metadata["final_counts"][0]
    assert final["counts_stage"] == "final_visible_structure"
    assert final["geometry_counts"] == {"v3_contour": 1, "sol": 1}
    assert final["visible_blocks"] == 2
    result = annotations(document)
    assert result["page_counts"][0] == {"contours": 1, "rectangles": 1, "skipped": 0}
    summary = layout.layout_summary({"layout": metadata})
    assert "initial eligible=1, matched=1, Sol-only=1, V3-only=0" in summary
    assert "source footprints:" in summary
    for image in result["pages"].values():
        image.close()


def test_filtered_empty_and_v3_only_reasons(build):
    filtered = analysis([])
    filtered.candidate_count = filtered.filtered_count = 300
    document, _ = build(
        [], [block()], engine=SimpleNamespace(analyze=lambda _: filtered)
    )
    assert document.layout.page_runtime[0].sol_only_reasons == {
        "all_candidates_filtered": 1
    }
    document, _ = build([region(kind=21)], [block()])
    runtime = document.layout.page_runtime[0]
    assert runtime.sol_only_reasons == {"no_compatible_v3_class": 1}
    assert runtime.unmatched_v3_reasons == {"no_compatible_sol_class": 1}


@pytest.mark.parametrize(
    "rotation,expected", [(90, [140, 10, 180, 30]), (270, [20, 70, 60, 90])]
)
def test_rotated_provider_contour_and_pdf_overlay(tmp_path, rotation, expected):
    import io

    import pypdfium2 as pdfium

    from doclayout.providers.pdf import PdfProvider

    original = tmp_path / "original.pdf"
    rotated = tmp_path / "rotated.pdf"
    with Image.new("RGB", (100, 200), "white") as image:
        ImageDraw.Draw(image).rectangle((10, 20, 30, 60), fill="black")
        image.save(original, resolution=72)
    with pdfium.PdfDocument(original) as pdf:
        page = pdf[0]
        page.set_rotation(rotation)
        page.close()
        pdf.save(rotated)
    polygon = PolygonBox.from_bbox(expected).polygon
    detection = region(expected, contour=polygon)
    engine = SimpleNamespace(analyze=lambda _: analysis([detection], (200, 100)))
    service = Mock(
        return_value={
            "blank": False,
            "blocks": [
                block(
                    [
                        expected[0] * 5,
                        expected[1] * 10,
                        expected[2] * 5,
                        expected[3] * 10,
                    ]
                )
            ],
        }
    )
    with PdfProvider(str(rotated)) as provider:
        document = DocumentBuilder({"highres_image_dpi": 72})(provider, service, engine)
    page = document.pages[0]
    assert page.highres_image.size == (200, 100)
    assert page.polygon.bbox == [0, 0, 200, 100]
    assert (
        page.highres_image.getpixel(
            (int((expected[0] + expected[2]) / 2), int((expected[1] + expected[3]) / 2))
        )[0]
        < 30
    )
    assert {tuple(p) for p in page.children[0].layout.sources[0].contours[0]} == {
        tuple(p) for p in polygon
    }
    overlay = annotations(document)
    assert overlay["page_counts"][0]["contours"] == 1
    with pdfium.PdfDocument(io.BytesIO(overlay["pdf"])) as pdf:
        rendered_page = pdf[0]
        bitmap = rendered_page.render(scale=200 / rendered_page.get_width())
        raster = bitmap.to_pil().convert("RGB")
        pixel = raster.getpixel((expected[0] + 1, expected[1] + 2))
        assert pixel[0] > pixel[1] + 50
        raster.close()
        bitmap.close()
        rendered_page.close()
    for image in overlay["pages"].values():
        image.close()
    page.highres_image.close()
