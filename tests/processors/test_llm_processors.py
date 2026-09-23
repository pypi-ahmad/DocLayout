from unittest.mock import MagicMock, Mock

import pytest

from doclayout.processors.llm.llm_complex import LLMComplexRegionProcessor
from doclayout.processors.llm.llm_equation import LLMEquationProcessor
from doclayout.processors.llm.llm_form import LLMFormProcessor
from doclayout.processors.llm.llm_image_description import LLMImageDescriptionProcessor
from doclayout.processors.llm.llm_meta import LLMSimpleBlockMetaProcessor
from doclayout.processors.llm.llm_table import LLMTableProcessor
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import ComplexRegion


def test_page_correction_reorders_real_ids(pdf_document):
    from doclayout.processors.llm.llm_page_correction import LLMPageCorrectionProcessor

    page = pdf_document.pages[0]
    original = list(page.structure)
    processor = LLMPageCorrectionProcessor(Mock(), {"use_llm": True})
    processor.handle_reorder([{"id": str(b)} for b in reversed(original)], page)
    assert page.structure == list(reversed(original))
    processor.handle_reorder([{"id": str(original[0])}], page)
    assert page.structure == list(reversed(original))
    assert page.metadata.llm_error_count == 1


def test_llm_form_processor(pdf_document):
    from doclayout.schema.blocks import Form

    page = pdf_document.pages[0]
    original = page.get_block(page.structure[1])
    form = page.add_block(Form, original.polygon)
    form.html = "<table><tr><td>Name</td><td>Original</td></tr></table>"
    page.structure.append(form.id)
    replacement = "<table><tr><td>Name</td><td>Corrected value</td></tr></table>"
    service = Mock(return_value={"corrected_html": replacement})
    config = {"use_llm": True}
    LLMSimpleBlockMetaProcessor([LLMFormProcessor(config)], service, config)(
        pdf_document
    )
    assert form.html == replacement


def test_refinement_failure_preserves_extraction(pdf_document, caplog):
    from doclayout.services.openai import ExtractionError

    before = [b.html for b in pdf_document.pages[0].children]
    service = Mock(side_effect=ExtractionError("incomplete"))
    LLMTableProcessor(service, {"use_llm": True})(pdf_document)
    assert [b.html for b in pdf_document.pages[0].children] == before
    assert "Error rewriting" in caplog.text


@pytest.mark.config({"page_range": [0]})
def test_llm_table_processor(pdf_document):
    corrected_html = """
<table>
    <tr>
        <td>Column 1</td>
        <td>Column 2</td>
        <td>Column 3</td>
        <td>Column 4</td>
    </tr>
    <tr>
        <td>Value 1 <math>x</math></td>
        <td>Value 2</td>
        <td>Value 3</td>
        <td>Value 4</td>
    </tr>
    <tr>
        <td>Value 5</td>
        <td>Value 6</td>
        <td>Value 7</td>
        <td>Value 8</td>
    </tr>
</table>
    """.strip()

    mock_cls = Mock()
    mock_cls.return_value = {"corrected_html": corrected_html}

    processor = LLMTableProcessor(mock_cls, {"use_llm": True})
    processor(pdf_document)

    tables = pdf_document.contained_blocks((BlockTypes.Table,))
    table_cells = tables[0].contained_blocks(pdf_document, (BlockTypes.TableCell,))
    if table_cells:
        # Simple-mode table - LLM rewrite parsed the html into cells
        assert table_cells[0].text == "Column 1"
    else:
        # Full-mode (OCR'd) table - LLM rewrite wrote the html back
        assert "Column 1" in tables[0].html

    markdown = MarkdownRenderer()(pdf_document).markdown
    assert "Value 1 $x$" in markdown


@pytest.mark.config({"page_range": [0]})
def test_llm_caption_processor_disabled(pdf_document):
    config = {"use_llm": True}
    mock_cls = MagicMock()
    processor_lst = [LLMImageDescriptionProcessor(config)]
    processor = LLMSimpleBlockMetaProcessor(processor_lst, mock_cls, config)
    processor(pdf_document)

    contained_pictures = pdf_document.contained_blocks(
        (BlockTypes.Picture, BlockTypes.Figure)
    )
    assert all(picture.description is None for picture in contained_pictures)


@pytest.mark.config({"page_range": [0]})
def test_llm_caption_processor(pdf_document):
    description = "This is an image description."
    mock_cls = Mock()
    mock_cls.return_value = {"image_description": description}

    config = {"use_llm": True, "extract_images": False}
    processor_lst = [LLMImageDescriptionProcessor(config)]
    processor = LLMSimpleBlockMetaProcessor(processor_lst, mock_cls, config)
    processor(pdf_document)

    contained_pictures = pdf_document.contained_blocks(
        (BlockTypes.Picture, BlockTypes.Figure)
    )
    assert all(picture.description == description for picture in contained_pictures)

    # Ensure the rendering includes the description
    renderer = MarkdownRenderer({"extract_images": False})
    md = renderer(pdf_document).markdown

    assert description in md


@pytest.mark.config({"page_range": [0]})
def test_llm_complex_region_processor(pdf_document):
    md = "This is some *markdown* for a complex region."
    mock_cls = Mock()
    mock_cls.return_value = {"corrected_markdown": md * 25}

    # Replace the block with a complex region (use a live structure block -
    # children can contain blocks retired by full-page OCR)
    old_block = pdf_document.pages[0].get_block(pdf_document.pages[0].structure[0])
    new_block = ComplexRegion(
        **old_block.dict(exclude=["id", "block_id", "block_type"]),
    )
    pdf_document.pages[0].replace_block(old_block, new_block)

    # Test processor
    config = {"use_llm": True}
    processor_lst = [LLMComplexRegionProcessor(config)]
    processor = LLMSimpleBlockMetaProcessor(processor_lst, mock_cls, config)
    processor(pdf_document)

    # Ensure the rendering includes the description
    renderer = MarkdownRenderer()
    rendered_md = renderer(pdf_document).markdown

    assert md in rendered_md


@pytest.mark.config({"page_range": [0]})
def test_multi_llm_processors(pdf_document):
    description = (
        "<math>This is an image description.  And here is a lot of writing about it.</math>"
        * 10
    )
    mock_cls = Mock()
    mock_cls.return_value = {
        "image_description": description,
        "corrected_equation": description,
    }

    config = {
        "use_llm": True,
        "extract_images": False,
        "min_equation_height": 0.001,
    }
    processor_lst = [LLMImageDescriptionProcessor(config), LLMEquationProcessor(config)]
    processor = LLMSimpleBlockMetaProcessor(processor_lst, mock_cls, config)
    processor(pdf_document)

    contained_pictures = pdf_document.contained_blocks(
        (BlockTypes.Picture, BlockTypes.Figure)
    )
    assert all(picture.description == description for picture in contained_pictures)

    contained_equations = pdf_document.contained_blocks((BlockTypes.Equation,))
    print([equation.html for equation in contained_equations])
    assert all(equation.html == description for equation in contained_equations)
