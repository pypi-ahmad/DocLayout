"""Offline proof of whole-page layout-conditioned transcription and exports."""

import base64
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from doclayout import layout
from doclayout.builders.document import DocumentBuilder
from doclayout.builders.structure import StructureBuilder
from doclayout.processors.footnote import FootnoteProcessor
from doclayout.processors.page_header import PageHeaderProcessor
from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.json import JSONRenderer
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.schema.extraction import PAGE_PROMPT, ExtractedPage, sanitize_html
from doclayout.schema.layout import LayoutAnalysis, LayoutRegion
from doclayout.schema.polygon import PolygonBox
from doclayout.services.openai import OpenAIService
from doclayout.ui.exports import annotations


def region(box, *, row=0, kind=22, order=0, eligible=True):
    return LayoutRegion(
        row=row,
        class_id=kind,
        label=layout.LABELS[kind],
        score=0.9,
        raw_bbox_px=list(box),
        bbox_px=list(box),
        order_key=order,
        eligible=eligible,
        mask_rle=[40000],
    )


def analysis(regions, size=(200, 100)):
    return LayoutAnalysis(
        image_size=size,
        model_id=layout.REPO,
        model_revision=layout.REVISION,
        provider="CPUExecutionProvider",
        actual_device="cpu",
        elapsed_ms=12.5,
        candidate_count=len(regions),
        filtered_count=0,
        regions=regions,
    )


def block(box, html="<p>Visible text</p>", kind="Text"):
    return {"bbox": box, "html": html, "block_type": kind}


def prior(prompt):
    return json.loads(prompt.removeprefix(PAGE_PROMPT.rstrip()).strip())["given_layout"]


@pytest.fixture
def build_page():
    images = []

    def build(regions, blocks, *, service=None):
        image = Image.new("RGB", (200, 100), (17, 31, 53))
        images.append(image)
        provider = SimpleNamespace(
            filepath="synthetic.pdf",
            page_range=[3],
            get_images=Mock(return_value=[image]),
            get_page_bbox=lambda _: PolygonBox.from_bbox([10, 20, 210, 120]),
            get_page_refs=lambda _: [],
        )
        engine = SimpleNamespace(analyze=Mock(return_value=analysis(regions)))
        if service is None:
            service = Mock(return_value={"blank": not blocks, "blocks": blocks})
        document = DocumentBuilder()(provider, service, engine)
        engine.analyze.assert_called_once_with(image)
        provider.get_images.assert_called_once_with([3], 192)
        return document, service, image

    yield build
    for image in images:
        image.close()


def test_prior_scaling_mapping_and_deterministic_payload():
    expected = [
        "Text",
        None,
        "Text",
        "Figure",
        "TableOfContents",
        "Equation",
        "SectionHeader",
        "Caption",
        "PageFooter",
        "Picture",
        "Footnote",
        None,
        "PageHeader",
        "Picture",
        "Picture",
        None,
        None,
        "SectionHeader",
        None,
        "Bibliography",
        "Picture",
        "Table",
        "Text",
        "Text",
        None,
    ]
    regions = [
        region([20, 10, 180, 90], row=i, kind=i, order=24 - i) for i in range(25)
    ]
    regions.append(region([0, 0, 0, 10], row=25, eligible=False))
    result = analysis(regions)
    before = result.model_dump()
    prompt = layout.extraction_prompt(PAGE_PROMPT, result)
    payload = prior(prompt)
    assert payload["coordinate_space"] == "full_page_normalized_0_1000"
    assert payload["geometry_type"] == "rectangle" and payload["version"] == 1
    assert [r["row"] for r in payload["regions"]] == list(range(24, -1, -1))
    for item in payload["regions"]:
        assert item["bbox"] == [100, 100, 900, 900]
        assert item["label"] == layout.LABELS[item["class_id"]]
        assert item["block_type_hint"] == expected[item["class_id"]]
        assert item["score"] == 0.9
        assert "mask_rle" not in item and "observed_rank" not in item
    assert layout.extraction_prompt(PAGE_PROMPT, result) == prompt
    assert result.model_dump() == before  # Never normalize the evidence in place.


