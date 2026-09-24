import pytest
from fastapi.testclient import TestClient

from doclayout.scripts import server


@pytest.fixture
def api(model_dict, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "create_model_dict", lambda: model_dict)
    monkeypatch.setenv("DOCLAYOUT_API_TOKEN", "test-token-" * 4)
    monkeypatch.setenv("DOCLAYOUT_INPUT_ROOT", str(tmp_path))
    with TestClient(server.app) as client:
        client.headers["Authorization"] = "Bearer " + "test-token-" * 4
        yield client


def test_api_path(api, temp_doc):
    response = api.post("/doclayout", json={"filepath": temp_doc.name})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["metadata"]["extraction"]["model"] == "gpt-6-sol"


def test_api_rejects_removed_config(api, temp_doc):
    response = api.post(
        "/doclayout", json={"filepath": temp_doc.name, "force_ocr": True}
    )
    assert response.status_code == 422


def test_api_upload(api, temp_doc):
    with open(temp_doc.name, "rb") as stream:
        response = api.post(
            "/doclayout/upload",
            files={"file": ("input.pdf", stream, "application/pdf")},
            data={"output_format": "json"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True


def test_api_upload_rejects_removed_config(api, temp_doc):
    with open(temp_doc.name, "rb") as stream:
        response = api.post(
            "/doclayout/upload",
            files={"file": ("input.pdf", stream, "application/pdf")},
            data={"force_ocr": "true"},
        )
    assert response.status_code == 422


def test_gui_starts_with_new_options(model_dict, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        "doclayout.scripts.common.create_model_dict", lambda: model_dict
    )
    monkeypatch.setattr("doclayout.scripts.common.parse_args", lambda: {})
    app = AppTest.from_file("doclayout/scripts/streamlit_app.py").run(timeout=30)
    assert not app.exception
