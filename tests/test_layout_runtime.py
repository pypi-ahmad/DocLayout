"""Runtime-only layout tests: no weights, network, GPU, or model API requests."""

import hashlib
import json
import subprocess
import sys
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from doclayout import layout
from doclayout.schema.layout import LayoutAnalysis, PageRegions
from doclayout.settings import Settings

# Capture before the shared offline conversion fixture injects its fake getter.
process_engine = layout.get_layout_engine


def tensors(rows=None):
    boxes = np.array(
        rows if rows is not None else [[22, 0.9, 20, 10, 180, 90, 42]],
        dtype=np.float32,
    ).reshape(-1, 7)
    return [
        boxes,
        np.array([len(boxes)], dtype=np.int32),
        np.zeros((len(boxes), 200, 200), dtype=np.int32),
    ]


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

    def __init__(self, directory, provider, *, kernel=True, fail_on=()):
        self.provider = provider
        self.kernel = kernel
        self.fail_on = fail_on
        self.calls = 0
        self.profiles = 0
        self.path = directory / f"{provider}.json"

    def run(self, names, inputs):
        assert names == layout.OUTPUTS
        assert inputs["image"].shape == (1, 3, 800, 800)
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("private native error details")
        return tensors()

    def end_profiling(self):
        self.profiles += 1
        self.path.write_text(
            json.dumps(
                [
                    {
                        "cat": "Node" if self.kernel else "Session",
                        "name": "fixture_kernel_time",
                        "args": {"provider": self.provider},
                    }
                ]
            ),
            encoding="utf-8",
        )
        return str(self.path)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    dependencies = Mock()
    files = Mock(return_value={"inference.onnx": tmp_path / "inference.onnx"})
    monkeypatch.setattr(layout, "check_runtime_dependencies", dependencies)
    monkeypatch.setattr(layout, "model_files", files)
    monkeypatch.setattr(layout.settings, "DOCLAYOUT_LAYOUT_MODEL_DIR", None)
    return dependencies, files


def test_prepare_once_across_jobs_and_no_page_reprobes(tmp_path, monkeypatch, isolated):
    engine = layout.LayoutEngine(tmp_path, device="cpu")
    session = FakeSession(tmp_path, "CPUExecutionProvider")
    create = Mock(return_value=session)
    monkeypatch.setattr(engine, "_new_session", create)
    borrowed = []
    analyze = engine.analyze

    def capture(image):
        borrowed.append(image)
        assert image.size == (800, 800) and image.getpixel((0, 0)) == (255, 255, 255)
        return analyze(image)

    monkeypatch.setattr(engine, "analyze", capture)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(lambda _: engine.prepare(), range(9))) == [None] * 9
    assert len(borrowed) == create.call_count == session.calls == 1
    with pytest.raises(ValueError):
        borrowed[0].getpixel((0, 0))
    assert isolated[0].call_count == isolated[1].call_count == 1
    assert engine.actual_device == "cpu"
    with Image.new("RGB", (200, 100)) as image:
        result = analyze(image)
    engine.prepare()
    assert result.image_size == (200, 100) and session.calls == 2
    assert create.call_count == 1 and isolated[1].call_count == 1


@pytest.mark.parametrize(
    "device,kernel,expected",
    [("auto", True, "cuda"), ("cuda", True, "cuda"), ("auto", False, "cpu")],
)
def test_prepare_uses_exercised_provider(
    tmp_path, monkeypatch, isolated, device, kernel, expected
):
    engine = layout.LayoutEngine(tmp_path, device=device)
    sessions = []

    def create(provider):
        session = FakeSession(tmp_path, provider, kernel=kernel)
        sessions.append(session)
        return session

    monkeypatch.setattr(engine, "_new_session", create)
    engine.prepare()
    engine.prepare()
    assert engine.actual_device == expected
    assert len(sessions) == (2 if expected == "cpu" else 1)
    assert all(s.calls == 1 for s in sessions)
    assert sessions[0].profiles == 1 and not sessions[0].path.exists()


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_failed_prepare_latches_sanitized_error_until_retry(
    tmp_path, monkeypatch, isolated, device
):
    engine = layout.LayoutEngine(tmp_path, device=device)
    create = Mock(side_effect=RuntimeError("PRIVATE provider detail"))
    monkeypatch.setattr(engine, "_new_session", create)
    for _ in range(2):
        with pytest.raises(layout.LayoutModelUnavailable) as error:
            engine.prepare()
        assert "PRIVATE" not in str(error.value)
    assert create.call_count == 1 and engine.actual_device is None
    assert engine.status.startswith("Failed:")
    engine.retry_failed()
    provider = "CPUExecutionProvider" if device == "cpu" else "CUDAExecutionProvider"
    create.side_effect = None
    create.return_value = FakeSession(tmp_path, provider)
    engine.prepare()
    assert create.call_count == 2 and engine.actual_device == device


