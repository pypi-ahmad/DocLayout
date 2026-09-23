import json

import pytest
from click.testing import CliRunner

from doclayout.config.parser import ConfigParser
from doclayout.converters.pdf import PdfConverter
from doclayout.scripts.convert_single import convert_single_cli


@pytest.mark.parametrize(
    "key",
    [
        "mode",
        "force_ocr",
        "disable_ocr",
        "strip_existing_ocr",
        "openai_model",
        "llm_service",
        "torch_device",
        "LayoutBuilder_force_ocr",
        "pdftext_workers",
    ],
)
def test_removed_settings(key, model_dict, tmp_path):
    with pytest.raises(ValueError, match="Removed configuration"):
        PdfConverter(model_dict, config={key: False})
    path = tmp_path / "config.json"
    path.write_text(json.dumps({key: False}))
    with pytest.raises(ValueError, match="Removed configuration"):
        ConfigParser({"config_json": str(path)}).generate_config_dict()
    result = CliRunner().invoke(convert_single_cli, ["--" + key, "test.pdf"])
    assert result.exit_code != 0
    assert "Removed configuration" in result.output


def test_false_config_preserved():
    assert (
        ConfigParser({"extract_images": False}).generate_config_dict()["extract_images"]
        is False
    )


def test_cli_help():
    result = CliRunner().invoke(convert_single_cli, ["--help"])
    assert result.exit_code == 0
    assert "--use_llm" in result.output
    assert "--force_ocr" not in result.output


def test_range():
    assert ConfigParser({"page_range": "0,2-3"}).generate_config_dict()[
        "page_range"
    ] == [0, 2, 3]
