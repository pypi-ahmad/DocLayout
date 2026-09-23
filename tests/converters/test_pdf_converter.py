import io

import pytest

from doclayout.converters.ocr import OCRConverter
from doclayout.converters.pdf import PdfConverter
from doclayout.converters.table import TableConverter
from doclayout.services.openai import ExtractionError


def test_converter_bytes(pdf_converter, temp_doc, extraction_service):
    with open(temp_doc.name, "rb") as stream:
        rendered = pdf_converter(io.BytesIO(stream.read()))
    assert "Hello, World!" in rendered.markdown
    assert extraction_service.call_count == 2


@pytest.mark.parametrize("converter", [PdfConverter, OCRConverter, TableConverter])
def test_converter_uses_one_extraction_per_page(
    converter, model_dict, temp_doc, extraction_service
):
    result = converter(model_dict)(temp_doc.name)
    assert extraction_service.call_count == 2
    assert result.metadata["extraction"]["model"] == "gpt-6-sol"


def test_table_filter(model_dict, temp_doc):
    document = TableConverter(model_dict).build_document(temp_doc.name)
    assert all(
        block_id.block_type.name == "Table"
        for p in document.pages
        for block_id in p.structure
    )


def test_ocr_order(model_dict, temp_doc):
    output = OCRConverter(model_dict)(temp_doc.name)
    assert [b.block_type for b in output.children[0].children][:4] == [
        "SectionHeader",
        "Text",
        "Equation",
        "Table",
    ]


def test_failure_does_not_save(
    model_dict, extraction_service, temp_doc, tmp_path, monkeypatch
):
    from click.testing import CliRunner

    from doclayout.scripts.convert_single import convert_single_cli

    monkeypatch.setattr(
        "doclayout.scripts.convert_single.create_model_dict", lambda: model_dict
    )
    extraction_service.side_effect = ExtractionError("incomplete")
    folder = tmp_path / "document"
    folder.mkdir()
    previous = folder / "document.md"
    previous.write_text("existing result")
    result = CliRunner().invoke(
        convert_single_cli, [temp_doc.name, "--output_dir", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert previous.read_text() == "existing result"


def test_batch_continues(
    model_dict, extraction_service, temp_doc, tmp_path, monkeypatch
):
    from click.testing import CliRunner

    from doclayout.scripts.convert import convert_cli

    monkeypatch.setattr("doclayout.scripts.convert.create_model_dict", lambda: model_dict)
    (tmp_path / "bad.pdf").write_text("not a PDF")
    result = CliRunner().invoke(
        convert_cli, [str(tmp_path), "--output_dir", str(tmp_path / "output")]
    )
    assert result.exit_code != 0
    assert list((tmp_path / "output/document").glob("document_*.md"))