def test_actual_responses_payload_preserves_whole_image_and_contract(
    build_page, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    response = ExtractedPage(blank=False, blocks=[block([100, 100, 900, 300])])
    client = Mock()
    client.with_options.return_value = client
    client.responses.parse.return_value = SimpleNamespace(
        status="completed",
        output_parsed=response,
        usage=None,
    )
    monkeypatch.setattr("doclayout.services.openai.OpenAI", Mock(return_value=client))
    service = OpenAIService()
    try:
        _, _, image = build_page([region([20, 10, 180, 30])], [], service=service)
        client.responses.parse.assert_called_once()
        request = client.responses.parse.call_args.kwargs
        assert request["model"] == "gpt-6-sol"
        assert request["reasoning"] == {"effort": "medium"}
        assert request["store"] is False and request["text_format"] is ExtractedPage
        content = request["input"][1]["content"]
        assert len(content) == 2 and content[0]["type"] == "input_text"
        assert prior(content[0]["text"])["regions"][0]["bbox"] == [100, 100, 900, 300]
        assert content[1]["type"] == "input_image"
        with Image.open(
            io.BytesIO(base64.b64decode(content[1]["image_url"].split(",")[1]))
        ) as sent:
            assert sent.size == image.size and sent.tobytes() == image.tobytes()
    finally:
        service.close()


def test_two_column_order_final_bounds_and_rectangle_annotations(
    build_page, monkeypatch
):
    boxes = [[10, 10, 80, 25], [120, 10, 190, 25], [10, 40, 80, 55], [120, 40, 190, 55]]
    regions = [
        region(b, row=i, order=o) for i, (b, o) in enumerate(zip(boxes, [0, 2, 1, 3]))
    ]
    # Slightly different Sol boxes prove accepted V3 geometry is used.
    blocks = [
        block(
            [b[0] * 5 + 1, b[1] * 10, b[2] * 5 - 1, b[3] * 10],
            f"<p>Column item {i}</p>",
        )
        for i, b in enumerate(boxes)
    ]
    document, _, _ = build_page(regions, blocks)
    page = document.pages[0]
    original_ids = [b.id for b in page.children]
    assert page.structure == [original_ids[i] for i in [0, 2, 1, 3]]
    layout.finalize_layout(document)
    markdown = MarkdownRenderer()(document)
    structured = JSONRenderer()(document)
    chunks = ChunkRenderer()(document)
    assert [b.id for b in chunks.blocks] == [str(b) for b in page.structure]
    assert [b.id for b in structured.children[0].children] == [
        b.id for b in chunks.blocks
    ]
    positions = [markdown.markdown.index(f"Column item {i}") for i in [0, 2, 1, 3]]
    assert positions == sorted(positions)
    metadata = chunks.metadata["layout"]
    for chunk, node in zip(chunks.blocks, structured.children[0].children):
        index = [str(bid) for bid in original_ids].index(chunk.id)
        expected = [
            boxes[index][0] + 10,
            boxes[index][1] + 20,
            boxes[index][2] + 10,
            boxes[index][3] + 20,
        ]
        assert (
            chunk.bbox
            == node.bbox
            == metadata["blocks"][chunk.id]["final_bbox"]
            == expected
        )
        assert metadata["blocks"][chunk.id]["geometry_source"] == "v3_bbox"
        assert len(chunk.polygon) == 4
    drawn = []
    original = ImageDraw.ImageDraw.rectangle

    def capture(self, xy, *args, **kwargs):
        drawn.append(list(xy))
        return original(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rectangle", capture)
    overlays = annotations(document)
    assert drawn == [boxes[i] for i in [0, 2, 1, 3]]
    assert overlays["drawn"] == 4 and overlays["skipped"] == 0
    for image in overlays["pages"].values():
        image.close()
    runtime = document.layout.page_runtime[3]
    assert runtime.model_id == layout.REPO and runtime.model_revision == layout.REVISION
    assert runtime.actual_device == "cpu" and runtime.elapsed_ms == 12.5
    assert runtime.matched_count == runtime.prior_region_count == 4
    assert runtime.sol_only_count == runtime.unmatched_v3_count == 0
    assert [b.id for b in page.children] == original_ids


def test_sol_html_semantics_and_unmatched_evidence(build_page):
    heading = '<h3 onclick="bad()">Visible heading</h3>'
    table = '<table><tr><th colspan="2">Title</th></tr><tr><td>A</td><td>B</td></tr></table>'
    document, _, _ = build_page(
        [
            region([10, 10, 180, 20], kind=6),
            region([10, 30, 180, 60], row=1, kind=21, order=1),
            region([150, 80, 190, 95], row=2, kind=1, order=2),
        ],
        [
            block([50, 100, 900, 200], heading, "SectionHeader"),
            block([50, 300, 900, 600], table, "Table"),
            block([50, 700, 400, 800], "<p>Missed text</p>"),
        ],
    )
    heading_block, table_block, missed = document.pages[0].children
    assert heading_block.html == "<h3>Visible heading</h3>"
    assert table_block.html == sanitize_html(table)
    assert missed.layout.status == "sol_only" and missed.polygon.bbox == [
        20,
        90,
        90,
        100,
    ]
    assert document.layout.pages[0].regions[-1].issues == ["unmatched_v3"]
    runtime = document.layout.page_runtime[3]
    assert (
        runtime.matched_count,
        runtime.sol_only_count,
        runtime.unmatched_v3_count,
    ) == (2, 1, 1)
    text = MarkdownRenderer()(document).markdown
    assert text.count("Visible heading") == text.count("Missed text") == 1
    assert "algorithm" not in text and len(ChunkRenderer()(document).blocks) == 3


@pytest.mark.parametrize(
    "detected,visible", [(False, False), (True, False), (False, True)]
)
def test_blank_and_empty_prior_never_invent_content(build_page, detected, visible):
    document, service, _ = build_page(
        [region([20, 10, 180, 30])] if detected else [],
        [block([100, 100, 900, 300])] if visible else [],
    )
    assert len(prior(service.call_args.args[0])["regions"]) == int(detected)
    assert len(document.pages[0].children) == int(visible)
    assert bool(document.layout.pages[0].warnings) == (detected and not visible)
    if visible:
        assert document.pages[0].children[0].layout.status == "sol_only"


@pytest.mark.parametrize("keep", [False, True])
def test_processor_order_and_header_footer_visibility(build_page, keep):
    document, _, _ = build_page(
        [
            region([10, 40, 180, 60], kind=10),
            region([10, 25, 180, 35], row=1),
            region([10, 5, 180, 15], row=2, kind=12),
            region([10, 85, 180, 95], row=3, kind=8),
        ],
        [
            block([50, 400, 900, 600], "<p>Footnote visible</p>", "Footnote"),
            block([50, 250, 900, 350], "<p>Body visible</p>"),
            block([50, 50, 900, 150], "<p>Header visible</p>", "PageHeader"),
            block([50, 850, 900, 950], "<p>Footer visible</p>", "PageFooter"),
        ],
    )
    PageHeaderProcessor()(document)
    FootnoteProcessor()(document)
    layout.finalize_layout(document)
    config = {"keep_pageheader_in_output": keep, "keep_pagefooter_in_output": keep}
    markdown = MarkdownRenderer(config)(document)
    chunks = ChunkRenderer(config)(document)
    assert ("Header visible" in markdown.markdown) is keep
    assert ("Footer visible" in markdown.markdown) is keep
    assert chunks.blocks[0].block_type == "PageHeader"
    assert chunks.blocks[-1].block_type == "Footnote"
    assert chunks.metadata["layout"]["final_order"][3] == [b.id for b in chunks.blocks]
    assert bool(chunks.blocks[0].html) is keep
    overlays = annotations(document)
    assert overlays["drawn"] == (4 if keep else 2)
    for image in overlays["pages"].values():
        image.close()


def test_pipeline_versions_and_prior_protocol_are_distinct(monkeypatch):
    current = layout.pipeline_manifest()
    assert current["pipeline"] == "sol-layout-v3/v2"
    monkeypatch.setattr(layout, "PIPELINE", "sol-layout-v3/v1")
    assert current["fingerprint"] != layout.pipeline_manifest()["fingerprint"]
    monkeypatch.setattr(layout, "PIPELINE", "sol-layout-v3/v2")
    monkeypatch.setattr(layout, "PRIOR_VERSION", 2)
    assert current["fingerprint"] != layout.pipeline_manifest()["fingerprint"]


def test_grouped_geometry_is_final_and_retains_original_regions(
    build_page, monkeypatch
):
    document, _, _ = build_page(
        [
            region([20, 20, 180, 60], kind=21),
            region([20, 62, 180, 72], row=1, kind=7, order=1),
        ],
        [
            block(
                [100, 200, 900, 600], "<table><tr><td>Cell</td></tr></table>", "Table"
            ),
            block([100, 620, 900, 720], "<p>Caption</p>", "Caption"),
        ],
    )
    StructureBuilder()(document)
    layout.finalize_layout(document)
    chunks = ChunkRenderer()(document)
    structured = JSONRenderer()(document)
    assert len(chunks.blocks) == 1
    group = chunks.blocks[0]
    assert group.block_type == "TableGroup"
    assert group.bbox == structured.children[0].children[0].bbox == [30, 40, 190, 92]
    record = chunks.metadata["layout"]["blocks"][group.id]
    assert record["geometry_source"] == "processor"
    assert len(record["sources"]) == 2
    assert document.layout.page_runtime[3].matched_count == 2
    assert document.layout.page_runtime[3].counts_stage == "initial_reconciliation"
    markdown = MarkdownRenderer()(document).markdown
    assert markdown.count("Caption") == markdown.count("Cell") == 1
    drawn = []
    monkeypatch.setattr(
        ImageDraw.ImageDraw, "rectangle", lambda self, xy, **kw: drawn.append(list(xy))
    )
    overlays = annotations(document)
    assert drawn == [[20, 20, 180, 72]] and overlays["drawn"] == 1
    for image in overlays["pages"].values():
        image.close()


def test_equal_overlap_candidates_are_not_forced_or_rendered_twice(build_page):
    document, _, _ = build_page(
        [region([0, 10, 80, 30]), region([40, 10, 120, 30], row=1)],
        [block([100, 100, 500, 300], "<p>Keep once</p>")],
    )
    item = document.pages[0].children[0]
    assert item.layout.status == "sol_only"
    assert item.layout.issues == ["ambiguous_match"]
    assert item.polygon.bbox == [30, 30, 110, 50]
    assert MarkdownRenderer()(document).markdown.count("Keep once") == 1
    assert document.layout.page_runtime[3].unmatched_v3_count == 2


def test_prior_requests_share_three_page_api_cap(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    client = Mock()
    client.with_options.return_value = client
    monkeypatch.setattr("doclayout.services.openai.OpenAI", Mock(return_value=client))
    guard = threading.Lock()
    barrier = threading.Barrier(3)
    active = peak = 0

    def parse(**kwargs):
        nonlocal active, peak
        assert prior(kwargs["input"][1]["content"][0]["text"])["regions"] == []
        with guard:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        time.sleep(0.02)
        with guard:
            active -= 1
        return SimpleNamespace(
            status="completed",
            output_parsed=ExtractedPage(blank=True, blocks=[]),
            usage=None,
        )

    client.responses.parse.side_effect = parse
    service = OpenAIService()
    jobs = [service.configured({}) for _ in range(3)]
    prompt = layout.extraction_prompt(PAGE_PROMPT, analysis([]))
    try:
        with (
            Image.new("RGB", (200, 100)) as image,
            ThreadPoolExecutor(max_workers=9) as executor,
        ):
            results = list(
                executor.map(
                    lambda i: jobs[i % 3](prompt, image, None, ExtractedPage), range(9)
                )
            )
        assert peak == 3 and len(results) == 9
    finally:
        service.close()


def test_mixed_page_failure_keeps_sol_box_and_successful_v3_match():
    with Image.new("RGB", (200, 100), "white") as image:
        provider = SimpleNamespace(
            filepath="synthetic.pdf",
            page_range=[0, 1],
            get_images=lambda *_: [image],
            get_page_bbox=lambda _: PolygonBox.from_bbox([10, 20, 210, 120]),
            get_page_refs=lambda _: [],
        )
        engine = SimpleNamespace(
            analyze=Mock(
                side_effect=[
                    analysis([region([10, 10, 180, 20])]),
                    RuntimeError("PRIVATE native error"),
                ]
            )
        )
        service = Mock(
            return_value={
                "blank": False,
                "blocks": [
                    block([50, 100, 880, 200], '<p onclick="bad()">Keep text</p>')
                ],
            }
        )
        document = DocumentBuilder({"page_concurrency": 1})(provider, service, engine)
        assert service.call_count == 2
        assert prior(service.call_args_list[0].args[0])["regions"]
        assert service.call_args_list[1].args[0] == PAGE_PROMPT
        first, second = (p.children[0] for p in document.pages)
        assert first.layout.status == "matched" and first.polygon.bbox == [
            20,
            30,
            190,
            40,
        ]
        assert second.layout.status == "sol_only" and second.polygon.bbox == [
            20,
            30,
            186,
            40,
        ]
        assert first.html == second.html == "<p>Keep text</p>"
        runtime = document.layout.page_runtime[1]
        assert runtime.status == "sol_fallback" and runtime.sol_only_count == 1
        assert runtime.actual_device is runtime.order_key_source is None
        assert "PRIVATE" not in document.layout.model_dump_json()
        assert MarkdownRenderer()(document).markdown.count("Keep text") == 2
        layout.finalize_layout(document)
        chunks = ChunkRenderer()(document)
        structured = JSONRenderer()(document)
        assert len(chunks.blocks) == 2
        assert (
            chunks.blocks[1].bbox
            == structured.children[1].children[0].bbox
            == [20, 30, 186, 40]
        )
        assert (
            chunks.metadata["layout"]["blocks"][str(second.id)]["geometry_source"]
            == "sol"
        )
        assert annotations(document)["drawn"] == 2
