"""Offline proofs of mandatory whole-page layout across the shared pipeline."""

import base64
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from doclayout.builders.document import DocumentBuilder
from doclayout.converters.ocr import OCRConverter
from doclayout.converters.pdf import PdfConverter
from doclayout.converters.table import TableConverter
from doclayout.models import create_layout_service as configured_layout
from doclayout.processors.llm.llm_page_correction import LLMPageCorrectionProcessor
from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.json import JSONRenderer
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.renderers.ocr_json import OCRJSONRenderer
from doclayout.schema.extraction import ExtractedPage
from doclayout.schema.layout import (
    alignment_policy,
    check_layout,
    given_layout,
    source_blocks,
)
from doclayout.schema.polygon import PolygonBox
from doclayout.services.layout import (
    MODEL_ID,
    MODEL_REVISION,
    LayoutArtifactError,
    LayoutCacheError,
    LayoutConfigurationError,
    LayoutDependencyError,
    LayoutDeviceError,
    LayoutInferenceError,
    LayoutInvariantError,
    LayoutPromptLimitError,
    LayoutRegion,
    LayoutResult,
)
from doclayout.services.openai import OpenAIService
from doclayout.settings import settings
from doclayout.ui.documents import prepare_upload, run_document
from doclayout.ui.exports import annotations


def block(text, box, kind="Text"):
    return {"block_type": kind, "html": text, "bbox": box}


def engine(regions):
    """Fixtures use normalized rectangles; the injected engine returns page pixels."""

    def predict(image):
        width, height = image.size
        return LayoutResult(
            MODEL_ID,
            MODEL_REVISION,
            "cpu",
            "CPUExecutionProvider",
            0.01,
            image.size,
            tuple(
                LayoutRegion(
                    class_id,
                    label,
                    score,
                    tuple(
                        v * size / 1000
                        for v, size in zip(
                            box, (width, height, width, height), strict=True
                        )
                    ),
                    order,
                )
                for class_id, label, score, box, order in regions
            ),
        )

    return Mock(predict=Mock(side_effect=predict))


@pytest.fixture
def columns(model_dict):
    model_dict["extraction_service"].side_effect = None
    model_dict["extraction_service"].return_value = {
        "blank": False,
        "blocks": [
            block("<p>Right column</p>", [555, 105, 955, 895]),
            block("<p>Left column</p>", [55, 105, 445, 895]),
        ],
    }
    model_dict["layout_service"] = engine(
        [
            (22, "text", 0.99, (550, 100, 950, 900), 2),
            (22, "text", 0.98, (50, 100, 450, 900), 1),
        ]
    )
    return model_dict


