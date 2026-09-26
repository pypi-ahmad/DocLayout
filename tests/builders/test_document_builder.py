import hashlib
import json
import threading
import time

import pytest
from pydantic import ValidationError

from doclayout.builders.document import DocumentBuilder
from doclayout.schema.extraction import ExtractedPage, sanitize_html


def test_pages_and_geometry(pdf_document, extraction_service):
    assert extraction_service.call_count == 2
    # Static instructions are fingerprinted separately from per-page layout data.
    for call in extraction_service.call_args_list:
        prompt, guide = call.args[0].split("\n\ngiven_layout=", 1)
        assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == (
            "a7ba7c1b7a7c901aa38e5219b394d6c36f7a9e307edff210f1b4cd8683559b8e"
        )
        assert json.loads(guide)["image_size"] == list(call.args[1].size)
    page = pdf_document.pages[0]
    assert page.text_extraction_method == "openai"
    assert len(page.structure) == 7
    assert page.get_block(page.structure[0]).html.startswith("<h1>")
    assert all(block.polygon.x_end <= page.polygon.x_end for block in page.children)
    assert page.metadata.llm_request_count == 1
    assert page.metadata.llm_tokens_used == 123
    assert all(block.structure is None for block in page.children)


def test_blank_page(doc_provider):
    document = DocumentBuilder()(
        doc_provider, lambda *args: {"blank": True, "blocks": []}
    )
    assert all(page.structure == [] for page in document.pages)


@pytest.mark.parametrize(
    "change",
    [
        {"blank": True},
        {"blocks": []},
        {"blocks": [{"block_type": "Unknown", "html": "text", "bbox": [0, 0, 10, 10]}]},
        {"blocks": [{"block_type": "Text", "html": "", "bbox": [0, 0, 10, 10]}]},
        {"blocks": [{"block_type": "Text", "html": "text", "bbox": [10, 0, 0, 10]}]},
        {"blocks": [{"block_type": "Text", "html": "text", "bbox": [0, 0, 1001, 10]}]},
    ],
)
def test_invalid_response(page_result, change):
    with pytest.raises(ValidationError):
        ExtractedPage.model_validate(page_result | change)


def test_render_on_caller_thread(doc_provider, page_result, monkeypatch):
    caller = threading.get_ident()
    original = doc_provider.get_images
    render_threads, request_threads = [], []

    def render(*args):
        render_threads.append(threading.get_ident())
        return original(*args)

    def extract(*args):
        request_threads.append(threading.get_ident())
        time.sleep(0.01)
        return page_result

    monkeypatch.setattr(doc_provider, "get_images", render)
    DocumentBuilder()(doc_provider, extract)
    assert set(render_threads) == {caller}
    assert caller not in request_threads


def test_html_safety():
    html = sanitize_html(
        '<script>alert(1)</script><p onclick="evil()">Keep <a href="javascript:evil()">link</a></p><math display="block">x</math><table><tr><td colspan="2">42</td></tr></table>'
    )
    assert "script" not in html and "onclick" not in html and "evil" not in html
    assert 'display="block"' in html and 'colspan="2"' in html
