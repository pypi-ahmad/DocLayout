"""Offline frontend regression checks using the real converter and renderers."""

import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from PIL import Image

from doclayout.ui.chat import answer_document_question
from doclayout.ui.documents import page_range, prepare_upload, preview, run_document
from doclayout.ui.exports import annotations, markdown_html, output_zip


def test_single_extraction_all_exports(temp_doc, model_dict, extraction_service):
    upload = prepare_upload(Path(temp_doc.name).read_bytes(), "source.pdf")
    assert upload.count == 2
    assert preview(upload, 1).width > 0
    result = run_document(upload, {"page_range": page_range(2, 2, 2)}, model_dict)
    assert extraction_service.call_count == 1
    assert set(result["pages"]) == {2}
    assert "Hello, World!" in result["markdown"]
    assert json.loads(result["json"])["children"]
    assert json.loads(result["chunks"])["blocks"]
    original = result["document"].pages[0].highres_image.tobytes()
    result["html"] = markdown_html(result["markdown"], result["images"])
    result["annotations"] = annotations(result["document"])
    assert result["annotations"]["drawn"] > 0
    assert result["annotations"]["pdf"].startswith(b"%PDF")
    assert result["document"].pages[0].highres_image.tobytes() == original
    with ZipFile(io.BytesIO(output_zip(result))) as archive:
        assert archive.read("document.md").decode() == result["markdown"]
        assert archive.read("document.html").decode() == result["html"]
        assert "annotations/page-2.png" in archive.namelist()
        assert set(result["images"]) <= set(archive.namelist())
        assert "source.pdf" not in archive.namelist()
        assert "chat.json" not in archive.namelist()
    assert extraction_service.call_count == 1


@pytest.mark.parametrize("start,end,count", [(0, 1, 2), (2, 1, 2), (1, 3, 2)])
def test_invalid_ranges(start, end, count):
    with pytest.raises(ValueError):
        page_range(start, end, count)


def test_image_upload(temp_image):
    upload = prepare_upload(Path(temp_image.name).read_bytes(), "image.png")
    assert upload.count == 1
    assert preview(upload, 0).size == (512, 512)


def test_office_preparation_reuses_pdf(temp_doc, tmp_path, monkeypatch, model_dict):
    prepared_pdf = tmp_path / "prepared.pdf"
    prepared_pdf.write_bytes(Path(temp_doc.name).read_bytes())
    provider = Mock(return_value=SimpleNamespace(temp_pdf_path=prepared_pdf))

    class PreparedProvider:
        temp_pdf_path = prepared_pdf

        def close(self):
            pass

        def __len__(self):
            return 2

    provider.return_value = PreparedProvider()
    monkeypatch.setattr(
        "doclayout.ui.documents.provider_from_filepath", lambda _: provider
    )
    upload = prepare_upload(b"office source", "source.docx")
    assert upload.suffix == ".pdf" and upload.count == 2
    assert upload.data == prepared_pdf.read_bytes()
    assert provider.call_count == 1
    # Conversion now uses PdfConverter's registry with the prepared PDF.
    result = run_document(upload, {"page_range": "0-0"}, model_dict)
    assert result["markdown"]
    assert provider.call_count == 1


def test_annotation_scaling_and_invalid_boxes():
    from doclayout.schema import BlockTypes
    from doclayout.schema.polygon import PolygonBox

    source = Image.new("RGB", (200, 200), "white")
    blocks = [
        SimpleNamespace(
            removed=False,
            ignore_for_output=False,
            structure=[],
            block_type=BlockTypes.Text,
            polygon=PolygonBox.from_bbox(box),
        )
        for box in ([10.0, 10.0, 30.0, 30.0], [-10.0, 10.0, 20.0, 20.0])
    ]
    page = SimpleNamespace(
        page_id=4,
        layout=None,
        structure=[0, 1],
        get_block=lambda key: blocks[key],
        children=blocks,
        polygon=PolygonBox.from_bbox([0, 0, 100, 100]),
        get_image=lambda **_: source,
    )
    result = annotations(SimpleNamespace(pages=[page]))
    assert result["drawn"] == 1 and result["skipped"] == 1
    assert result["pages"][5].getpixel((20, 20)) == (220, 30, 30)
    assert source.getpixel((20, 20)) == (255, 255, 255)


