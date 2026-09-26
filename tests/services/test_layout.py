"""Offline layout runtime tests: no weights, native sessions, or Sol requests."""

import hashlib
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from doclayout.services import layout


class LocalEntryNotFoundError(Exception):
    pass


class PaddleDependencyError(RuntimeError):
    pass


def fake_model(provider=layout.CPU_PROVIDER):
    session = SimpleNamespace(
        get_providers=Mock(return_value=[provider]), disable_fallback=Mock()
    )
    return SimpleNamespace(
        paddlex_predictor=SimpleNamespace(runner=SimpleNamespace(session=session)),
        predict=Mock(return_value=[{"boxes": []}]),
        close=Mock(),
    )


@pytest.fixture(autouse=True)
def clean_runtime_registry():
    layout._runtimes.clear()
    yield
    layout._runtimes.clear()


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    """Replace only external dependencies; exercise the real cache/state logic."""
    cache = tmp_path / "layout"
    snapshot = cache / "hub" / "snapshots" / layout.MODEL_REVISION
    snapshot.mkdir(parents=True)
    payloads = {"inference.onnx": b"fake onnx", "inference.yml": b"fake config"}
    for filename, data in payloads.items():
        (snapshot / filename).write_bytes(data)
    monkeypatch.setattr(
        layout,
        "ARTIFACT_FILES",
        {
            filename: (len(data), hashlib.sha256(data).hexdigest())
            for filename, data in payloads.items()
        },
    )
    errors = ModuleType("huggingface_hub.errors")
    monkeypatch.setattr(
        errors, "LocalEntryNotFoundError", LocalEntryNotFoundError, raising=False
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", errors)

    def download(**kwargs):
        path = snapshot / kwargs["filename"]
        if kwargs["local_files_only"]:
            if not path.exists():
                raise LocalEntryNotFoundError()
        else:
            path.write_bytes(payloads[kwargs["filename"]])
        return str(path)

    models = []

    def construct(**kwargs):
        model = fake_model(kwargs["engine_config"]["providers"][0])
        models.append(model)
        return model

    downloader = Mock(side_effect=download)
    factory = Mock(side_effect=construct)
    ort = SimpleNamespace(preload_dlls=Mock())
    dependencies = Mock(return_value=(ort, factory, downloader, PaddleDependencyError))
    monkeypatch.setattr(layout, "_dependencies", dependencies)
    return SimpleNamespace(
        cache=cache,
        snapshot=snapshot,
        download=downloader,
        factory=factory,
        models=models,
        ort=ort,
        dependencies=dependencies,
        image=Image.new("RGB", (320, 480), (10, 20, 30)),
    )


def service(runtime, device="cpu"):
    return layout.LayoutService(device=device, cache_dir=runtime.cache)


@pytest.mark.parametrize("device", ["cpu", "auto", "cuda"])
def test_lazy_cached_session_and_actual_device(runtime, device):
    instance = service(runtime, device)
    runtime.dependencies.assert_not_called()
    first = instance.predict(runtime.image)
    second = service(runtime, device).predict(runtime.image)
    expected = layout.CPU_PROVIDER if device == "cpu" else layout.CUDA_PROVIDER
    assert first.provider == second.provider == expected
    assert first.actual_device == ("cpu" if device == "cpu" else "cuda:0")
    assert first.model_id == layout.MODEL_ID
    assert first.revision == layout.MODEL_REVISION
    assert first.image_size == (320, 480)
    assert first.elapsed_seconds >= 0
    assert first.regions == ()
    runtime.dependencies.assert_called_once()
    runtime.factory.assert_called_once()
    model = runtime.models[0]
    assert model.predict.call_count == 3  # One real warm-up, then two pages.
    model.paddlex_predictor.runner.session.disable_fallback.assert_called_once()
    assert runtime.ort.preload_dlls.call_count == (0 if device == "cpu" else 1)
    assert runtime.factory.call_args.kwargs["model_dir"] == str(runtime.snapshot)
    assert runtime.factory.call_args.kwargs["engine"] == "onnxruntime"
    for call in model.predict.call_args_list:
        assert call.kwargs == {
            "batch_size": 1,
            "layout_shape_mode": "rect",
            "skip_order_labels": [],
        }
    page = model.predict.call_args.args[0]
    assert page.flags.c_contiguous
    assert page.dtype == np.uint8
    assert page[0, 0].tolist() == [30, 20, 10]  # RGB -> BGR, no double normalization.
    assert runtime.image.getpixel((0, 0)) == (10, 20, 30)


def test_cache_hit_never_uses_network(runtime):
    service(runtime).predict(runtime.image)
    assert runtime.download.call_count == 2
    for call in runtime.download.call_args_list:
        assert call.kwargs["local_files_only"] is True
        assert call.kwargs["revision"] == layout.MODEL_REVISION
        assert call.kwargs["repo_id"] == layout.MODEL_ID


@pytest.mark.parametrize("device", ["cpu", "auto", "cuda"])
def test_prepare_shares_one_warmup_with_predictions(runtime, device):
    instance = service(runtime, device)
    with ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(lambda _: instance.prepare(), range(3)))
    assert reports[0] == reports[1] == reports[2]
    ready = reports[0]
    result = service(runtime, device).predict(runtime.image)
    assert ready.actual_device == result.actual_device
    assert ready.provider == result.provider
    assert ready.elapsed_seconds == result.preparation_seconds > 0
    assert ready.fallback_reason is result.fallback_reason is None
    runtime.factory.assert_called_once()
    assert runtime.models[0].predict.call_count == 2