def test_analyze_timing_provenance_and_legacy_shape(tmp_path, monkeypatch, isolated):
    engine = layout.LayoutEngine(tmp_path, device="cpu")
    session = FakeSession(tmp_path, "CPUExecutionProvider")
    create = Mock(return_value=session)
    monkeypatch.setattr(engine, "_new_session", create)
    monkeypatch.setattr(
        layout, "perf_counter", Mock(side_effect=[1.0, 1.125, 2.0, 2.25])
    )
    image = Image.new("RGB", (200, 100), "red")
    result = engine.analyze(image)
    assert isinstance(result, LayoutAnalysis)
    assert result.elapsed_ms == 125
    assert result.model_id == layout.REPO and result.model_revision == layout.REVISION
    assert result.actual_device == engine.actual_device == "cpu"
    assert result.image_size == (200, 100)
    assert result.regions[0].raw_bbox_px == [20, 10, 180, 90]
    assert result.regions[0].order_key == 42
    assert result.order_key_source == "model_output"
    assert result.observed_rank_source == "derived_sort"
    assert "page_id" not in result.model_dump()
    old = engine.infer(image, 9)
    assert isinstance(old, PageRegions) and old.page_id == 9
    assert set(old.model_dump()) == {
        "page_id",
        "image_size",
        "provider",
        "candidate_count",
        "filtered_count",
        "regions",
        "warnings",
    }
    assert old.regions == result.regions
    assert session.calls == 2 and session.profiles == 0
    assert create.call_count == 1
    assert all(mock.call_count == 1 for mock in isolated)
    assert image.size == (200, 100) and image.getpixel((0, 0)) == (255, 0, 0)


def test_first_run_races_share_one_engine_and_preparation(
    tmp_path, monkeypatch, isolated
):
    engine = layout.LayoutEngine(tmp_path, device="cpu")
    created = Mock(return_value=engine)
    registered = Mock()
    monkeypatch.setattr(layout, "LayoutEngine", created)
    monkeypatch.setattr(layout, "_engine", None)
    monkeypatch.setattr(layout.atexit, "register", registered)
    session = FakeSession(tmp_path, "CPUExecutionProvider")
    create = Mock(return_value=session)
    monkeypatch.setattr(engine, "_new_session", create)
    barrier = threading.Barrier(9)
    guard = threading.Lock()
    active = peak = 0
    original = session.run

    def run(*args):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.005)
        result = original(*args)
        with guard:
            active -= 1
        return result

    session.run = run

    def work(_):
        barrier.wait(timeout=10)
        with Image.new("RGB", (200, 100)) as image:
            return process_engine().analyze(image)

    with ThreadPoolExecutor(max_workers=9) as pool:
        results = list(pool.map(work, range(9)))
    assert len(results) == session.calls == 9 and peak == 1
    assert created.call_count == registered.call_count == create.call_count == 1
    assert all(mock.call_count == 1 for mock in isolated)


@pytest.mark.parametrize("device", ["auto", "cuda"])
def test_cuda_success_profiles_only_initial_execution(
    tmp_path, monkeypatch, isolated, device
):
    engine = layout.LayoutEngine(tmp_path, device=device)
    session = FakeSession(tmp_path, "CUDAExecutionProvider")
    create = Mock(return_value=session)
    monkeypatch.setattr(engine, "_new_session", create)
    for _ in range(3):
        result = engine.analyze(Image.new("RGB", (200, 100)))
        assert result.actual_device == engine.actual_device == "cuda"
        assert not result.warnings
    assert session.calls == 3 and session.profiles == create.call_count == 1
    assert not session.path.exists()


