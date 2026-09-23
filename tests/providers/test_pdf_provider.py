import pypdfium2 as pdfium
import pytest

from doclayout.providers.pdf import PdfProvider


def test_render_only(temp_doc):
    provider = PdfProvider(temp_doc.name)
    assert len(provider) == 2
    assert provider.get_page_lines(0) == []
    assert provider.get_images([0], 72)[0].size == (512, 512)


@pytest.mark.parametrize("pages", [[], [-1], [2]])
def test_invalid_range(temp_doc, pages):
    with pytest.raises(ValueError, match="page_range"):
        PdfProvider(temp_doc.name, {"page_range": pages})


def test_rotated_geometry(temp_doc, tmp_path):
    path = tmp_path / "rotated.pdf"
    with pdfium.PdfDocument(temp_doc.name) as doc:
        page = doc[0]
        page.set_rotation(90)
        page.close()
        doc.save(str(path))
    provider = PdfProvider(str(path))
    image = provider.get_images([0], 72)[0]
    assert tuple(provider.get_page_bbox(0).size) == image.size
