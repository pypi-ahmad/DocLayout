"""Offline layout contracts; real providers are exercised separately and explicitly."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from doclayout import layout
from doclayout.builders.document import DocumentBuilder
from doclayout.schema.extraction import ExtractedPage
from doclayout.schema.layout import (
    BlockLayout,
    LayoutAnalysis,
    LayoutRegion,
    PageRegions,
    SourceRegion,
)


def detection(box=(10, 10, 90, 30), *, row=0, kind=22, order=0, score=0.9):
    return LayoutRegion(
        row=row,
        class_id=kind,
        label=layout.LABELS[kind],
        score=score,
        raw_bbox_px=list(box),
        bbox_px=list(box),
        order_key=order,
    )


def page(*regions, size=(100, 100)):
    return PageRegions(
        page_id=0, image_size=size, provider="test", regions=list(regions)
    )


def sol(*boxes, types=None):
    return ExtractedPage(
        blank=not boxes,
        blocks=[
            {
                "block_type": types[i] if types else "Text",
                "bbox": box,
                "html": f"<p>Keep {i}</p>",
            }
            for i, box in enumerate(boxes)
        ],
    )


def tensors():
    return [
        np.array([[22, 0.9, 10, 10, 90, 30, 8]], dtype=np.float32),
        np.array([1], dtype=np.int32),
        np.zeros((1, 200, 200), dtype=np.int32),
    ]


def test_preprocess_rgb_non_square_and_image_ownership():
    image = Image.new("RGB", (200, 100), (255, 0, 0))
    inputs = layout.image_inputs(image)
    assert inputs["image"].shape == (1, 3, 800, 800)
    assert inputs["image"].dtype == np.float32
    assert inputs["image"][0, :, 0, 0].tolist() == [1, 0, 0]
    assert inputs["scale_factor"].tolist() == [[8, 4]]
    assert inputs["im_shape"].tolist() == [[800, 800]]
    assert image.size == (200, 100) and image.getpixel((0, 0)) == (255, 0, 0)


def test_decode_mask_score_and_original_pixels():
    outputs = tensors()
    outputs[2][0, 0, :2] = 1
    result = layout.decode_outputs(outputs, (100, 100), 7, "CPUExecutionProvider")
    region = result.regions[0]
    assert region.bbox_px == [10, 10, 90, 30]
    assert region.class_id == 22 and region.label == "text"
    assert region.mask_rle == [0, 2, 39998]
    assert result.page_id == 7 and region.order_key == 8
    outputs[0][0, 1] = 0.5
    assert layout.decode_outputs(outputs, (100, 100), 0, "test").filtered_count == 1


@pytest.mark.parametrize("failure", ["shape", "count", "nan", "label", "mask", "score"])
def test_decode_fails_closed(failure):
    outputs = tensors()
    if failure == "shape":
        outputs[0] = outputs[0][:, :6]
    elif failure == "count":
        outputs[1][0] = 2
    elif failure == "nan":
        outputs[0][0, 2] = np.nan
    elif failure == "label":
        outputs[0][0, 0] = 25
    elif failure == "mask":
        outputs[2][0, 0, 0] = 2
    else:
        outputs[0][0, 1] = 1.1
    with pytest.raises(layout.LayoutUnavailableError):
        layout.decode_outputs(outputs, (100, 100), 0, "test")


def test_geometry_clips_but_preserves_raw_box():
    outputs = tensors()
    outputs[0][0, 2] = -2
    region = layout.decode_outputs(outputs, (100, 100), 0, "test").regions[0]
    assert region.raw_bbox_px[0] == -2 and region.bbox_px[0] == 0
    assert layout.page_box([10, 20, 50, 60], (100, 200), [2, 4, 202, 404]) == [
        22,
        44,
        102,
        124,
    ]


def test_reconciliation_preserves_text_type_and_reorders_only_matched_runs():
    response = sol(
        [100, 100, 900, 300],
        [100, 400, 900, 600],
        [100, 650, 900, 750],
        [100, 800, 900, 950],
    )
    before = response.model_dump()
    regions = page(
        detection(order=20),
        detection((10, 40, 90, 60), row=1, order=10),
        detection((10, 80, 90, 95), row=2, order=0),
    )
    boxes, records, order = layout.reconcile(response, regions, [0, 0, 200, 200])
    assert order == [1, 0, 2, 3]
    assert records[2].status == "sol_only"
    assert boxes[0] == [20, 20, 180, 60]
    assert response.model_dump() == before


@pytest.mark.parametrize(
    "regions",
    [
        [detection(), detection(row=1)],
        [detection((10, 10, 50, 30)), detection((50, 10, 90, 30), row=1)],
    ],
)
def test_duplicate_and_split_regions_do_not_duplicate_sol(regions):
    response = sol([100, 100, 900, 300])
    _, records, order = layout.reconcile(response, page(*regions), [0, 0, 100, 100])
    assert len(records) == 1 and records[0].status == "sol_only" and order == [0]
    assert all("unmatched_v3" in r.issues for r in regions)


def test_one_region_cannot_merge_two_sol_blocks():
    response = sol([100, 100, 500, 300], [500, 100, 900, 300])
    _, records, _ = layout.reconcile(response, page(detection()), [0, 0, 100, 100])
    assert all(
        r.status == "sol_only" and "split_merge_overlap" in r.issues for r in records
    )


def test_iou_boundary_is_not_intersection_percentage():
    response = sol([0, 0, 400, 400])
    # Half-overlap area / union gives exactly 0.5; containment is 1 here.
    _, records, _ = layout.reconcile(
        response, page(detection((0, 0, 80, 40))), [0, 0, 100, 100]
    )
    assert records[0].status == "matched" and records[0].iou == 0.5
    _, records, _ = layout.reconcile(
        response, page(detection((0, 0, 81, 40))), [0, 0, 100, 100]
    )
    assert records[0].status == "sol_only"


def test_unsupported_classes_and_order_ties_are_preserved():
    assert len(layout.LABELS) == len(layout.MAPPING) == 25
    assert not layout.compatible("Form", 21)
    assert not layout.compatible("Code", 1)
    assert layout.compatible("Diagram", 3)
    response = sol([100, 100, 900, 300], [100, 400, 900, 600])
    _, records, order = layout.reconcile(
        response,
        page(detection(order=2), detection((10, 40, 90, 60), row=1, order=2)),
        [0, 0, 100, 100],
    )
    assert order == [0, 1] and all("ambiguous_order" in r.issues for r in records)
    empty = page(detection())
    assert layout.reconcile(sol(), empty, [0, 0, 100, 100]) == ([], [], [])
    assert empty.warnings


class FakeSession:
    def get_provider_graph_assignment_info(self):
        return [
            SimpleNamespace(
                ep_name="CPUExecutionProvider",
                get_nodes=lambda: [SimpleNamespace(op_type="ScatterND")],
            )
        ]

    def get_inputs(self):
        return [
            SimpleNamespace(name=name) for name in ("image", "im_shape", "scale_factor")
        ]

    def get_outputs(self):
        return [SimpleNamespace(name=name) for name in layout.OUTPUTS]

    def __init__(
        self, tmp_path, *, provider="CPUExecutionProvider", error=False, kernels=True
    ):
        self.provider, self.error, self.kernels = provider, error, kernels
        self.path = tmp_path / "profile.json"
        self.calls = 0

    def run(self, names, inputs):
        assert names == layout.OUTPUTS and inputs["image"].shape[0] == 1
        self.calls += 1
        if self.error:
            raise RuntimeError("sensitive backend details must not escape")
        return tensors()

    def end_profiling(self):
        self.path.write_text(
            json.dumps(
                [
                    {
                        "cat": "Node",
                        "name": "fixture_kernel_time",
                        "args": {"provider": self.provider},
                    }
                ]
                if self.kernels
                else []
            )
        )
        return str(self.path)


@pytest.mark.parametrize("failure", ["initialization", "run", "silent_cpu"])
def test_exercised_cuda_fallback(tmp_path, monkeypatch, failure):
    engine = layout.LayoutEngine(tmp_path)
    engine._paths = {}
    attempted = []

    def create(provider):
        attempted.append(provider)
        if provider == "CUDAExecutionProvider" and failure == "initialization":
            raise RuntimeError("DLL unavailable")
        return FakeSession(
            tmp_path,
            provider=provider,
            error=provider == "CUDAExecutionProvider" and failure == "run",
            kernels=failure != "silent_cpu",
        )

    monkeypatch.setattr(engine, "_new_session", create)
    image = Image.new("RGB", (100, 100))
    result = engine.infer(image, 0)
    assert result.provider == "CPUExecutionProvider" and result.warnings
    assert attempted == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    engine.infer(image, 1)
    assert len(attempted) == 2
    assert "Ready" in engine.status


def test_cuda_runtime_failure_latches_cpu(tmp_path, monkeypatch):
    engine = layout.LayoutEngine(tmp_path)
    engine._paths = {}
    gpu = FakeSession(tmp_path, provider="CUDAExecutionProvider")
    cpu = FakeSession(tmp_path)
    monkeypatch.setattr(
        engine, "_new_session", lambda p: gpu if p.startswith("CUDA") else cpu
    )
    image = Image.new("RGB", (100, 100))
    assert engine.infer(image, 0).provider.startswith("CUDA")
    gpu.error = True
    assert engine.infer(image, 1).provider.startswith("CPU")
    assert engine.infer(image, 2).provider.startswith("CPU")
    assert cpu.calls == 2


def test_terminal_failure_is_sanitized_and_retry_is_explicit(tmp_path, monkeypatch):
    engine = layout.LayoutEngine(tmp_path, device="cpu")
    engine._paths = {}
    create = Mock(side_effect=RuntimeError("secret detail"))
    monkeypatch.setattr(engine, "_new_session", create)
    image = Image.new("RGB", (100, 100))
    for _ in range(2):
        with pytest.raises(
            layout.LayoutUnavailableError, match="RuntimeError"
        ) as error:
            engine.infer(image, 0)
        assert "secret detail" not in str(error.value)
    assert create.call_count == 1
    engine.retry_failed()
    monkeypatch.setattr(engine, "_new_session", lambda _: FakeSession(tmp_path))
    assert engine.infer(image, 0).provider.startswith("CPU")


def test_concurrent_jobs_serialize_layout_only(tmp_path, monkeypatch):
    engine = layout.LayoutEngine(tmp_path, device="cpu")
    engine._paths = {}
    active = peak = 0
    guard = threading.Lock()
    session = FakeSession(tmp_path)

    def run(names, inputs):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with guard:
            active -= 1
        return tensors()

    session.run = run
    create = Mock(return_value=session)
    monkeypatch.setattr(engine, "_new_session", create)
    image = Image.new("RGB", (100, 100))
    with ThreadPoolExecutor(max_workers=9) as pool:
        results = list(pool.map(lambda i: engine.infer(image, i), range(9)))
    assert len(results) == 9 and peak == 1 and create.call_count == 1


def test_layout_failure_preserves_sol_and_image(doc_provider, extraction_service):
    captured = []

    def fail(image):
        captured.append(image)
        raise layout.LayoutUnavailableError("CPU unavailable")

    document = DocumentBuilder()(
        doc_provider, extraction_service, SimpleNamespace(analyze=fail)
    )
    assert extraction_service.called
    captured[0].getpixel((0, 0))  # Borrowed image remains available for exports.
    assert all(
        p.status == "sol_fallback" for p in document.layout.page_runtime.values()
    )
    assert all(
        p.failure_stage == "inference" for p in document.layout.page_runtime.values()
    )
    assert all(
        "layout_unavailable" in b.layout.issues
        for page in document.pages
        for b in page.children
    )


def test_sol_failure_still_propagates_after_layout_fallback(doc_provider):
    service = Mock(side_effect=RuntimeError("Sol failed"))
    with pytest.raises(RuntimeError, match="Sol failed"):
        DocumentBuilder()(doc_provider, service, layout.SolFallbackEngine())
    assert service.called
    for call in service.call_args_list:
        with pytest.raises(ValueError):
            call.args[1].getpixel((0, 0))


@pytest.mark.parametrize(
    "regions", [[], [detection(kind=21)], [detection((0, 80, 20, 100))]]
)
def test_missed_or_mismatched_regions_keep_sol_geometry_content_order(regions):
    response = sol([100, 100, 900, 300])
    original = response.model_dump()
    boxes, records, order = layout.reconcile(response, page(*regions), [0, 0, 100, 100])
    assert boxes == [[10, 10, 90, 30]] and order == [0]
    assert records[0].status == "sol_only"
    assert response.model_dump() == original


def test_builder_uses_same_image_and_request(doc_provider, extraction_service):
    images = []

    def analyze(image):
        images.append(image)
        return LayoutAnalysis(
            image_size=image.size,
            provider="test",
            model_id="test",
            model_revision="fixture",
            actual_device="cpu",
            elapsed_ms=0,
            candidate_count=0,
            filtered_count=0,
            regions=[],
        )

    document = DocumentBuilder()(
        doc_provider, extraction_service, SimpleNamespace(analyze=analyze)
    )
    for call in extraction_service.call_args_list:
        assert any(call.args[1] is image for image in images)
        assert call.args[3] is ExtractedPage
    assert document.layout.manifest["pipeline"] == layout.PIPELINE


def test_cache_offline_checksum_and_warm_resolution(tmp_path, monkeypatch):
    import hashlib

    import huggingface_hub
    from huggingface_hub.errors import LocalEntryNotFoundError

    model = tmp_path / "inference.onnx"
    model.write_bytes(b"fixture")
    config = tmp_path / "inference.yml"
    config.write_text(
        "label_list:\n" + "".join(f"- {label}\n" for label in layout.LABELS)
    )
    monkeypatch.setattr(
        layout,
        "HASHES",
        {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (model, config)},
    )
    download = Mock(side_effect=lambda **kw: str(tmp_path / kw["filename"]))
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    assert layout.model_files(tmp_path, True)["inference.onnx"] == model
    assert all(call.kwargs["local_files_only"] for call in download.call_args_list)
    model.write_bytes(b"corrupt")
    with pytest.raises(layout.LayoutUnavailableError, match="checksum"):
        layout.model_files(tmp_path, True)
    download.side_effect = LocalEntryNotFoundError("missing")
    with pytest.raises(layout.LayoutUnavailableError, match="offline"):
        layout.model_files(tmp_path, True)


def test_fingerprint_has_no_model_initialization(monkeypatch):
    monkeypatch.setattr(
        layout, "model_files", Mock(side_effect=AssertionError("network"))
    )
    a = layout.pipeline_manifest({"highres_image_dpi": 192})
    assert a == layout.pipeline_manifest({"highres_image_dpi": 192})
    assert (
        a["fingerprint"]
        != layout.pipeline_manifest({"highres_image_dpi": 96})["fingerprint"]
    )


def test_merge_lineage_retains_original_match():
    first = SimpleNamespace(
        layout=BlockLayout(
            status="matched",
            region_row=7,
            sol_ordinal=2,
            sources=[
                SourceRegion(block_id="/page/0/Table/0", page_id=0, bbox=[0, 0, 10, 10])
            ],
        )
    )
    second = SimpleNamespace(
        layout=BlockLayout(
            status="sol_only",
            sources=[
                SourceRegion(block_id="/page/1/Table/0", page_id=1, bbox=[0, 0, 10, 10])
            ],
        )
    )
    layout.merge_lineage(first, [second])
    assert first.layout.status == "processor" and first.layout.region_row == 7
    assert len(first.layout.sources) == 2 and first.layout.sol_ordinal == 2


def test_chunk_page_ids_and_annotations_follow_structure(pdf_document):
    from doclayout.renderers.chunk import ChunkRenderer
    from doclayout.ui.exports import annotations

    first = pdf_document.pages[0]
    first.structure = first.structure[1:2]
    chunks = ChunkRenderer()(pdf_document)
    assert all(block.page == int(block.id.split("/")[2]) for block in chunks.blocks)
    assert chunks.blocks[0].id == str(first.structure[0])
    overlays = annotations(pdf_document)
    assert overlays["drawn"] == sum(
        not pdf_document.get_block(b).ignore_for_output
        for p in pdf_document.pages
        for b in p.structure
    )


def test_cli_existing_output_requires_matching_pipeline(tmp_path):
    from doclayout.output import output_exists

    (tmp_path / "sample.md").write_text("historical")
    assert output_exists(str(tmp_path), "sample")
    assert not output_exists(str(tmp_path), "sample", fingerprint="new")
    (tmp_path / "sample_metadata.json").write_text(
        json.dumps({"layout": {"manifest": {"fingerprint": "new"}}})
    )
    assert output_exists(str(tmp_path), "sample", fingerprint="new")


def test_http_layout_failure_is_service_unavailable():
    import asyncio

    from fastapi import HTTPException

    from doclayout.scripts.server import _run

    def unavailable():
        raise layout.LayoutUnavailableError("Layout files missing offline.")

    with pytest.raises(HTTPException) as error:
        asyncio.run(_run(unavailable))
    assert error.value.status_code == 503
    assert error.value.detail == "Layout files missing offline."


def test_multi_page_lineage_never_invents_quote_location():
    from doclayout.fields import ground_records

    data = {
        "records": [
            {
                "fields": {"member_id": "42"},
                "evidence": [{"field_path": "/member_id", "quote": "Member 42"}],
                "issues": [],
            }
        ],
        "document_issues": [],
    }
    chunks = {
        "blocks": [
            {
                "id": "/page/0/Table/0",
                "html": "Member 42",
                "page": 0,
                "bbox": [0, 0, 100, 100],
            }
        ],
        "metadata": {"layout": {"blocks": {"/page/0/Table/0": {"multi_page": True}}}},
    }
    result = ground_records(data, "Member 42", chunks)
    evidence = result["records"][0]["evidence"][0]
    assert evidence["verified"] and not evidence["locations"]
    assert "multiple source pages" in result["records"][0]["issues"][0]["reason"]