@pytest.mark.parametrize("failure", ["initialization", "execution", "profile", "later"])
def test_explicit_cuda_never_falls_back(tmp_path, monkeypatch, isolated, failure):
    engine = layout.LayoutEngine(tmp_path, device="cuda")
    session = FakeSession(
        tmp_path,
        "CUDAExecutionProvider",
        kernel=failure != "profile",
        fail_on=(2,) if failure == "later" else (1,) if failure == "execution" else (),
    )
    create = Mock(return_value=session)
    if failure == "initialization":
        create.side_effect = RuntimeError("private DLL details")
    monkeypatch.setattr(engine, "_new_session", create)
    image = Image.new("RGB", (200, 100))
    if failure == "later":
        assert engine.analyze(image).actual_device == "cuda"
    for _ in range(2):
        with pytest.raises(
            layout.LayoutModelUnavailable, match="CPU fallback is disabled"
        ) as exc:
            engine.analyze(image)
        assert "private" not in str(exc.value)
    assert engine.actual_device is None
    assert create.call_args_list == [(("CUDAExecutionProvider",),)]


@pytest.mark.parametrize("failure", ["initialization", "execution", "profile"])
def test_auto_fallback_is_exercised_and_latched(
    tmp_path, monkeypatch, isolated, failure
):
    engine = layout.LayoutEngine(tmp_path, device="auto")
    cpu = FakeSession(tmp_path, "CPUExecutionProvider")
    gpu = FakeSession(
        tmp_path,
        "CUDAExecutionProvider",
        kernel=failure != "profile",
        fail_on=(1,) if failure == "execution" else (),
    )

    def create(provider):
        if provider == "CPUExecutionProvider":
            return cpu
        if failure == "initialization":
            raise RuntimeError("DLL failed")
        return gpu

    factory = Mock(side_effect=create)
    monkeypatch.setattr(engine, "_new_session", factory)
    for _ in range(2):
        result = engine.analyze(Image.new("RGB", (200, 100)))
        assert result.actual_device == engine.actual_device == "cpu"
        assert result.warnings and "CPU fallback" in engine.status
    assert cpu.calls == 2 and factory.call_count == 2


def test_failed_cuda_session_released_before_cpu_creation(
    tmp_path, monkeypatch, isolated
):
    engine = layout.LayoutEngine(tmp_path)
    gpu_ref = None

    def create(provider):
        nonlocal gpu_ref
        if provider == "CPUExecutionProvider":
            assert gpu_ref() is None
            return FakeSession(tmp_path, provider)
        session = FakeSession(tmp_path, provider, fail_on=(2,))
        gpu_ref = weakref.ref(session)
        return session

    monkeypatch.setattr(engine, "_new_session", create)
    image = Image.new("RGB", (200, 100))
    assert engine.analyze(image).actual_device == "cuda"
    assert engine.analyze(image).actual_device == "cpu"


@pytest.mark.parametrize("device", ["cpu", "auto"])
def test_cpu_failure_is_typed_and_requires_explicit_retry(
    tmp_path, monkeypatch, isolated, device
):
    engine = layout.LayoutEngine(tmp_path, device=device)
    create = Mock(side_effect=RuntimeError("private failure"))
    monkeypatch.setattr(engine, "_new_session", create)
    for _ in range(3):
        with pytest.raises(layout.LayoutModelUnavailable) as exc:
            engine.analyze(Image.new("RGB", (200, 100)))
        assert "private" not in str(exc.value)
    assert create.call_count == (2 if device == "auto" else 1)
    assert engine.actual_device is None
    assert layout.LayoutUnavailableError is layout.LayoutModelUnavailable
    engine.retry_failed()
    create.side_effect = None
    create.return_value = FakeSession(tmp_path, "CPUExecutionProvider")
    engine.device = "cpu"
    assert not engine.analyze(Image.new("RGB", (200, 100))).warnings


