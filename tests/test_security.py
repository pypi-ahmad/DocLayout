"""Small defensive regression fixtures; no external calls or stress inputs."""

import asyncio
import base64
import io
from pathlib import Path
from threading import Event
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from doclayout.credentials import CredentialsError, api_configuration
from doclayout.providers.html import HTMLProvider
from doclayout.providers.spreadsheet import SpreadSheetProvider
from doclayout.scripts import server
from doclayout.security import (
    DocumentLimitError,
    check_file,
    check_pixels,
    embedded_resource,
)
from doclayout.settings import settings
from doclayout.util import parse_range_str

TOKEN = "dummy-api-token-" * 3


@pytest.fixture
def api(model_dict, monkeypatch, tmp_path):
    monkeypatch.setenv("DOCLAYOUT_API_TOKEN", TOKEN)
    monkeypatch.setenv("DOCLAYOUT_INPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(server, "create_model_dict", lambda: model_dict)
    with TestClient(server.app) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        yield client


def test_authentication_before_body_consumption(monkeypatch):
    monkeypatch.setitem(server.app_data, "token", TOKEN)
    touched = []

    async def inner(*args):
        pytest.fail("Unauthenticated request reached the application")

    async def receive():
        pytest.fail("Unauthenticated body was consumed")

    async def send(message):
        touched.append(message)

    asyncio.run(
        server.RequestGuard(inner)(
            {"type": "http", "method": "POST", "headers": []}, receive, send
        )
    )
    assert touched[0]["status"] == 401


def test_api_token_required(monkeypatch):
    monkeypatch.setenv("DOCLAYOUT_API_TOKEN", "")
    monkeypatch.setenv("DOCLAYOUT_INPUT_ROOT", "")
    with pytest.raises(CredentialsError):
        api_configuration()


def test_path_disabled_and_confined(api, tmp_path, temp_doc, monkeypatch):
    monkeypatch.setitem(server.app_data, "root", None)
    assert api.post("/doclayout", json={"filepath": temp_doc.name}).status_code == 403
    monkeypatch.setitem(server.app_data, "root", tmp_path / "allowed")
    assert api.post("/doclayout", json={"filepath": temp_doc.name}).status_code == 403
    for name in (
        "../document.pdf",
        "document.pdf:stream",
        "//server/share/document.pdf",
    ):
        assert api.post("/doclayout", json={"filepath": name}).status_code == 403


def test_upload_rejects_filepath_and_duplicate_fields(api):
    parts = [
        ("file", ("doc.pdf", b"ordinary bytes", "application/pdf")),
        ("output_format", (None, "json")),
        ("output_format", (None, "html")),
    ]
    assert api.post("/doclayout/upload", files=parts).status_code == 422
    assert (
        api.post(
            "/doclayout/upload",
            files={"file": ("doc.pdf", b"x")},
            data={"filepath": "private.pdf"},
        ).status_code
        == 422
    )


def test_small_configured_upload_limit(api, monkeypatch):
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_FILE_MIB", 0)
    assert (
        api.post(
            "/doclayout/upload", files={"file": ("doc.pdf", b"ordinary")}
        ).status_code
        == 413
    )


def test_stream_limit_without_content_length(api, monkeypatch):
    # Shrink the unit for this fixture instead of allocating a large request.
    monkeypatch.setattr(server, "MIB", 1)
    assert (
        api.post("/doclayout", content=iter([b" " * 120, b" " * 120])).status_code
        == 413
    )


def test_generic_conversion_error(api, monkeypatch):
    def fail(*args):
        raise RuntimeError("dummy-private-path-and-token")

    monkeypatch.setattr(server, "_convert_pdf", fail)
    response = api.post("/doclayout/upload", files={"file": ("doc.pdf", b"ordinary")})
    assert response.status_code == 500
    assert "dummy-private" not in response.text
    assert not server.app_data["busy"]


def test_busy_conversion_keeps_event_loop_responsive(api, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    started, release = Event(), Event()

    def convert(*args):
        started.set()
        assert release.wait(5)
        return {"success": True}

    monkeypatch.setattr(server, "_convert_pdf", convert)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(
            api.post, "/doclayout/upload", files={"file": ("doc.pdf", b"x")}
        )
        try:
            assert started.wait(5)
            assert api.get("/").status_code == 200
            assert (
                api.post(
                    "/doclayout/upload", files={"file": ("doc.pdf", b"x")}
                ).status_code
                == 429
            )
        finally:
            release.set()
        assert pending.result().status_code == 200


@pytest.mark.parametrize("text", ["", "-1", "3-1", "1.5", "0-999999999"])
def test_range_rejected_without_expansion(text):
    with pytest.raises(ValueError):
        parse_range_str(text)


def test_range_cap_and_duplicates(monkeypatch):
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_PAGES", 2)
    assert parse_range_str("0-1,1") == [0, 1]
    with pytest.raises(DocumentLimitError):
        parse_range_str("0,1,2")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/image.png",
        "file:///dummy.png",
        "//example.invalid/image.png",
    ],
)
def test_external_resources_never_delegated(url):
    with pytest.raises(ValueError, match="disabled"):
        embedded_resource(url)