def test_gui_layout_failure_has_warning_and_sol_result(
    temp_doc, model_dict, monkeypatch
):
    from streamlit.testing.v1 import AppTest

    from doclayout.services.layout import LayoutInferenceError

    monkeypatch.setattr("doclayout.scripts.common.load_models", lambda: model_dict)
    monkeypatch.setattr("doclayout.scripts.common.parse_args", dict)
    model_dict["layout_service"].predict.side_effect = LayoutInferenceError(
        "private payload"
    )
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=20
    ).run()
    app.file_uploader[0].set_value(
        ("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")
    ).run()
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception
    assert not app.error
    assert any("V3 unavailable" in warning.value for warning in app.warning)
    assert all("private" not in warning.value for warning in app.warning)
    assert "result" in app.session_state
    assert model_dict["extraction_service"].called


@pytest.mark.parametrize("invalid_policy", [False, True])
def test_gui_preparation_failure_falls_back_but_invalid_policy_stops(
    temp_doc, model_dict, monkeypatch, invalid_policy
):
    from streamlit.testing.v1 import AppTest

    from doclayout.services.layout import LayoutArtifactError
    from doclayout.settings import settings

    monkeypatch.setattr("doclayout.scripts.common.load_models", lambda: model_dict)
    monkeypatch.setattr("doclayout.scripts.common.parse_args", dict)
    model_dict["layout_service"].prepare.side_effect = LayoutArtifactError(
        "private payload"
    )
    model_dict["layout_service"].predict.side_effect = LayoutArtifactError(
        "private payload"
    )
    if invalid_policy:
        monkeypatch.setattr(settings, "DOCLAYOUT_ALIGNMENT_POLICY", "{}")
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=20
    ).run()
    app.file_uploader[0].set_value(
        ("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")
    ).run()
    model_dict["layout_service"].prepare.assert_not_called()
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception
    if invalid_policy:
        assert "Layout conversion failed" in app.error[0].value
        assert "result" not in app.session_state
        model_dict["layout_service"].predict.assert_not_called()
        model_dict["extraction_service"].assert_not_called()
    else:
        assert not app.error
        assert "result" in app.session_state
        assert model_dict["extraction_service"].called
        assert any("V3 unavailable" in warning.value for warning in app.warning)
        assert all("private" not in warning.value for warning in app.warning)
    assert model_dict["layout_service"].prepare.call_count == (
        0 if invalid_policy else 1
    )
    if not invalid_policy:
        assert app.status[0].state == "error"


def test_gui_reports_actual_cpu_after_cuda_page_failure(
    temp_doc, model_dict, monkeypatch
):
    from streamlit.testing.v1 import AppTest

    from doclayout.services.layout import LayoutPreparation

    monkeypatch.setattr("doclayout.scripts.common.load_models", lambda: model_dict)
    monkeypatch.setattr("doclayout.scripts.common.parse_args", dict)
    layout = model_dict["layout_service"]
    layout.prepare.return_value = LayoutPreparation(
        "cuda:0", "CUDAExecutionProvider", 0.1
    )
    predict = layout.predict.side_effect
    reason = "CUDA page inference failed (RuntimeError); using CPU."
    layout.predict.side_effect = lambda image: replace(
        predict(image), fallback_reason=reason
    )
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=20
    ).run()
    app.file_uploader[0].set_value(
        ("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")
    ).run()
    layout.prepare.assert_not_called()
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception and not app.error
    assert "CUDAExecutionProvider" in app.status[0].label
    assert app.status[0].state == "complete"
    assert any("Layout: cpu" in item.value for item in app.caption)
    assert any(item.value == reason for item in app.warning)
    layout.prepare.assert_called_once()
    app.number_input(key="preview_page").set_value(2).run()
    layout.prepare.assert_called_once()
    assert any("Layout: cpu" in item.value for item in app.caption)


def test_gui_without_policy_extracts_with_sol_geometry(
    temp_doc, model_dict, monkeypatch
):
    from streamlit.testing.v1 import AppTest

    from doclayout.settings import settings

    monkeypatch.setattr(settings, "DOCLAYOUT_ALIGNMENT_POLICY", None)
    monkeypatch.setattr("doclayout.scripts.common.load_models", lambda: model_dict)
    monkeypatch.setattr("doclayout.scripts.common.parse_args", dict)
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=20
    ).run()
    app.file_uploader[0].set_value(
        ("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")
    ).run()
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception and not app.error
    assert any("No matching policy configured" in item.value for item in app.info)
    assert all(
        page["alignment_mode"] == "sol_geometry"
        for page in app.session_state["result"]["metadata"]["layout"]
    )
    assert model_dict["layout_service"].predict.call_count == 2


def test_zip_rejects_unsafe_crop_paths():
    result = {
        "markdown": "",
        "html": "",
        "json": "{}",
        "chunks": "{}",
        "metadata": {},
        "annotations": {"pdf": b"", "pages": {}},
        "images": {"../crop.png": Image.new("RGB", (1, 1))},
    }
    with pytest.raises(ValueError, match="Unsafe"):
        output_zip(result)


