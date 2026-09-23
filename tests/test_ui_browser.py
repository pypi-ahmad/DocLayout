"""Browser smoke test with an offline extraction service and real Streamlit UI."""

import io
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from zipfile import ZipFile

import requests
from playwright.sync_api import expect, sync_playwright


def test_browser_exports_and_no_repeat_ocr(tmp_path, temp_doc, page_result):
    root = Path(__file__).resolve().parents[1]
    calls = tmp_path / "calls.txt"
    script = tmp_path / "offline_app.py"
    script.write_text(
        f"""import runpy
from pathlib import Path
import doclayout.scripts.common
from openai.resources.responses.responses import Responses
def blocked(*args, **kwargs):
    raise AssertionError("Live API disabled in browser test")
Responses.create = blocked
Responses.parse = blocked
def extract(prompt, image, block, schema, **kwargs):
    with Path({str(calls)!r}).open("a") as stream:
        stream.write("call\\n")
    block.update_metadata(llm_request_count=1, llm_tokens_used=123)
    return {page_result!r}
doclayout.scripts.common.load_models = lambda: {{"extraction_service": extract}}
runpy.run_path({str(root / "doclayout/scripts/streamlit_app.py")!r}, run_name="__main__")
""",
        encoding="utf-8",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(root)}
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENAI_BASE_URL", None)
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(script),
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--server.headless=true",
                "--server.fileWatcherType=none",
                "--browser.gatherUsageStats=false",
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    if requests.get(url + "/_stcore/health", timeout=1).ok:
                        break
                except requests.RequestException:
                    time.sleep(0.2)
            else:
                raise AssertionError("Test Streamlit server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    permissions=["clipboard-read", "clipboard-write"]
                )
                page = context.new_page()
                page.goto(url)
                page.locator('input[type="file"]').set_input_files(temp_doc.name)
                expect(page.get_by_label("End page", exact=True)).to_have_value("2")
                page.get_by_role("button", name="Run DocLayout", exact=True).click()
                expect(page.get_by_text("OCR complete", exact=False)).to_be_visible(
                    timeout=30_000
                )
                page.get_by_role("tab", name="Markdown", exact=True).click()
                page.get_by_role("button", name="Copy Markdown", exact=True).click()
                expect(
                    page.get_by_text("Markdown copied.", exact=False)
                ).to_be_visible()
                # Windows clipboard normalizes text line endings to CRLF.
                raw = page.evaluate("navigator.clipboard.readText()").replace(
                    "\r\n", "\n"
                )
                assert "Hello, World!" in raw
                page.get_by_role("button", name="Copy rendered", exact=True).click()
                expect(
                    page.get_by_text("Formatted content copied.", exact=False)
                ).to_be_visible()
                assert page.evaluate(
                    "navigator.clipboard.read().then(items => items[0].types)"
                ) == ["text/plain", "text/html"]
                with page.expect_download() as download:
                    page.get_by_role(
                        "button", name="Download Markdown", exact=True
                    ).click()
                markdown_name = download.value.suggested_filename
                assert re.fullmatch(
                    re.escape(Path(temp_doc.name).stem) + r"_\d{8}_\d{6}\.md",
                    markdown_name,
                )
                assert Path(download.value.path()).read_text(encoding="utf-8") == raw
                for label, control in (
                    ("HTML", "Download HTML"),
                    ("Annotated", "Download annotated PDF"),
                    ("JSON", "Download JSON"),
                    ("Chunks", "Download Chunks"),
                    ("Chat", "Clear chat"),
                ):
                    page.get_by_role("tab", name=label, exact=True).click()
                    expect(
                        page.get_by_role("button", name=control, exact=True)
                    ).to_be_visible()
                with page.expect_download() as download:
                    page.get_by_role("button", name="Download ZIP", exact=True).click()
                assert download.value.suggested_filename == markdown_name[:-3] + ".zip"
                with ZipFile(
                    io.BytesIO(Path(download.value.path()).read_bytes())
                ) as archive:
                    assert archive.read(markdown_name).decode() == raw
                    assert json.loads(archive.read(markdown_name[:-3] + ".json"))[
                        "children"
                    ]
                assert calls.read_text().splitlines() == ["call", "call"]
                page.get_by_label("Start page", exact=True).fill("2")
                page.get_by_label("Start page", exact=True).press("Enter")
                expect(
                    page.get_by_role("button", name="Download ZIP", exact=True)
                ).to_have_count(0)
                assert calls.read_text().splitlines() == ["call", "call"]
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=15)