def test_embedded_resource_and_pixel_caps(monkeypatch):
    assert (
        embedded_resource(
            "data:image/png;base64," + base64.b64encode(b"dummy").decode()
        )["string"]
        == b"dummy"
    )
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_RESOURCE_MIB", 0)
    with pytest.raises(DocumentLimitError):
        embedded_resource("data:text/plain,x")
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_RENDER_PIXELS", 16)
    check_pixels(4, 4)
    with pytest.raises(DocumentLimitError):
        check_pixels(5, 4)


def test_archive_limits_use_small_fixture(tmp_path, monkeypatch):
    path = tmp_path / "book.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("first", "x")
        archive.writestr("second", "y")
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(DocumentLimitError):
        check_file(path)


def test_spreadsheet_text_is_escaped_and_cells_bounded(monkeypatch):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "<em>ordinary & text</em>"
    provider = object.__new__(SpreadSheetProvider)
    html = provider._excel_to_html_table(sheet)
    assert "&lt;em&gt;ordinary &amp; text&lt;/em&gt;" in html
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_WORKSHEET_CELLS", 1)
    sheet["B1"] = "second cell"
    with pytest.raises(DocumentLimitError):
        provider._excel_to_html_table(sheet)
    workbook.close()


def test_temporary_pdf_removed_on_failure(temp_doc, monkeypatch):
    paths = []

    def fail(self, path):
        paths.append(Path(self.temp_pdf_path))
        raise ValueError("ordinary conversion failure")

    monkeypatch.setattr(HTMLProvider, "convert_html_to_pdf", fail)
    with pytest.raises(ValueError):
        HTMLProvider(temp_doc.name)
    assert paths and all(not path.exists() for path in paths)


def test_file_copy_is_chunked_and_bounded(monkeypatch):
    monkeypatch.setattr(server, "MIB", 1)
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_FILE_MIB", 4)
    with pytest.raises(DocumentLimitError):
        server._copy_limited(io.BytesIO(b"12345"), io.BytesIO())


@pytest.mark.parametrize("phase", ["startup", "shutdown"])
def test_lifespan_always_clears_state(monkeypatch, phase):
    monkeypatch.setattr(server, "api_configuration", lambda: (TOKEN, None))

    def fail(*args):
        raise RuntimeError("ordinary lifecycle failure")

    monkeypatch.setattr(
        server, "create_model_dict", fail if phase == "startup" else lambda: {}
    )
    monkeypatch.setattr(server, "shutdown_models", fail)

    async def run():
        with pytest.raises(RuntimeError):
            async with server.lifespan(server.app):
                pass
        assert server.app_data == {}

    asyncio.run(run())


def test_json_has_small_body_cap(api):
    assert api.post("/doclayout", content=b" " * (64 * 1024 + 1)).status_code == 413


def test_bearer_scheme_is_case_insensitive(api, monkeypatch):
    monkeypatch.setattr(server, "_convert_pdf", lambda *args: {"success": True})
    api.headers["Authorization"] = "bearer " + TOKEN
    assert (
        api.post("/doclayout/upload", files={"file": ("doc.pdf", b"x")}).status_code
        == 200
    )


def test_input_handle_allows_only_regular_single_link(tmp_path):
    import os
    from doclayout.input_files import input_file

    path = tmp_path / "ordinary.txt"
    path.write_bytes(b"ordinary")
    for name in (path.name, str(path)):
        with input_file(name, tmp_path) as source:
            assert source.read() == b"ordinary"
    link = tmp_path / "linked.txt"
    os.link(path, link)
    with pytest.raises(ValueError):
        with input_file(str(link), tmp_path):
            pytest.fail("hard-linked file accepted")


def test_embedded_image_checked_before_encoding(monkeypatch):
    from PIL import Image
    from doclayout.security import image_data_uri
    from doclayout.providers.document import DocumentProvider

    output = io.BytesIO()
    with Image.new("RGB", (3, 3)) as image:
        image.save(output, "PNG")
    uri = image_data_uri(output.getvalue(), "image/png")
    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_SOURCE_PIXELS", 4)
    with pytest.raises(DocumentLimitError):
        image_data_uri(output.getvalue(), "image/png")
    with pytest.raises(DocumentLimitError):
        DocumentProvider._preprocess_base64_images(f'<img src="{uri}">')