def test_preparation_error_is_sticky_and_typed(runtime):
    runtime.dependencies.side_effect = layout.LayoutDependencyError("missing")
    for _ in range(2):
        with pytest.raises(layout.LayoutDependencyError):
            service(runtime).prepare()
    runtime.dependencies.assert_called_once()
    runtime.factory.assert_not_called()


def test_preparation_fallback_report_is_safe(runtime):
    runtime.factory.side_effect = [RuntimeError("private payload"), fake_model()]
    instance = service(runtime, "auto")
    ready = instance.prepare()
    assert ready.provider == layout.CPU_PROVIDER
    assert (
        ready.fallback_reason
        == "CUDA initialization/warm-up failed (RuntimeError); using CPU."
    )
    result = instance.predict(runtime.image)
    assert result.fallback_reason == ready.fallback_reason
    assert instance.prepare() == ready
    assert runtime.factory.call_count == 2


def test_partial_cache_downloads_only_absent_file(runtime):
    (runtime.snapshot / "inference.onnx").unlink()
    service(runtime).predict(runtime.image)
    network = [
        call
        for call in runtime.download.call_args_list
        if not call.kwargs["local_files_only"]
    ]
    assert len(network) == 1
    assert network[0].kwargs["filename"] == "inference.onnx"
    assert network[0].kwargs["revision"] == layout.MODEL_REVISION


@pytest.mark.parametrize("data", [b"", b"xxxxxxxxx", b"<html>bad download</html>"])
def test_corrupt_cache_is_typed_and_never_replaced(runtime, data):
    path = runtime.snapshot / "inference.onnx"
    path.write_bytes(data)
    with pytest.raises(layout.LayoutArtifactError, match="Corrupt layout artifact"):
        service(runtime).predict(runtime.image)
    assert path.read_bytes() == data
    assert all(
        call.kwargs["local_files_only"] for call in runtime.download.call_args_list
    )
    runtime.factory.assert_not_called()


def test_bad_download_is_not_loaded(runtime):
    (runtime.snapshot / "inference.yml").write_bytes(b"truncated")
    runtime.download.side_effect = [
        LocalEntryNotFoundError(),
        str(runtime.snapshot / "inference.yml"),
    ]
    with pytest.raises(layout.LayoutArtifactError):
        service(runtime).predict(runtime.image)
    runtime.factory.assert_not_called()


