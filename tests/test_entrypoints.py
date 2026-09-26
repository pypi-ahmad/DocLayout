import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doclayout.scripts import server


def test_launcher_retains_frozen_layout_and_loopback_contract():
    script = (Path(__file__).resolve().parents[1] / "launch.cmd").read_text()
    assert "uv run --frozen --extra gui --extra layout python -m streamlit" in script
    assert "--server.port 8471 --server.address 127.0.0.1" in script
    assert "Where-Object LocalPort -eq 8471" in script
    assert "Stop-Process -Id $ownerId -Force" in script
    assert "Select-Object -ExpandProperty OwningProcess -Unique" in script


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows launcher")
@pytest.mark.parametrize("stop_fails", [False, True])
def test_launcher_port_cleanup(stop_fails):
    root = Path(__file__).resolve().parents[1]
    script = (root / "launch.cmd").read_text()
    line = next(
        line for line in script.splitlines() if line.startswith("powershell.exe")
    )
    command = line.split(' -Command "', 1)[1].removesuffix('"')
    # Execute the launcher's real cleanup on a child-owned ephemeral port only.
    listener = subprocess.Popen(
        [
            str(Path(sys.base_prefix) / "python.exe"),
            "-u",
            "-c",
            "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
        cwd=root,
    )
    try:
        assert listener.stdout is not None
        port = int(listener.stdout.readline())
        command = command.replace("8471", str(port))
        if stop_fails:
            command = command.replace(
                "Stop-Process -Id $ownerId -Force", "throw 'test stop failure'"
            )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if stop_fails:
            assert result.returncode == 1
            assert "ERROR: test stop failure" in result.stdout
            assert listener.poll() is None
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            assert f"Stopping process {listener.pid}" in result.stdout
            listener.wait(timeout=5)
    finally:
        if listener.poll() is None:
            listener.terminate()
        listener.wait(timeout=5)
        if listener.stdout is not None:
            listener.stdout.close()


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


@pytest.mark.parametrize("upload", [False, True])
def test_api_layout_failure_uses_sol_safely(api, temp_doc, model_dict, upload):
    from doclayout.services.layout import LayoutInferenceError

    model_dict["layout_service"].predict.side_effect = LayoutInferenceError(
        "private path and payload"
    )
    if upload:
        with open(temp_doc.name, "rb") as stream:
            response = api.post(
                "/doclayout/upload",
                files={"file": ("input.pdf", stream, "application/pdf")},
            )
    else:
        response = api.post("/doclayout", json={"filepath": temp_doc.name})
    assert response.status_code == 200
    assert "LayoutInferenceError" in response.text
    assert "sol_fallback" in response.text
    assert "private" not in response.text
    assert model_dict["extraction_service"].called


@pytest.mark.parametrize(
    "key",
    [
        "alignment_policy",
        "layout_device",
        "layout_cache_dir",
        "layout_service",
        "layout_off",
        "use_layout",
    ],
)
def test_api_cannot_override_operator_layout(api, temp_doc, key):
    response = api.post("/doclayout", json={"filepath": temp_doc.name, key: "anything"})
    assert response.status_code == 422


def test_gui_starts_with_new_options(model_dict, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        "doclayout.scripts.common.create_model_dict", lambda: model_dict
    )
    monkeypatch.setattr("doclayout.scripts.common.parse_args", dict)
    app = AppTest.from_file("doclayout/scripts/streamlit_app.py").run(timeout=30)
    assert not app.exception