@pytest.mark.parametrize("module", ["onnxruntime", "cv2", "huggingface_hub", "yaml"])
def test_missing_dependencies_precede_download(tmp_path, monkeypatch, module):
    download = Mock(side_effect=AssertionError("must not download"))
    imported = layout.import_module

    def missing(name):
        if name == module:
            raise ImportError("private loader details")
        return imported(name)

    monkeypatch.setattr(layout, "import_module", missing)
    monkeypatch.setattr(layout, "model_files", download)
    with pytest.raises(layout.LayoutModelUnavailable, match=module) as exc:
        layout.LayoutEngine(tmp_path, device="cpu").analyze(Image.new("RGB", (20, 10)))
    assert "uv sync" in str(exc.value) and "private" not in str(exc.value)
    download.assert_not_called()


def test_import_without_layout_runtime_dependencies():
    script = """
import importlib.abc
import sys
class BlockLayoutImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'onnxruntime', 'huggingface_hub', 'yaml'}:
            raise ImportError('runtime dependencies deliberately unavailable')
sys.meta_path.insert(0, BlockLayoutImports())
import doclayout.layout
import doclayout.models
assert doclayout.layout._engine is None
from PIL import Image
try:
    doclayout.layout.get_layout_engine().analyze(Image.new('RGB', (10, 10)))
except doclayout.layout.LayoutModelUnavailable:
    pass
else:
    raise AssertionError('missing dependency was not reported')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    import huggingface_hub

    contents = {
        "inference.onnx": b"offline fixture",
        "inference.yml": (
            "label_list:\n" + "".join(f"- {s}\n" for s in layout.LABELS)
        ).encode(),
    }
    monkeypatch.setattr(
        layout,
        "HASHES",
        {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    )
    directory = tmp_path / "override"
    directory.mkdir()
    for name, data in contents.items():
        (directory / name).write_bytes(data)
    download = Mock(side_effect=AssertionError("unexpected network"))
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    return directory, contents, download


def test_override_precedence_offline_and_warm_reuse(tmp_path, monkeypatch, artifacts):
    directory, _, download = artifacts
    monkeypatch.setattr(layout.settings, "DOCLAYOUT_LAYOUT_MODEL_DIR", str(directory))
    engine = layout.LayoutEngine(tmp_path / "unused_cache", device="cpu", offline=True)
    session = FakeSession(tmp_path, "CPUExecutionProvider")
    monkeypatch.setattr(engine, "_new_session", Mock(return_value=session))
    resolver = Mock(wraps=layout.model_files)
    monkeypatch.setattr(layout, "model_files", resolver)
    for _ in range(2):
        assert engine.analyze(Image.new("RGB", (200, 100))).actual_device == "cpu"
    assert resolver.call_count == 1
    assert resolver.call_args.kwargs["model_dir"] == str(directory)
    assert engine._paths["inference.onnx"] == directory / "inference.onnx"
    download.assert_not_called()


def test_override_downloads_only_missing_file_and_rejects_corruption(
    tmp_path, artifacts
):
    directory, contents, download = artifacts
    (directory / "inference.onnx").unlink()
    with pytest.raises(layout.LayoutModelUnavailable, match="offline"):
        layout.model_files(tmp_path, True, model_dir=directory)
    download.assert_not_called()

    def fetch(**kwargs):
        assert kwargs["local_dir"] == directory and "cache_dir" not in kwargs
        assert (
            kwargs["repo_id"] == layout.REPO and kwargs["revision"] == layout.REVISION
        )
        path = directory / kwargs["filename"]
        path.write_bytes(contents[kwargs["filename"]])
        return str(path)

    download.side_effect = fetch
    layout.model_files(tmp_path, False, model_dir=directory)
    layout.model_files(tmp_path, False, model_dir=directory)
    assert download.call_count == 1
    (directory / "inference.yml").write_bytes(b"corrupt")
    with pytest.raises(layout.LayoutModelUnavailable, match="checksum"):
        layout.model_files(tmp_path, False, model_dir=directory)
    assert (
        download.call_count == 1
        and (directory / "inference.yml").read_bytes() == b"corrupt"
    )


def test_download_failure_and_invalid_yaml_are_typed(tmp_path, artifacts, monkeypatch):
    directory, _, download = artifacts
    (directory / "inference.onnx").unlink()
    download.side_effect = OSError("private URL credentials")
    with pytest.raises(
        layout.LayoutModelUnavailable, match="artifact preparation"
    ) as exc:
        layout.model_files(tmp_path, False, model_dir=directory)
    assert "private" not in str(exc.value)
    (directory / "inference.onnx").write_bytes(b"offline fixture")
    data = b"[]"
    (directory / "inference.yml").write_bytes(data)
    monkeypatch.setitem(
        layout.HASHES, "inference.yml", hashlib.sha256(data).hexdigest()
    )
    with pytest.raises(layout.LayoutModelUnavailable, match="label contract"):
        layout.model_files(tmp_path, False, model_dir=directory)


@pytest.mark.parametrize("output", [None, [], [None, None, None], tensors()[:2]])
def test_unsupported_output_containers_raise_typed_error(output):
    with pytest.raises(layout.LayoutModelUnavailable, match="tensor contract"):
        layout.decode_outputs(output, (200, 100), 0, "CPUExecutionProvider")


def test_all_class_ids_and_order_are_read_from_outputs():
    rows = [[i, 0.9, 20, 10, 180, 90, 100 - i] for i in range(25)]
    result = layout.decode_outputs(tensors(rows), (200, 100), 0, "CPUExecutionProvider")
    assert [(r.class_id, r.label) for r in result.regions] == list(
        enumerate(layout.LABELS)
    )
    assert [r.order_key for r in result.regions] == list(range(100, 75, -1))
    assert [r.observed_rank for r in result.regions] == list(range(24, -1, -1))
    assert all(r.bbox_px == [20, 10, 180, 90] for r in result.regions)
    assert all(r.geometry_kind == "rectangle_with_mask" for r in result.regions)


def test_settings_accept_explicit_cuda_without_changing_default(monkeypatch):
    monkeypatch.delenv("DOCLAYOUT_LAYOUT_DEVICE", raising=False)
    assert Settings(_env_file=None).DOCLAYOUT_LAYOUT_DEVICE == "auto"
    monkeypatch.setenv("DOCLAYOUT_LAYOUT_DEVICE", "cuda")
    assert Settings(_env_file=None).DOCLAYOUT_LAYOUT_DEVICE == "cuda"


def test_fake_analyzer_is_injectable_without_production_switch(
    doc_provider, extraction_service
):
    from doclayout.builders.document import DocumentBuilder

    class FakeAnalyzer:
        infer = layout.LayoutEngine.infer

        def analyze(self, image):
            return LayoutAnalysis(
                image_size=image.size,
                model_id="test",
                model_revision="fixture",
                actual_device="cpu",
                provider="offline fake",
                elapsed_ms=0,
                candidate_count=0,
                filtered_count=0,
                regions=[],
            )

    result = DocumentBuilder()(doc_provider, extraction_service, FakeAnalyzer())
    assert result.layout.pages and all(
        p.provider == "offline fake" for p in result.layout.pages
    )
    assert extraction_service.call_count == len(result.pages)


def test_cold_hub_download_once_across_file_jobs(tmp_path, artifacts, monkeypatch):
    from huggingface_hub.errors import LocalEntryNotFoundError

    directory, _, download = artifacts
    cached = set()
    online = []

    def fetch(**kwargs):
        name = kwargs["filename"]
        assert kwargs["cache_dir"] == tmp_path
        assert (
            kwargs["revision"] == layout.REVISION and kwargs["repo_id"] == layout.REPO
        )
        if kwargs.get("local_files_only"):
            if name not in cached:
                raise LocalEntryNotFoundError("offline fixture cache miss")
        else:
            cached.add(name)
            online.append(name)
        return str(directory / name)

    download.side_effect = fetch
    monkeypatch.setattr(layout.settings, "DOCLAYOUT_LAYOUT_MODEL_DIR", None)
    engine = layout.LayoutEngine(tmp_path, device="cpu", offline=False)
    factory = Mock(return_value=FakeSession(tmp_path, "CPUExecutionProvider"))
    monkeypatch.setattr(engine, "_new_session", factory)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(lambda _: engine.analyze(Image.new("RGB", (200, 100))), range(9))
        )
    assert len(results) == 9 and factory.call_count == 1
    assert online == ["inference.onnx", "inference.yml"]
    assert download.call_count == 4  # One local miss and one download per artifact.


@pytest.mark.parametrize("which", ["inputs", "outputs"])
def test_session_contract_failure_cleans_profile_and_is_typed(
    tmp_path, monkeypatch, isolated, which
):
    engine = layout.LayoutEngine(tmp_path, device="cuda")
    session = FakeSession(tmp_path, "CUDAExecutionProvider")
    monkeypatch.setattr(
        session, "get_" + which, lambda: [SimpleNamespace(name="unexpected")]
    )
    monkeypatch.setattr(engine, "_new_session", lambda provider: session)
    with pytest.raises(
        layout.LayoutModelUnavailable, match="contract changed|names changed"
    ):
        engine.analyze(Image.new("RGB", (200, 100)))
    assert not session.calls and session.profiles == 1 and not session.path.exists()


@pytest.mark.parametrize("value", ["", "file"])
def test_invalid_model_directory_is_typed(tmp_path, artifacts, value):
    _, _, download = artifacts
    target = ""
    if value == "file":
        target = tmp_path / "not_a_directory"
        target.write_text("fixture", encoding="utf-8")
    with pytest.raises(layout.LayoutModelUnavailable, match="directory"):
        layout.model_files(tmp_path, False, model_dir=target)
    download.assert_not_called()


@pytest.mark.parametrize("provider", ["CUDAExecutionProvider", "CPUExecutionProvider"])
def test_native_session_scatter_placement_options(tmp_path, monkeypatch, provider):
    options = SimpleNamespace(add_session_config_entry=Mock())
    session = SimpleNamespace(disable_fallback=Mock())
    ort = SimpleNamespace(
        SessionOptions=Mock(return_value=options),
        InferenceSession=Mock(return_value=session),
    )
    monkeypatch.setattr(layout, "_dependency", lambda name: ort)
    engine = layout.LayoutEngine(tmp_path, device="auto")
    engine._paths = {"inference.onnx": tmp_path / "model.onnx"}
    assert engine._new_session(provider) is session
    if provider == "CUDAExecutionProvider":
        assert options.add_session_config_entry.call_args_list == [
            (("session.name_based_layer_assignment", "cpu(ScatterND)"),),
            (("session.record_ep_graph_assignment_info", "1"),),
        ]
        assert options.enable_profiling
    else:
        options.add_session_config_entry.assert_not_called()
    session.disable_fallback.assert_called_once()


@pytest.mark.parametrize("device", ["auto", "cuda"])
@pytest.mark.parametrize(
    "placement", [[], ["CUDAExecutionProvider"], ["CPUExecutionProvider"] * 2]
)
def test_unverified_scatter_placement_rejects_cuda(
    tmp_path, monkeypatch, isolated, device, placement
):
    engine = layout.LayoutEngine(tmp_path, device=device)
    cuda = FakeSession(tmp_path, "CUDAExecutionProvider")
    cpu = FakeSession(tmp_path, "CPUExecutionProvider")
    cuda.get_provider_graph_assignment_info = lambda: [
        SimpleNamespace(
            ep_name=ep, get_nodes=lambda: [SimpleNamespace(op_type="ScatterND")]
        )
        for ep in placement
    ]
    monkeypatch.setattr(
        engine,
        "_new_session",
        lambda provider: cuda if provider == "CUDAExecutionProvider" else cpu,
    )
    with Image.new("RGB", (200, 100)) as image:
        if device == "cuda":
            with pytest.raises(layout.LayoutModelUnavailable, match="placement"):
                engine.analyze(image)
            assert not cpu.calls
        else:
            result = engine.analyze(image)
            assert result.actual_device == "cpu" and cpu.calls == 1
    assert cuda.calls == 0 and cuda.profiles == 1 and not cuda.path.exists()


def test_scatter_policy_changes_saved_conversion_identity(monkeypatch):
    current = layout.pipeline_manifest()
    assert current["execution_policy"] == "onnx-cuda-scatternd-cpu/v1"
    monkeypatch.setattr(layout, "EXECUTION_POLICY", "old-placement")
    assert current["fingerprint"] != layout.pipeline_manifest()["fingerprint"]