@pytest.mark.parametrize(
    "error", [PermissionError("denied"), ConnectionError("offline")]
)
def test_cache_errors(runtime, error):
    runtime.download.side_effect = error
    with pytest.raises(layout.LayoutCacheError):
        service(runtime).predict(runtime.image)
    runtime.factory.assert_not_called()


def test_unwritable_cache_directory(runtime, monkeypatch):
    monkeypatch.setattr(layout.Path, "mkdir", Mock(side_effect=PermissionError()))
    with pytest.raises(layout.LayoutCacheError, match="Cannot create"):
        service(runtime).predict(runtime.image)
    runtime.dependencies.assert_not_called()


@pytest.mark.parametrize("failure", ["setup", "substitution", "warmup", "after_warmup"])
@pytest.mark.parametrize("device", ["auto", "cuda"])
def test_cuda_startup_failure_policy(runtime, failure, device):
    gpu = fake_model(layout.CUDA_PROVIDER)
    cpu = fake_model()
    session = gpu.paddlex_predictor.runner.session
    if failure == "setup":
        first = RuntimeError("CUDA DLL missing")
    else:
        first = gpu
        if failure == "substitution":
            session.get_providers.return_value = [layout.CPU_PROVIDER]
        elif failure == "warmup":
            gpu.predict.side_effect = RuntimeError("CUDA kernel failure")
        else:
            session.get_providers.side_effect = [
                [layout.CUDA_PROVIDER],
                [layout.CPU_PROVIDER],
            ]
    runtime.factory.side_effect = [first, cpu]
    if device == "auto":
        result = service(runtime, device).predict(runtime.image)
        assert result.provider == layout.CPU_PROVIDER
        service(runtime, device).predict(runtime.image)
        assert runtime.factory.call_count == 2
        assert cpu.predict.call_count == 3
    else:
        for _ in range(2):
            with pytest.raises(
                layout.LayoutDeviceError, match="CPU fallback is disabled"
            ):
                service(runtime, device).predict(runtime.image)
        assert runtime.factory.call_count == 1
        cpu.predict.assert_not_called()
    if failure != "setup":
        gpu.close.assert_called_once()


def test_auto_later_cuda_failure_retries_once_then_stays_cpu(runtime):
    gpu, cpu = fake_model(layout.CUDA_PROVIDER), fake_model()
    gpu.predict.side_effect = [[{"boxes": []}], RuntimeError("GPU lost")]
    runtime.factory.side_effect = [gpu, cpu]
    result = service(runtime, "auto").predict(runtime.image)
    assert result.provider == layout.CPU_PROVIDER
    assert (
        result.fallback_reason
        == "CUDA page inference failed (RuntimeError); using CPU."
    )
    assert service(runtime, "auto").prepare().fallback_reason == result.fallback_reason
    service(runtime, "auto").predict(runtime.image)
    assert runtime.factory.call_count == 2
    assert gpu.predict.call_count == 2
    assert cpu.predict.call_count == 3
    gpu.close.assert_called_once()


def test_explicit_cuda_later_failure_does_not_fallback(runtime):
    gpu = fake_model(layout.CUDA_PROVIDER)
    gpu.predict.side_effect = [[{"boxes": []}], RuntimeError("GPU lost")]
    runtime.factory.side_effect = [gpu]
    with pytest.raises(layout.LayoutInferenceError, match="no device fallback"):
        service(runtime, "cuda").predict(runtime.image)
    assert runtime.factory.call_count == 1


@pytest.mark.parametrize("stage", ["initialization", "retry"])
def test_cpu_fallback_failure_is_typed(runtime, stage):
    gpu, cpu = fake_model(layout.CUDA_PROVIDER), fake_model()
    gpu.predict.side_effect = [[{"boxes": []}], RuntimeError("GPU lost")]
    cpu.predict.side_effect = (
        RuntimeError("CPU failed")
        if stage == "initialization"
        else [[{"boxes": []}], RuntimeError("CPU failed")]
    )
    runtime.factory.side_effect = [gpu, cpu]
    with pytest.raises(layout.LayoutInferenceError, match="CPU"):
        service(runtime, "auto").predict(runtime.image)
    if stage == "initialization":
        with pytest.raises(layout.LayoutInferenceError):
            service(runtime, "auto").predict(runtime.image)
    assert runtime.factory.call_count == 2


