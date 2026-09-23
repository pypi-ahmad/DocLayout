from doclayout.processors.footnote import FootnoteProcessor
from doclayout.schema.blocks import Footnote


def test_footnote_processor(pdf_document):
    page = pdf_document.pages[0]
    block = page.add_block(Footnote, page.polygon)
    block.html = "<p>5 A footnote.</p>"
    page.structure.insert(1, block.id)
    FootnoteProcessor()(pdf_document)
    assert block.raw_text(pdf_document).strip() == "5 A footnote."
    assert block.id in page.structure