def test_bytesio_limit_before_copy(monkeypatch):
    from doclayout.converters.pdf import PdfConverter

    monkeypatch.setattr(settings, "DOCLAYOUT_MAX_FILE_MIB", 0)
    converter = object.__new__(PdfConverter)
    with pytest.raises(DocumentLimitError):
        with converter.filepath_to_str(io.BytesIO(b"ordinary")):
            pytest.fail("oversized BytesIO accepted")


def test_direct_page_selection_deduplicated(temp_doc):
    from doclayout.providers.pdf import PdfProvider

    with PdfProvider(temp_doc.name, {"page_range": [0, 0]}) as provider:
        assert provider.page_range == [0]


def test_preview_uses_only_generated_images():
    from bs4 import BeautifulSoup
    from PIL import Image
    from doclayout.ui.exports import markdown_preview

    with Image.new("RGB", (2, 2)) as image:
        preview = markdown_preview(
            "# Ordinary\n\n![crop](crop.png)\n\n![linked](https://example.invalid/image.png)",
            {"crop.png": image},
        )
    soup = BeautifulSoup(preview, "html.parser")
    assert soup.h1.text == "Ordinary"
    assert len(soup.find_all("img")) == 1
    assert soup.img["src"].startswith("data:image/png;base64,")
    assert "example.invalid" not in preview
    assert soup.find("style") is None


def test_upload_documented_in_openapi(api):
    schema = api.get("/openapi.json").json()
    upload = schema["paths"]["/doclayout/upload"]["post"]
    assert (
        upload["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"][
            "file"
        ]["format"]
        == "binary"
    )
    assert upload["security"]


def test_cancellation_does_not_release_active_worker(monkeypatch):
    import anyio

    started, release = Event(), Event()
    monkeypatch.setitem(server.app_data, "token", TOKEN)
    monkeypatch.setitem(server.app_data, "busy", False)

    def worker():
        started.set()
        assert release.wait(5)

    async def inner(*args):
        await server._run(worker)

    async def nothing(*args):
        pass

    async def run():
        async with anyio.create_task_group() as group:
            group.start_soon(
                server.RequestGuard(inner),
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/doclayout",
                    "headers": [(b"authorization", ("Bearer " + TOKEN).encode())],
                },
                nothing,
                nothing,
            )
            with anyio.fail_after(3):
                while not started.is_set():
                    await anyio.sleep(0.01)
            group.cancel_scope.cancel()
            with anyio.CancelScope(shield=True):
                await anyio.sleep(0.02)
                assert server.app_data["busy"]
                release.set()
        assert not server.app_data["busy"]

    try:
        anyio.run(run)
    finally:
        release.set()


def test_partial_multipart_spool_closed_on_limit(monkeypatch):
    import starlette.formparsers as parser
    from starlette.requests import Request

    opened = []
    original = parser.SpooledTemporaryFile

    def track(*args, **kwargs):
        file = original(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(parser, "SpooledTemporaryFile", track)
    monkeypatch.setattr(server, "MIB", 1)
    monkeypatch.setitem(server.app_data, "token", TOKEN)
    monkeypatch.setitem(server.app_data, "busy", False)
    parts = iter(
        [
            b'--ordinary\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\nx',
            b" " * 150,
        ]
    )

    async def receive():
        return {"type": "http.request", "body": next(parts), "more_body": True}

    async def inner(scope, receive, send):
        with pytest.raises(parser.MultiPartException):
            async with Request(scope, receive).form():
                pytest.fail("over-limit body accepted")

    async def send(message):
        pass

    asyncio.run(
        server.RequestGuard(inner)(
            {
                "type": "http",
                "method": "POST",
                "path": "/doclayout/upload",
                "headers": [
                    (b"authorization", ("Bearer " + TOKEN).encode()),
                    (b"content-type", b"multipart/form-data; boundary=ordinary"),
                ],
            },
            receive,
            send,
        )
    )
    assert opened and all(file.closed for file in opened)


@pytest.mark.parametrize("fail", [False, True])
def test_font_download_atomic_and_cleanup(tmp_path, monkeypatch, fail):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from doclayout import util

    target = tmp_path / "font.ttf"
    monkeypatch.setattr(settings, "FONT_PATH", str(target))

    def chunks(**kwargs):
        yield b"ordinary font bytes"
        assert not target.exists()
        if fail:
            raise OSError("ordinary interrupted download")

    def get(url, **kwargs):
        assert kwargs == {"stream": True, "timeout": (5, 10)}
        return nullcontext(
            SimpleNamespace(raise_for_status=lambda: None, iter_content=chunks)
        )

    monkeypatch.setattr(util.requests, "get", get)
    if fail:
        with pytest.raises(OSError):
            util.download_font()
        assert list(tmp_path.iterdir()) == []
    else:
        util.download_font()
        assert target.read_bytes() == b"ordinary font bytes"
        assert list(tmp_path.iterdir()) == [target]