def test_missing_dependency_is_not_misreported_as_cuda_failure(runtime):
    runtime.factory.side_effect = ImportError("missing optional module")
    with pytest.raises(layout.LayoutDependencyError):
        service(runtime, "auto").predict(runtime.image)
    runtime.factory.assert_called_once()


def test_wrapped_paddlex_dependency_failure_is_typed(runtime):
    error = RuntimeError("PaddleOCR predictor creation failed")
    error.__cause__ = PaddleDependencyError("ocr-core dependency missing")
    runtime.factory.side_effect = error
    with pytest.raises(layout.LayoutDependencyError):
        service(runtime, "auto").predict(runtime.image)
    runtime.factory.assert_called_once()


def test_unsupported_python_fails_before_optional_import(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "version_info", (3, 10))
    with pytest.raises(layout.LayoutDependencyError, match="3.11"):
        layout._dependencies(tmp_path)


def test_opencv_blank_page_regression():
    from doclayout.processors.blank_page import BlankPageProcessor

    image = Image.new("RGB", (128, 128), "white")
    processor = BlankPageProcessor()
    assert processor.is_blank(image)
    image.paste("black", (20, 20, 100, 100))
    assert not processor.is_blank(image)


def test_three_concurrent_callers_share_one_serial_session(runtime):
    barrier, counter_lock = Barrier(3), Lock()
    active = maximum = 0
    model = fake_model()

    def predict(*args, **kwargs):
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with counter_lock:
            active -= 1
        return [{"boxes": []}]

    model.predict.side_effect = predict
    runtime.factory.side_effect = [model]

    def page(_):
        barrier.wait(timeout=5)
        return service(runtime).predict(runtime.image)

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(page, range(3)))
    assert len(results) == 3
    assert maximum == 1
    runtime.factory.assert_called_once()
    assert model.predict.call_count == 4


def test_explicit_modes_do_not_reuse_auto_cpu_fallback(runtime):
    runtime.factory.side_effect = [
        RuntimeError("no CUDA"),
        fake_model(),
        fake_model(),
        RuntimeError("no CUDA"),
    ]
    assert service(runtime, "auto").predict(runtime.image).actual_device == "cpu"
    assert service(runtime, "cpu").predict(runtime.image).actual_device == "cpu"
    with pytest.raises(layout.LayoutDeviceError):
        service(runtime, "cuda").predict(runtime.image)
    assert runtime.factory.call_count == 4


LABELS = [
    "abstract",
    "algorithm",
    "aside_text",
    "chart",
    "content",
    "display_formula",
    "doc_title",
    "figure_title",
    "footer",
    "footer_image",
    "footnote",
    "formula_number",
    "header",
    "header_image",
    "image",
    "inline_formula",
    "number",
    "paragraph_title",
    "reference",
    "reference_content",
    "seal",
    "table",
    "text",
    "vertical_text",
    "vision_footnote",
]


def box(class_id=22, order=1, rectangle=(10, 20, 120, 100)):
    return {
        "cls_id": np.int64(class_id),
        "label": LABELS[class_id],
        "score": np.float32(0.75),
        "coordinate": rectangle,
        "order": np.int64(order),
    }


def test_all_class_ids_and_original_scores_are_retained(runtime):
    boxes = [box(i, i + 1) for i in range(25)]
    model = fake_model()
    model.predict.return_value = [{"boxes": boxes[::-1]}]
    runtime.factory.side_effect = [model]
    regions = service(runtime).predict(runtime.image).regions
    assert [r.class_id for r in regions] == list(range(25))
    assert [r.label for r in regions] == LABELS
    assert [r.order_index for r in regions] == list(range(1, 26))
    assert all(r.score == pytest.approx(0.75) for r in regions)
    assert regions[0].as_polygon_box().polygon == [
        [10, 20],
        [120, 20],
        [120, 100],
        [10, 100],
    ]
    assert not hasattr(regions[0], "polygon")


