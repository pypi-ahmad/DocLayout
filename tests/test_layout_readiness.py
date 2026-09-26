"""Readiness gates across real entry points, using only offline engines."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from doclayout import layout
from doclayout.converters.ocr import OCRConverter
from doclayout.converters.pdf import PdfConverter
from doclayout.converters.table import TableConverter
from doclayout.field_store import FieldStore
from doclayout.fields import load_definition
from doclayout.scripts import convert, convert_single, server
from doclayout.ui import batch


@pytest.fixture
def failed_models(model_dict):
    engine = SimpleNamespace(
        prepare=Mock(
            side_effect=layout.LayoutModelUnavailable(
                "Layout CPU unavailable. Check installation."
            )
        ),
        analyze=Mock(side_effect=AssertionError("Page inference before preparation")),
        retry_failed=Mock(),
        actual_device=None,
        status="Not loaded",
    )
    return {**model_dict, "layout_engine": engine}


@pytest.mark.parametrize("converter", [PdfConverter, OCRConverter, TableConverter])
def test_library_preparation_failure_uses_sol(
    converter, failed_models, temp_doc, extraction_service, monkeypatch
):
    document = converter(failed_models).build_document(temp_doc.name)
    assert extraction_service.call_count == len(document.pages)
    assert all(
        p.status == "sol_fallback" for p in document.layout.page_runtime.values()
    )
    assert all(p.actual_device is None for p in document.layout.page_runtime.values())
    assert all(
        block.layout.status in {"sol_only", "processor"}
        for page in document.pages
        for block in page.children
        if block.layout
    )
    failed_models["layout_engine"].analyze.assert_not_called()


@pytest.mark.parametrize("mode", ["file", "folder", "single"])
def test_cli_preparation_failure_preserves_outputs(
    mode, failed_models, temp_doc, tmp_path, monkeypatch, extraction_service
):
    monkeypatch.setattr(convert, "create_model_dict", lambda: failed_models)
    monkeypatch.setattr(convert_single, "create_model_dict", lambda: failed_models)
    destination = tmp_path / "output"
    destination.mkdir()
    previous = destination / "previous.md"
    previous.write_text("Historical output", encoding="utf-8")
    if mode == "file":
        command, args = convert.convert_cli, [temp_doc.name, str(destination)]
    elif mode == "folder":
        command, args = (
            convert.convert_cli,
            [str(tmp_path), "--output_dir", str(destination)],
        )
    else:
        command, args = (
            convert_single.convert_single_cli,
            [temp_doc.name, "--output_dir", str(destination)],
        )
    result = CliRunner().invoke(command, args)
    assert result.exit_code == 0, result.output
    assert previous.read_text("utf-8") == "Historical output"
    assert len(list(destination.rglob("*.md"))) > 1
    assert extraction_service.called
    failed_models["layout_engine"].analyze.assert_not_called()


@pytest.mark.parametrize("route", ["path", "upload"])
def test_http_preparation_failure_returns_sol_output(
    route, failed_models, temp_doc, tmp_path, monkeypatch, extraction_service
):
    token = "test-token-" * 4
    monkeypatch.setenv("DOCLAYOUT_API_TOKEN", token)
    monkeypatch.setenv("DOCLAYOUT_INPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(server, "create_model_dict", lambda: failed_models)
    with TestClient(server.app) as client:
        failed_models["layout_engine"].prepare.assert_not_called()  # Lazy API startup.
        client.headers["Authorization"] = "Bearer " + token
        if route == "path":
            response = client.post("/doclayout", json={"filepath": temp_doc.name})
        else:
            response = client.post(
                "/doclayout/upload",
                files={
                    "file": (
                        "input.pdf",
                        Path(temp_doc.name).read_bytes(),
                        "application/pdf",
                    )
                },
            )
        assert response.status_code == 200, response.text
        assert "sol_fallback" in response.text
        assert not server.app_data["busy"]
    assert extraction_service.called


def test_cached_batch_never_resolves_engine(tmp_path, monkeypatch):
    files = [("saved.pdf", b"saved")]
    store = FieldStore(tmp_path)
    document_id = batch.conversion_id(*files[0], {})
    store.save_document(document_id, "saved.pdf", {})
    forbidden = Mock(side_effect=AssertionError("Cached batch loaded model"))
    monkeypatch.setattr(batch, "get_layout_engine", forbidden)
    worker = Mock(return_value={"status": "needs_review", "reused": True})
    monkeypatch.setattr(batch, "process_file", worker)
    results = list(batch.process_batch(files, {}, {}, load_definition(), root=tmp_path))
    assert len(results) == 1 and results[0]["reused"]
    forbidden.assert_not_called()
    worker.assert_called_once()


def test_failed_batch_preparation_uses_fallback_for_uncached_jobs(
    tmp_path, monkeypatch
):
    files = [("new.pdf", b"new"), ("saved.pdf", b"saved")]
    store = FieldStore(tmp_path)
    saved_id = batch.conversion_id(*files[1], {})
    store.save_document(saved_id, "saved.pdf", {})
    engine = SimpleNamespace(
        prepare=Mock(side_effect=RuntimeError("PRIVATE native message")),
        retry_failed=Mock(),
        actual_device=None,
        status="Not loaded",
    )
    worker = Mock(return_value={"filename": "saved.pdf", "status": "needs_review"})
    monkeypatch.setattr(batch, "process_file", worker)
    statuses = []
    results = list(
        batch.process_batch(
            files,
            {},
            {"layout_engine": engine},
            load_definition(),
            root=tmp_path,
            on_status=statuses.append,
        )
    )
    assert statuses[0] == "Preparing layout model…"
    assert statuses[-1].startswith("Sol fallback") and "PRIVATE" not in str(results)
    assert len(results) == worker.call_count == 2
    assert all(
        isinstance(c.args[3]["layout_engine"], layout.SolFallbackEngine)
        for c in worker.call_args_list
    )
    engine.prepare.assert_called_once()
    assert not store.document_dir(batch.conversion_id(*files[0], {})).exists()


def test_batch_prepares_before_dispatch_on_caller_status_thread(tmp_path, monkeypatch):
    import threading

    caller = threading.get_ident()
    events = []
    engine = SimpleNamespace(
        actual_device=None, status="Not loaded", retry_failed=Mock()
    )

    def prepare():
        assert threading.get_ident() != caller
        events.append("prepared")
        engine.actual_device = "cuda"

    engine.prepare = prepare

    def worker(*args, **kwargs):
        assert events == ["prepared"]
        return {"status": "success"}

    monkeypatch.setattr(batch, "process_file", worker)
    statuses = []

    def status(value):
        assert threading.get_ident() == caller
        statuses.append(value)

    results = list(
        batch.process_batch(
            [("a.pdf", b"a"), ("b.pdf", b"b")],
            {},
            {"layout_engine": engine},
            load_definition(),
            root=tmp_path,
            on_status=status,
        )
    )
    assert len(results) == 2
    assert (
        statuses[0] == "Preparing layout model…"
        and statuses[-1] == "PP-DocLayoutV3 · CUDA"
    )


def test_saved_layout_summary_uses_metadata_only():
    assert batch.layout_summary({}) is None
    pages = {
        "0": {"retained_region_count": 3, "matched_count": 2, "elapsed_ms": 12.5},
        "1": {"retained_region_count": 4, "matched_count": 3, "elapsed_ms": 17.5},
    }
    assert (
        batch.layout_summary({"layout": {"page_runtime": pages}})
        == "V3: 7 regions · 5 initial matches · 30 ms summed page analysis (includes queue wait)"
    )
    pages["1"]["status"] = "sol_fallback"
    assert batch.layout_summary({"layout": {"page_runtime": pages}}).endswith(
        "Sol fallback: 1 page(s)"
    )


def test_fallback_policy_separates_historical_conversion_identity(monkeypatch):
    current = layout.pipeline_manifest()
    monkeypatch.setattr(layout, "FALLBACK_POLICY", "layout-required")
    assert current["fingerprint"] != layout.pipeline_manifest()["fingerprint"]


def test_preparation_failure_is_conversion_local_and_not_reprobed():
    engine = SimpleNamespace(prepare=Mock(side_effect=RuntimeError("PRIVATE")))
    fallback = layout.prepare_for_conversion(engine)
    from PIL import Image

    with Image.new("RGB", (123, 456)) as image:
        for _ in range(3):
            assert layout.prepare_for_conversion(fallback) is fallback
            result = fallback.analyze(image)
            assert result.status == "sol_fallback"
            assert result.image_size == (123, 456) and not result.regions
            assert result.actual_device is result.order_key_source is None
            assert "PRIVATE" not in result.model_dump_json()
    engine.prepare.assert_called_once()


def test_gui_preparation_failure_and_retry(
    temp_doc, model_dict, extraction_service, monkeypatch, tmp_path
):
    from streamlit.testing.v1 import AppTest

    engine = layout.get_layout_engine()
    original = engine.prepare

    def fail():
        engine.status = "Failed: Layout files missing offline. Populate the cache."
        raise layout.LayoutModelUnavailable(
            "Layout files missing offline. Populate the cache."
        )

    prepare = Mock(side_effect=fail)
    monkeypatch.setattr(engine, "prepare", prepare)
    monkeypatch.setattr(
        "doclayout.scripts.common.load_models",
        lambda: {**model_dict, "layout_engine": engine},
    )
    monkeypatch.setattr(
        "doclayout.settings.settings.OUTPUT_DIR", str(tmp_path / "store")
    )
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=20
    ).run()
    prepare.assert_not_called()
    app.file_uploader[0].set_value(
        [("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")]
    ).run()
    prepare.assert_not_called()
    assert all("layout" not in c.label.lower() for c in app.checkbox)
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception and not app.error
    assert any("Sol fallback" in w.value for w in app.warning)
    assert extraction_service.call_count == 2
    assert prepare.call_count == 1
    next(c for c in app.checkbox if c.label == "Debug").check().run()
    assert prepare.call_count == 1  # Passive reruns do not retry.
    prepare.side_effect = original
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception and not app.error
    assert prepare.call_count == 1  # Saved fallback is not silently reconverted.
    assert extraction_service.call_count == 2
    count = prepare.call_count
    app.number_input(key="preview_page").set_value(2).run()
    assert prepare.call_count == count