@pytest.mark.parametrize("converter_cls", [PdfConverter, OCRConverter])
def test_final_order_geometry_and_all_renderers(converter_cls, columns, temp_doc):
    doc = converter_cls(columns, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = doc.pages[0]
    leaves = source_blocks(page)
    assert [getattr(b, "html", None) for b in leaves] == [
        "<p>Left column</p>",
        "<p>Right column</p>",
    ]
    expected = [[50, 100, 450, 900], [550, 100, 950, 900]]
    for leaf, box in zip(leaves, expected, strict=True):
        assert leaf.polygon.rescale(
            page.polygon.size, (1000, 1000)
        ).bbox == pytest.approx(box)
    assert [s.sol_index for s in page.layout.sources] == [1, 0]
    assert all(s.status == "matched" for s in page.layout.alignment.sol)
    assert page.structure == [b.id for b in leaves]
    image = columns["layout_service"].predict.call_args.args[0]
    call = columns["extraction_service"].call_args
    assert call.args[1] is image is page.highres_image
    guide = json.loads(call.args[0].split("given_layout=", 1)[1])
    assert [r["order"] for r in guide["regions"]] == [1, 2]
    assert guide["regions"][0]["bbox"] == expected[0]
    json_output = JSONRenderer()(doc)
    chunk_output = ChunkRenderer()(doc)
    ocr_output = OCRJSONRenderer()(doc)
    outputs = [json_output, chunk_output, ocr_output]
    lists = [
        json_output.children[0].children,
        chunk_output.blocks,
        ocr_output.children[0].children,
    ]
    for items in lists:
        assert items is not None
        assert [b.id for b in items] == [str(b.id) for b in leaves]
        assert [b.bbox for b in items] == [b.polygon.bbox for b in leaves]
    assert all(
        output.metadata["layout"][0]["model"]["revision"] == MODEL_REVISION
        for output in outputs
    )
    for output in [*outputs, MarkdownRenderer()(doc)]:
        metadata = output.metadata["layout"][0]
        assert metadata["counts"] == {
            "regions": 2,
            "matched": 2,
            "sol_only": 0,
            "v3_only": 0,
        }
        assert metadata["model"]["actual_device"] == "cpu"
        assert metadata["model"]["elapsed_seconds"] == 0.01
        assert metadata["model"]["preparation_seconds"] == 0
        assert metadata["model"]["fallback_reason"] is None
    text = MarkdownRenderer()(doc).markdown
    assert text.index("Left column") < text.index("Right column")
    drawn = annotations(doc)
    assert drawn["drawn"] == 2
    assert drawn["pages"][1].getpixel(
        (int(image.width * 0.05), int(image.height * 0.1))
    ) == (220, 30, 30)


@pytest.mark.parametrize("split", [True, False])
@pytest.mark.parametrize("converter_cls", [PdfConverter, OCRConverter])
def test_split_merge_content_survives_full_rendering(
    model_dict, temp_doc, split, converter_cls
):
    whole = [100, 100, 900, 300]
    halves = [[100, 100, 490, 300], [510, 100, 900, 300]]
    sol_boxes, v3_boxes = ([whole], halves) if split else (halves, [whole])
    markers = [f"UniqueContent{index}" for index in range(len(sol_boxes))]
    model_dict["extraction_service"].side_effect = None
    model_dict["extraction_service"].return_value = {
        "blank": False,
        "blocks": [
            block(f"<p>{text}</p>", box)
            for text, box in zip(markers, sol_boxes, strict=True)
        ],
    }
    model_dict["layout_service"] = engine(
        [(22, "text", 0.99, box, index + 1) for index, box in enumerate(v3_boxes)]
    )
    doc = converter_cls(model_dict, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = doc.pages[0]
    assert all(
        ("split" if split else "merge") in item.reasons
        for item in page.layout.alignment.sol
    )
    assert page.layout.metadata()["counts"] == {
        "regions": len(v3_boxes),
        "matched": 0,
        "sol_only": len(sol_boxes),
        "v3_only": len(v3_boxes),
    }
    markdown = MarkdownRenderer()(doc).markdown
    for marker in markers:
        assert markdown.count(marker) == 1
    leaves = source_blocks(page)
    assert len(leaves) == len(sol_boxes)
    for leaf, box in zip(leaves, sol_boxes, strict=True):
        assert leaf.polygon.rescale(
            page.polygon.size, (1000, 1000)
        ).bbox == pytest.approx(box)
    assert annotations(doc)["drawn"] == len(sol_boxes)


def test_real_sdk_payload_keeps_full_image_and_schema(
    columns, doc_provider, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    client = Mock()
    client.with_options.return_value = client
    client.responses.parse.return_value = SimpleNamespace(
        status="completed",
        usage=None,
        output_parsed=ExtractedPage.model_validate(
            columns["extraction_service"].return_value
        ),
    )
    monkeypatch.setattr("doclayout.services.openai.OpenAI", Mock(return_value=client))
    service = OpenAIService()
    doc = DocumentBuilder()(
        doc_provider, service, layout_service=columns["layout_service"]
    )
    for call, page in zip(
        client.responses.parse.call_args_list, doc.pages, strict=True
    ):
        request = call.kwargs
        assert request["model"] == "gpt-6-sol"
        assert request["text_format"] is ExtractedPage
        content = request["input"][1]["content"]
        assert len(content) == 2 and "given_layout=" in content[0]["text"]
        image = Image.open(
            io.BytesIO(base64.b64decode(content[1]["image_url"].split(",", 1)[1]))
        )
        assert image.size == page.highres_image.size
        assert image.tobytes() == page.highres_image.tobytes()
    service.close()


@pytest.mark.parametrize(
    "error",
    [
        LayoutDependencyError,
        LayoutCacheError,
        LayoutArtifactError,
        LayoutDeviceError,
        LayoutInferenceError,
        RuntimeError,
    ],
)
@pytest.mark.parametrize("converter_cls", [PdfConverter, OCRConverter])
def test_failed_layout_uses_sol(error, columns, temp_doc, converter_cls):
    columns["layout_service"].predict.side_effect = error("private provider payload")
    doc = converter_cls(columns, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = doc.pages[0]
    assert "given_layout=" not in columns["extraction_service"].call_args.args[0]
    assert columns["extraction_service"].call_args.args[1] is page.highres_image
    for leaf, box in zip(
        source_blocks(page), [[555, 105, 955, 895], [55, 105, 445, 895]], strict=True
    ):
        assert leaf.polygon.rescale(
            page.polygon.size, (1000, 1000)
        ).bbox == pytest.approx(box)
    for renderer in (MarkdownRenderer, JSONRenderer, ChunkRenderer, OCRJSONRenderer):
        metadata = renderer()(doc).metadata["layout"][0]
        assert metadata["alignment_mode"] == "sol_fallback"
        assert metadata["model"]["actual_device"] == "unavailable"
        assert metadata["model"]["error_code"]
        assert "private" not in json.dumps(metadata)
        assert metadata["counts"] == {
            "regions": 0,
            "matched": 0,
            "sol_only": 2,
            "v3_only": 0,
        }
        assert all(
            item["reasons"] == ("layout_unavailable",) for item in metadata["sol"]
        )
    markdown = MarkdownRenderer()(doc).markdown
    assert markdown.count("Right column") == markdown.count("Left column") == 1
    assert markdown.index("Right column") < markdown.index("Left column")
    assert annotations(doc)["drawn"] == 2


@pytest.mark.parametrize("policy", ["", "{}", "not JSON", '{"min_iou":0.5}'])
def test_invalid_or_partial_policy_precedes_both_models(
    policy, model_dict, monkeypatch
):
    monkeypatch.setattr(settings, "DOCLAYOUT_ALIGNMENT_POLICY", policy)
    with pytest.raises(LayoutConfigurationError):
        PdfConverter(model_dict)
    model_dict["extraction_service"].assert_not_called()
    model_dict["layout_service"].predict.assert_not_called()


def test_explicit_invalid_override_does_not_fall_back(model_dict):
    assert alignment_policy({"alignment_policy": None}) is None
    assert alignment_policy({"alignment_policy": "null"}) is None
    with pytest.raises(LayoutConfigurationError):
        PdfConverter(model_dict, config={"alignment_policy": {}})
    with pytest.raises(LayoutConfigurationError):
        alignment_policy({"alignment_policy": {"min_iou": 0.5}})


@pytest.mark.parametrize("converter_cls", [PdfConverter, OCRConverter])
def test_absent_policy_keeps_sol_geometry_order_and_v3_guide(
    columns, temp_doc, monkeypatch, converter_cls
):
    monkeypatch.setattr(settings, "DOCLAYOUT_ALIGNMENT_POLICY", None)
    document = converter_cls(columns, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = document.pages[0]
    assert page.layout is not None
    leaves = source_blocks(page)
    assert [getattr(leaf, "html", None) for leaf in leaves] == [
        "<p>Right column</p>",
        "<p>Left column</p>",
    ]
    for leaf, expected in zip(
        leaves, [[555, 105, 955, 895], [55, 105, 445, 895]], strict=True
    ):
        assert leaf.polygon.rescale(
            page.polygon.size, (1000, 1000)
        ).bbox == pytest.approx(expected)
    assert page.structure == [leaf.id for leaf in leaves]
    columns["layout_service"].predict.assert_called_once()
    assert "given_layout=" in columns["extraction_service"].call_args.args[0]
    for renderer in (MarkdownRenderer, JSONRenderer, ChunkRenderer, OCRJSONRenderer):
        output = renderer()(document)
        metadata = output.metadata["layout"][0]
        assert metadata["alignment_mode"] == "sol_geometry"
        assert metadata["policy"] is None and metadata["candidates"] == []
        assert metadata["counts"] == {
            "regions": 2,
            "matched": 0,
            "sol_only": 2,
            "v3_only": 2,
        }
        assert all(
            item["reasons"] == ("policy_not_configured",) for item in metadata["sol"]
        )
        assert output.metadata["extraction"]["geometry"] == "model-estimated"
    text = MarkdownRenderer()(document).markdown
    assert text.count("Right column") == text.count("Left column") == 1
    assert text.index("Right column") < text.index("Left column")
    assert annotations(document)["drawn"] == 2


def test_absent_policy_uses_sol_when_v3_fails(model_dict, temp_doc, monkeypatch):
    monkeypatch.setattr(settings, "DOCLAYOUT_ALIGNMENT_POLICY", None)
    model_dict["layout_service"].predict.side_effect = LayoutInferenceError(
        "unavailable"
    )
    doc = PdfConverter(model_dict).build_document(temp_doc.name)
    assert all(
        page.layout is not None
        and page.layout.metadata()["alignment_mode"] == "sol_fallback"
        for page in doc.pages
    )
    assert model_dict["extraction_service"].called


def test_page_failure_does_not_disable_later_v3(doc_provider, page_result):
    healthy = engine([])
    calls = 0

    def predict(image):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LayoutInferenceError("private payload")
        return healthy.predict(image)

    sol = Mock(return_value=page_result)
    doc = DocumentBuilder()(doc_provider, sol, layout_service=Mock(predict=predict))
    assert len(doc.pages) == 2
    assert doc.pages[0].layout.metadata()["alignment_mode"] == "sol_fallback"
    assert doc.pages[1].layout.metadata()["alignment_mode"] == "v3_matching"
    assert doc.pages[1].layout.metadata()["model"]["error_code"] is None
    assert "given_layout=" not in sol.call_args_list[0].args[0]
    assert "given_layout=" in sol.call_args_list[1].args[0]


def test_guide_bounds_no_truncation():
    layout = engine([(22, "text", 0.9, (10, 10, 90, 90), 1)]).predict(
        Image.new("RGB", (100, 100))
    )
    with pytest.raises(LayoutPromptLimitError):
        given_layout(
            replace(
                layout,
                regions=tuple(
                    replace(layout.regions[0], order_index=i + 1) for i in range(513)
                ),
            ),
            (100, 100),
        )
    with pytest.raises(LayoutPromptLimitError):
        given_layout(
            replace(layout, regions=(replace(layout.regions[0], label="é" * 33000),)),
            (100, 100),
        )
    for invalid in [
        replace(layout, image_size=(99, 100)),
        replace(layout, regions=(replace(layout.regions[0], bbox=(10, 10, 10, 20)),)),
        replace(layout, regions=layout.regions * 2),
    ]:
        with pytest.raises(LayoutInferenceError):
            given_layout(invalid, (100, 100))


@pytest.mark.parametrize(
    "mutation",
    ["box", "order", "id", "duplicate", "remove", "page_box", "state", "invalid_id"],
)
def test_processors_cannot_undo_layout(mutation, columns, temp_doc):
    converter = PdfConverter(columns, config={"page_range": [0]})

    def corrupt(document):
        page = document.pages[0]
        if mutation == "box":
            page.children[0].polygon = PolygonBox.from_bbox([0, 0, 1, 1])
        elif mutation == "order":
            page.structure.reverse()
        elif mutation == "id":
            page.children[0].block_id = 42
        elif mutation == "duplicate":
            page.structure.append(page.structure[0])
        elif mutation == "page_box":
            page.polygon = PolygonBox.from_bbox([0, 0, 1, 1])
        elif mutation == "state":
            page.layout = None
        elif mutation == "invalid_id":
            page.structure[0] = page.structure[0].model_copy(update={"block_id": 999})
        else:
            page.structure.pop()

    converter.processor_list = [Mock(side_effect=corrupt)]
    with pytest.raises(LayoutInvariantError):
        converter.build_document(temp_doc.name)


@pytest.mark.parametrize(
    "action",
    [
        "rewrite",
        "reorder",
        "reorder_first",
        "wrong_type",
        "foreign_id",
        "duplicate",
        "bbox",
        "empty",
    ],
)
def test_page_correction_is_atomic_html_only(action, columns, temp_doc):
    doc = PdfConverter(columns, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = doc.pages[0]
    assert page.structure is not None and page.layout is not None
    original_order = list(page.structure)
    original_boxes = [b.polygon.model_copy(deep=True) for b in source_blocks(page)]
    first, second = source_blocks(page)
    change = {
        "id": str(first.id),
        "block_type": "Text",
        "html": "<p>Left <b>column</b></p>",
    }
    changes = [change]
    if action == "wrong_type":
        change["block_type"] = "Table"
    elif action == "foreign_id":
        changes.append({**change, "id": "/page/42/Text/0"})
    elif action == "duplicate":
        changes.append(change.copy())
    elif action == "bbox":
        change["bbox"] = [0, 0, 1, 1]
    elif action == "empty":
        change["html"] = ""
    service = Mock(
        return_value={
            "analysis": "test",
            "correction_type": action
            if action in {"reorder", "reorder_first"}
            else "rewrite",
            "blocks": changes,
        }
    )
    processor = LLMPageCorrectionProcessor(
        service, {"use_llm": True, "block_correction_prompt": "Improve formatting"}
    )
    processor.process_rewriting(doc, page)
    assert page.structure == original_order
    assert [b.polygon for b in source_blocks(page)] == original_boxes
    assert service.call_count == 1
    assert getattr(first, "html", None) == (
        change["html"] if action == "rewrite" else "<p>Left column</p>"
    )
    assert getattr(second, "html", None) == "<p>Right column</p>"
    assert bool(page.layout.events) == (action != "rewrite")
    check_layout(doc)


def test_group_boxes_and_table_filter_are_explicit(model_dict, temp_doc):
    model_dict["extraction_service"].side_effect = None
    model_dict["extraction_service"].return_value = {
        "blank": False,
        "blocks": [
            block("", [100, 100, 600, 400], "Figure"),
            block("<p>Caption</p>", [100, 405, 600, 450], "Caption"),
            block(
                "<table><tr><td>Cell</td></tr></table>", [100, 600, 900, 900], "Table"
            ),
        ],
    }
    model_dict["layout_service"] = engine(
        [
            (14, "image", 0.99, (100, 100, 600, 400), 1),
            (7, "figure_title", 0.99, (100, 405, 600, 450), 2),
            (21, "table", 0.99, (100, 600, 900, 900), 3),
        ]
    )
    doc = PdfConverter(model_dict, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = doc.pages[0]
    assert page.structure is not None
    assert len(page.structure) == 2 and len(source_blocks(page)) == 3
    group = page.get_block(page.structure[0])
    assert group is not None and str(group.block_type) == "FigureGroup"
    assert annotations(doc)["drawn"] == 3
    meta = ChunkRenderer()(doc).metadata["layout"][0]
    assert len(meta["groups"]) == 1
    check_layout(doc)
    table = TableConverter(model_dict, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    table_page = table.pages[0]
    assert table_page.structure is not None and table_page.layout is not None
    assert len(table_page.structure) == 1
    assert list(table_page.layout.filtered.values()) == ["table_converter"] * 2


def test_gui_helper_uses_layout(columns, temp_doc):
    upload = prepare_upload(Path(temp_doc.name).read_bytes(), "input.pdf")
    result = run_document(upload, {"page_range": "0"}, columns)
    assert columns["layout_service"].predict.call_count == 1
    assert result["markdown"].index("Left column") < result["markdown"].index(
        "Right column"
    )
    assert result["metadata"]["layout"][0]["sol"][0]["status"] == "matched"


@pytest.mark.parametrize("kind", ["blank", "graphic", "v3_only"])
def test_blank_and_graphic_pages(kind, model_dict, temp_doc):
    model_dict["layout_service"] = engine(
        [] if kind == "blank" else [(14, "image", 0.99, (100, 100, 900, 900), 1)]
    )
    model_dict["extraction_service"].side_effect = None
    model_dict["extraction_service"].return_value = {
        "blank": kind != "graphic",
        "blocks": [block("", [100, 100, 900, 900], "Figure")]
        if kind == "graphic"
        else [],
    }
    doc = PdfConverter(model_dict, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    page = doc.pages[0]
    assert page.structure is not None and page.layout is not None
    assert len(page.structure) == (1 if kind == "graphic" else 0)
    assert annotations(doc)["drawn"] == (1 if kind == "graphic" else 0)
    if kind == "v3_only":
        assert page.layout.alignment.regions[0].status == "v3_only"


@pytest.mark.parametrize("device", ["auto", "cpu", "cuda"])
def test_operator_factory_is_lazy(device, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DOCLAYOUT_LAYOUT_DEVICE", device)
    cache = tmp_path / "unused-cache"
    monkeypatch.setattr(settings, "DOCLAYOUT_LAYOUT_CACHE_DIR", str(cache))
    runtime = Mock(side_effect=AssertionError("Eager model load"))
    monkeypatch.setattr("doclayout.services.layout._dependencies", runtime)
    service = configured_layout()
    assert service.device == device and service.cache_dir == cache
    assert not cache.exists()
    runtime.assert_not_called()


def test_invalid_operator_device(monkeypatch):
    monkeypatch.setattr(settings, "DOCLAYOUT_LAYOUT_DEVICE", "off")
    with pytest.raises(LayoutConfigurationError):
        configured_layout()


@pytest.mark.parametrize("command", ["file", "single", "folder"])
def test_all_cli_paths_use_sol_on_layout_failure(
    command, model_dict, temp_doc, tmp_path, monkeypatch
):
    from click.testing import CliRunner

    from doclayout.scripts import convert, convert_single

    monkeypatch.setattr(convert, "create_model_dict", lambda: model_dict)
    monkeypatch.setattr(convert_single, "create_model_dict", lambda: model_dict)
    model_dict["layout_service"].predict.side_effect = LayoutCacheError("private path")
    destination = tmp_path / "out"
    destination.mkdir()
    existing = destination / "prior.md"
    existing.write_text("keep")
    if command == "file":
        cli, args = convert.convert_cli, [temp_doc.name, str(destination)]
    elif command == "single":
        cli, args = (
            convert_single.convert_single_cli,
            [temp_doc.name, "--output_dir", str(destination)],
        )
    else:
        cli, args = (
            convert.convert_cli,
            [str(tmp_path), "--output_dir", str(destination)],
        )
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "private path" not in result.output
    assert existing.read_text() == "keep"
    assert len(list(destination.rglob("*.*"))) > 1
    assert model_dict["extraction_service"].called


def test_page_furniture_order_and_repeat_export_visibility(model_dict, temp_doc):
    specs = [
        ("Footnote", "<p>Footnote</p>", [100, 800, 900, 850], 10, "footnote"),
        ("Text", "<p>Body</p>", [100, 200, 900, 700], 22, "text"),
        ("PageHeader", "<p>Header</p>", [100, 10, 900, 90], 12, "header"),
    ]
    model_dict["extraction_service"].side_effect = None
    model_dict["extraction_service"].return_value = {
        "blank": False,
        "blocks": [block(html, box, kind) for kind, html, box, _, _ in specs],
    }
    model_dict["layout_service"] = engine(
        [
            (cid, label, 0.99, box, i + 1)
            for i, (_, _, box, cid, label) in enumerate(specs)
        ]
    )
    doc = PdfConverter(model_dict, config={"page_range": [0]}).build_document(
        temp_doc.name
    )
    assert [str(b.block_type) for b in source_blocks(doc.pages[0])] == [
        s[0] for s in specs
    ]
    keep = {"keep_pageheader_in_output": True}
    assert annotations(doc, keep)["drawn"] == 3
    assert len(OCRJSONRenderer(keep)(doc).children[0].children) == 3
    assert "Header" in MarkdownRenderer(keep)(doc).markdown
    assert "Header" not in MarkdownRenderer()(doc).markdown
    assert "Header" in MarkdownRenderer(keep)(doc).markdown
    assert annotations(doc)["drawn"] == 2
    assert len(OCRJSONRenderer()(doc).children[0].children) == 2
    check_layout(doc)


def test_table_merge_is_skipped_and_heading_metadata_refreshed(model_dict, temp_doc):
    from doclayout.processors.llm.llm_table_merge import LLMTableMergeProcessor

    model_dict["extraction_service"].side_effect = None
    model_dict["extraction_service"].return_value = {
        "blank": False,
        "blocks": [block("<h1>Heading</h1>", [100, 100, 900, 200], "SectionHeader")],
    }
    model_dict["layout_service"] = engine(
        [(17, "paragraph_title", 0.99, (100, 100, 900, 200), 1)]
    )
    service = Mock(
        return_value={
            "analysis": "format",
            "correction_type": "rewrite",
            "blocks": [
                {
                    "id": "/page/0/SectionHeader/0",
                    "block_type": "SectionHeader",
                    "html": "<h3>Heading</h3>",
                }
            ],
        }
    )
    converter = PdfConverter(model_dict, config={"page_range": [0], "use_llm": True})
    merge = LLMTableMergeProcessor(service, {"use_llm": True})
    merge.rewrite_blocks = Mock(side_effect=AssertionError("Must skip merging"))
    correction = LLMPageCorrectionProcessor(
        service, {"use_llm": True, "block_correction_prompt": "Format"}
    )
    converter.processor_list = [merge, correction]
    doc = converter.build_document(temp_doc.name)
    assert (
        MarkdownRenderer()(doc).metadata["table_of_contents"][0]["heading_level"] == 3
    )
    state = doc.pages[0].layout
    assert state is not None
    assert state.events == ["table_merge_skipped:protected_layout"]
    assert service.call_count == 1


def test_inflight_image_lifetime_on_later_layout_failure(doc_provider, page_result):
    from threading import Event

    started, release = Event(), Event()
    images, reads = [], []

    def predict(image):
        images.append(image)
        if len(images) == 2:
            assert started.wait(3)
            release.set()
            raise LayoutInvariantError("second page")
        return LayoutResult(
            MODEL_ID,
            MODEL_REVISION,
            "cpu",
            "CPUExecutionProvider",
            0.01,
            image.size,
            (),
        )

    def extract(prompt, image, *args):
        started.set()
        assert release.wait(3)
        reads.append(image.getpixel((0, 0)))
        return page_result

    sol = Mock(side_effect=extract)
    with pytest.raises(LayoutInvariantError):
        DocumentBuilder()(doc_provider, sol, layout_service=Mock(predict=predict))
    assert len(reads) == 1 and sol.call_count == 1
    for image in images:
        with pytest.raises(ValueError, match="closed"):
            image.getpixel((0, 0))