@pytest.mark.parametrize(
    "boxes",
    [
        [],
        np.empty((0, 6)),
        [box(14), box(20, 2)],  # Graphic-only: image and seal keep reading order.
        [
            box(order=2, rectangle=(10, 200, 120, 300)),
            box(order=1),
            box(order=3, rectangle=(200, 0, 300, 100)),
        ],  # Left column finishes first.
        [
            box(order=1),
            box(order=2, rectangle=(10, 80, 120, 150)),
        ],  # Split/overlapping paragraphs stay separate.
        [box(rectangle=(0, 0, 320, 480))],  # One merged region stays one region.
    ],
)
def test_blank_graphic_columns_and_split_merge_are_not_reinterpreted(runtime, boxes):
    model = fake_model()
    model.predict.return_value = [{"boxes": boxes}]
    runtime.factory.side_effect = [model]
    regions = service(runtime).predict(runtime.image).regions
    assert len(regions) == len(boxes)
    assert [r.bbox for r in regions] == [
        tuple(b["coordinate"]) for b in sorted(boxes, key=lambda b: b["order"])
    ]


@pytest.mark.parametrize(
    "output",
    [
        [],
        [{"boxes": [box(order=0)]}],
        [{"boxes": [box(), box()]}],
        [{"boxes": [dict(box(), score=float("nan"))]}],
        [{"boxes": [dict(box(), coordinate=(-1, 0, 10, 10))]}],
        [{"boxes": [dict(box(), coordinate=(0, 0, 400, 500))]}],
        [{"boxes": [dict(box(), order=None)]}],
        [{"unexpected": []}],
    ],
)
def test_invalid_output_does_not_trigger_cpu_retry(runtime, output):
    model = fake_model(layout.CUDA_PROVIDER)
    model.predict.return_value = output
    runtime.factory.side_effect = [model]
    with pytest.raises(layout.LayoutInferenceError, match="rectangle-mode result"):
        service(runtime, "auto").predict(runtime.image)
    runtime.factory.assert_called_once()


def test_validation_precedes_loading(runtime):
    with pytest.raises(ValueError, match="device"):
        service(runtime, "bogus")
    with pytest.raises(ValueError, match="nonempty PIL"):
        service(runtime).predict(Image.new("RGB", (0, 0)))
    runtime.dependencies.assert_not_called()


def test_cache_resolution_failure_is_lazy_and_typed(monkeypatch, tmp_path):
    from pathlib import Path

    from doclayout.services.layout import LayoutCacheError, LayoutService

    service = LayoutService(cache_dir=tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", Mock(side_effect=OSError("private path")))
        with pytest.raises(LayoutCacheError):
            service.prepare()
        with pytest.raises(LayoutCacheError):
            service.predict(Image.new("RGB", (10, 10)))


def test_base_import_without_extra_or_network(tmp_path):
    code = """
import importlib.abc
import pathlib
import socket
import sys
class WithoutLayout(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'paddleocr', 'paddlex', 'onnxruntime', 'huggingface_hub'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, WithoutLayout())
def no_network(*args, **kwargs):
    raise AssertionError('network during import')
socket.socket.connect = no_network
import doclayout
from doclayout.converters.pdf import PdfConverter
from doclayout.models import create_model_dict
from doclayout.services.layout import LayoutService, LayoutDependencyError
from PIL import Image
cache = pathlib.Path(sys.argv[1])
service = LayoutService(cache_dir=cache)
assert not cache.exists()
try:
    service.predict(Image.new('RGB', (10, 10)))
except LayoutDependencyError:
    pass
else:
    raise AssertionError('missing extra did not raise typed error')
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "absent")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