def test_html_fidelity_and_safety():
    raw = '# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n$x^2$\n\n```python\nprint("hello")\n```\n\n![crop](crop.jpeg)\n\n<script>alert(1)</script><img src="https://example.com/tracker" onerror="alert(2)"><a href="javascript:alert(3)">bad</a>'
    html = markdown_html(raw, {"crop.jpeg": Image.new("RGB", (10, 10))})
    assert "<table>" in html and "<math" in html and "<code" in html
    assert "data:image/png;base64," in html
    assert "script>" not in html and "onerror" not in html and "javascript:" not in html
    assert "example.com" not in html
    assert "Georgia" in html


def response(value):
    return SimpleNamespace(
        output_text=json.dumps(value),
        model="gpt-6-luna",
        model_dump=lambda: {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text"}]}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    )


def draft(quote="Revenue was 42.", page=3):
    return {
        "decision": "answer",
        "statements": [
            {"text": "Revenue was 42.", "evidence": [{"page": page, "quote": quote}]}
        ],
    }


@pytest.mark.parametrize("approved,status", [(True, "answered"), (False, "blocked")])
def test_chat_verified(approved, status):
    client = Mock()
    client.responses.create.side_effect = [
        response(draft()),
        response({"approved": approved}),
    ]
    result = answer_document_question({3: "Revenue was 42."}, "Revenue?", client=client)
    assert result.status == status
    assert client.responses.create.call_count == 2
    if approved:
        assert result.answer == "Revenue was 42. (p. 3)"
    for call in client.responses.create.call_args_list:
        assert call.kwargs["model"] == "gpt-6-luna"
        assert call.kwargs["store"] is False
        assert call.kwargs["max_output_tokens"] == 8192
        assert "tools" not in call.kwargs


@pytest.mark.parametrize(
    "value",
    [draft("invented"), draft(page=9), {"decision": "answer", "statements": []}],
)
def test_chat_rejects_unverified_evidence(value):
    client = Mock()
    client.responses.create.return_value = response(value)
    result = answer_document_question({3: "Revenue was 42."}, "Revenue?", client=client)
    assert result.status == "blocked"
    assert client.responses.create.call_count == 1


@pytest.mark.parametrize("decision", ["not_found", "out_of_scope"])
def test_chat_no_answer(decision):
    client = Mock()
    client.responses.create.return_value = response(
        {"decision": decision, "statements": []}
    )
    assert (
        answer_document_question({1: "Text"}, "Question", client=client).status
        == decision
    )
    assert client.responses.create.call_count == 1


def test_chat_limits_history_and_errors():
    client = Mock()
    assert (
        answer_document_question({1: "x" * 200_000}, "q", client=client).status
        == "context_limit"
    )
    assert answer_document_question({}, "q", client=client).status == "no_document"
    assert (
        answer_document_question({1: "x"}, "", client=client).status
        == "invalid_question"
    )
    client.responses.create.assert_not_called()
    history = [
        {"question": str(i), "answer": "a", "status": "answered"} for i in range(9)
    ]
    history.append({"question": "rejected", "answer": "a", "status": "blocked"})
    client.responses.create.side_effect = RuntimeError("secret provider body")
    result = answer_document_question({1: "x"}, "q", history, client=client)
    assert result.status == "error" and "secret" not in result.answer
    data = json.loads(client.responses.create.call_args.kwargs["input"][1]["content"])
    assert len(data["history"]) == 6 and data["history"][0]["question"] == "3"


def test_session_reruns_and_invalidation(
    temp_doc, model_dict, extraction_service, monkeypatch
):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr("doclayout.scripts.common.load_models", lambda: model_dict)
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=20
    ).run()
    assert not app.exception
    app.file_uploader[0].set_value(
        ("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")
    ).run()
    assert not app.exception
    assert app.number_input(key="start").value == 1
    assert app.number_input(key="end").value == 2
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert not app.exception and not app.error
    assert extraction_service.call_count == 2
    app.number_input(key="preview_page").set_value(2).run()
    next(c for c in app.checkbox if c.label == "Debug").check().run()
    assert not app.exception
    assert extraction_service.call_count == 2
    assert app.session_state["result"]["markdown"]
    app.number_input(key="start").set_value(2).run()
    assert "result" not in app.session_state
    assert extraction_service.call_count == 2
    next(b for b in app.button if b.label == "Run DocLayout").click().run()
    assert extraction_service.call_count == 3
    next(c for c in app.checkbox if c.label == "Extra refinement").check().run()
    assert "result" not in app.session_state
