import hashlib
import threading
import time

import pytest
from pydantic import ValidationError

from doclayout.builders.document import DocumentBuilder
from doclayout.schema.extraction import PAGE_PROMPT, ExtractedPage, sanitize_html


def test_pages_and_geometry(pdf_document, extraction_service):
    assert extraction_service.call_count == 2
    # Fingerprint only the packaged instructions; page priors vary per image.
    assert hashlib.sha256(PAGE_PROMPT.encode("utf-8")).hexdigest() == (
        "57d05c2a4b72fac16d380fe4da5b7bd23e547520156ca648fafbfef203efaefc"
    )
    for call in extraction_service.call_args_list:
        assert call.args[0].startswith(PAGE_PROMPT.rstrip() + "\n\n")
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
