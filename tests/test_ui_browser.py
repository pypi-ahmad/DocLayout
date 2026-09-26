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
    field_calls = tmp_path / "field-calls.txt"
    example_fields = {
        "request": {
            "request_date": "09/25/2026",
            "authorization_reference_number": "00125",
        },
        "member": {
            "first_name": "Alex",
            "last_name": "Example",
            "member_id": "00123",
            "date_of_birth": None,
        },
        "referring_provider": {"name": "Example referring clinic", "npi": "0012345678"},
        "servicing_provider": {"name": "Example servicing clinic"},
        "requested_service_dates": {
            "service_start_date": "10/01/2026",
            "service_end_date": "10/31/2026",
        },
        "diagnoses": [
            {
                "code": "Z00.00",
                "code_system": "ICD-10",
                "description": "Routine examination",
            }
        ],
        "requested_services": [
            {
                "code": "99213",
                "code_system": "CPT",
                "requested_units_or_visits": "2",
                "frequency": "Weekly",
                "original_request_text": "Two requested visits.",
            }
        ],
        "expedited_requested": False,
        "additional_information": "Hello, World! First column text.",
    }
    script = tmp_path / "offline_app.py"
    script.write_text(
        f"""import runpy
from pathlib import Path
import doclayout.scripts.common
import doclayout.ui.batch
import doclayout.layout
from doclayout.schema.layout import LayoutAnalysis
from doclayout.fields import ground_records
from doclayout.settings import settings
from openai.resources.responses.responses import Responses
settings.OUTPUT_DIR = {str(tmp_path / "outputs")!r}
def blocked(*args, **kwargs):
    raise AssertionError("Live API disabled in browser test")
Responses.create = blocked
Responses.parse = blocked

class OfflineLayout:
    status = "Not loaded"
    actual_device = None
    def prepare(self):
        if self.actual_device is not None:
            return
        import time
        time.sleep(1)  # Expose the loading state without weights or native inference.
        self.actual_device = "cpu"
        self.status = "Ready: offline browser test"
    def analyze(self, image):
        return LayoutAnalysis(
            image_size=image.size, provider="test", model_id="test",
            model_revision="fixture", actual_device="cpu", elapsed_ms=0,
            candidate_count=0, filtered_count=0, regions=[],
        )
    def retry_failed(self):
        pass

layout_engine = OfflineLayout()
doclayout.layout.get_layout_engine = lambda: layout_engine
doclayout.ui.batch.get_layout_engine = doclayout.layout.get_layout_engine
def extract(prompt, image, block, schema, **kwargs):
    with Path({str(calls)!r}).open("a") as stream:
        stream.write("call\\n")
    block.update_metadata(llm_request_count=1, llm_tokens_used=123)
    result = {page_result!r}
    if block.page_id == 1:
        result["blocks"][1]["html"] = "<p>Second page supporting text.</p>"
    return result

def fields(markdown, chunks, definition, **kwargs):
    with Path({str(field_calls)!r}).open("a") as stream:
        stream.write("call\\n")
    value = {{"records": [{{"fields": {example_fields!r},
        "evidence": [{{"field_path": "/additional_information", "quote": "Hello, World! First column text."}}],
        "issues": []}}], "document_issues": []}}
    outcome = ground_records(value, markdown, chunks)
    # Synthetic presentation fixture; issue rendering is covered by AppTest.
    outcome["records"][0]["issues"] = []
    return {{**outcome, "status": "success", "classification": {{"status": "disabled"}}}}
doclayout.ui.batch.extract_fields = fields
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
                expect(
                    page.get_by_text("Preparing layout model…", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("OCR complete", exact=False)).to_be_visible(
                    timeout=30_000
                )
                expect(
                    page.get_by_text("PP-DocLayoutV3 · CPU", exact=True)
                ).to_be_visible()
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
                page.get_by_role(
                    "button", name=re.compile("View extracted information$")
                ).click()
                expect(
                    page.get_by_role(
                        "heading", name="Extracted information", exact=True
                    )
                ).to_be_visible()
                expect(
                    page.get_by_role(
                        "button", name=re.compile(r"Download data \(JSON\)$")
                    )
                ).to_be_visible()
                expect(
                    page.get_by_role("tab", name="Summary", exact=True)
                ).to_have_attribute("aria-selected", "true")
                expect(
                    page.get_by_text("Hello, World! First column text.", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Not found", exact=True)).to_have_count(0)
                page.get_by_text("Show missing information", exact=True).click()
                expect(page.get_by_text("Not found", exact=True).first).to_be_visible()
                page.get_by_text("Show missing information", exact=True).click()
                expect(page.get_by_text("Not found", exact=True)).to_have_count(0)
                for scheme in ("light", "dark"):
                    page.emulate_media(color_scheme=scheme)
                    for width in (1280, 390):
                        page.set_viewport_size({"width": width, "height": 900})
                        if (
                            width == 390
                            and page.get_by_test_id("stSidebar").get_attribute(
                                "aria-expanded"
                            )
                            == "true"
                        ):
                            page.get_by_test_id("stSidebarCollapseButton").get_by_role(
                                "button"
                            ).click()
                            expect(page.get_by_test_id("stSidebar")).to_have_attribute(
                                "aria-expanded", "false"
                            )
                        expect(
                            page.get_by_role(
                                "heading", name="Additional information", exact=True
                            )
                        ).to_be_visible()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                        page.screenshot(
                            path=str(tmp_path / f"summary-{scheme}-{width}.png"),
                            full_page=True,
                            animations="disabled",
                        )
                        page.get_by_role(
                            "heading", name="Requested services", exact=True
                        ).scroll_into_view_if_needed()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                        page.screenshot(
                            path=str(tmp_path / f"services-{scheme}-{width}.png"),
                            animations="disabled",
                        )
                        page.get_by_role(
                            "heading", name="Extracted information", exact=True
                        ).scroll_into_view_if_needed()
                page.set_viewport_size({"width": 1280, "height": 900})
                page.emulate_media(color_scheme="light")
                page.get_by_role("tab", name="Source document", exact=True).click()
                field = page.locator(".fields button").filter(
                    has_text="Additional information"
                )
                expect(field).not_to_contain_text("/additional_information")
                region = page.locator('rect[role="button"]')
                expect(region).to_have_count(1)
                field.hover()
                expect(region).to_have_class("active")
                region.hover()
                expect(field).to_have_class("active")
                region.click()
                expect(field).to_have_class("active")
                page.reload()
                expect(
                    page.get_by_role(
                        "button", name=re.compile(r"Download data \(JSON\)$")
                    )
                ).to_be_visible()
                assert calls.read_text().splitlines() == ["call", "call"]
                assert field_calls.read_text().splitlines() == ["call"]
                if (
                    page.get_by_test_id("stSidebar").get_attribute("aria-expanded")
                    == "false"
                ):
                    page.get_by_test_id("stExpandSidebarButton").click()
                page.get_by_role("button", name="Convert documents", exact=True).click()
                page.locator('input[type="file"]').set_input_files(
                    [
                        {
                            "name": "one.pdf",
                            "mimeType": "application/pdf",
                            "buffer": Path(temp_doc.name).read_bytes(),
                        },
                        {
                            "name": "two.pdf",
                            "mimeType": "application/pdf",
                            "buffer": Path(temp_doc.name).read_bytes(),
                        },
                    ]
                )
                expect(page.get_by_label("Start page", exact=True)).to_have_count(0)
                expect(page.get_by_label("End page", exact=True)).to_have_count(0)
                page.get_by_role("button", name="Run DocLayout", exact=True).click()
                expect(page.get_by_text("2/2 complete", exact=True)).to_be_visible(
                    timeout=30_000
                )
                assert len(calls.read_text().splitlines()) == 6
                selector = page.get_by_test_id("stSelectbox").filter(
                    has_text="Result document"
                )
                selector.get_by_role("combobox").click()
                page.get_by_role("option", name="two.pdf", exact=True).click()
                page.get_by_role(
                    "button", name=re.compile("View extracted information$")
                ).click()
                with page.expect_download() as download:
                    page.get_by_role(
                        "button", name=re.compile(r"Download data \(JSON\)$")
                    ).click()
                assert download.value.suggested_filename == "two_001.json"
                exported = json.loads(Path(download.value.path()).read_text("utf-8"))
                assert (
                    exported["fields"]["additional_information"]
                    == "Hello, World! First column text."
                )
                assert len(field_calls.read_text().splitlines()) == 3
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=15)
