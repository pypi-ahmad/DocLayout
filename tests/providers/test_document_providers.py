"""Document providers retain PDF rendering; extraction is handled by GPT."""

import shutil

import pytest

from doclayout.providers.document import DocumentProvider
from doclayout.providers.epub import EpubProvider
from doclayout.providers.html import HTMLProvider
from doclayout.providers.powerpoint import PowerPointProvider
from doclayout.providers.spreadsheet import SpreadSheetProvider


@pytest.mark.parametrize(
    "cls,method",
    [
        (DocumentProvider, "convert_docx_to_pdf"),
        (EpubProvider, "convert_epub_to_pdf"),
        (HTMLProvider, "convert_html_to_pdf"),
        (PowerPointProvider, "convert_pptx_to_pdf"),
        (SpreadSheetProvider, "convert_xlsx_to_pdf"),
    ],
)
def test_converted_documents_use_render_provider(cls, method, temp_doc, monkeypatch):
    def converted(self, filepath):
        shutil.copyfile(temp_doc.name, self.temp_pdf_path)

    monkeypatch.setattr(cls, method, converted)
    provider = cls("source.document")
    assert provider.get_images([0], 72)[0].size == (512, 512)
    assert provider.get_page_lines(0) == []
