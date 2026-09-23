import pytest

from doclayout.renderers.markdown import MarkdownRenderer


@pytest.mark.config({"page_range": [0]})
def test_disable_extract_images(pdf_document):
    renderer = MarkdownRenderer({"extract_images": False})
    md = renderer(pdf_document).markdown

    # Verify markdown
    assert "jpeg" not in md


@pytest.mark.config({"page_range": [0]})
def test_extract_images(pdf_document):
    renderer = MarkdownRenderer()
    md = renderer(pdf_document).markdown

    # Verify markdown
    assert "jpeg" in md