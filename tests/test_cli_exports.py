"""Offline command and filesystem checks for installed-style file conversion."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from click.testing import CliRunner

from doclayout.exports import save_document_exports
from doclayout.scripts import convert, run_streamlit_app
from doclayout.services.openai import ExtractionError
from doclayout.ui.documents import prepare_upload, run_document
from doclayout.ui.exports import markdown_html


@pytest.fixture
def file_cli(model_dict, monkeypatch):
    monkeypatch.setattr(convert, "create_model_dict", lambda: model_dict)
    return CliRunner()


@pytest.mark.parametrize(
    "flags,expected",
    [
        ([], {"document.md"}),
        (["--markdown"], {"document.md"}),
        (["--html"], {"document.html"}),
        (["--json"], {"document.json"}),
        (["--chunks"], {"chunks.json"}),
        (["--metadata"], {"metadata.json"}),
        (["--annotated-pdf"], {"annotated.pdf"}),
        (["--annotated-images"], {"annotations/page-2.png"}),
        (["--json", "--chunks"], {"document.json", "chunks.json"}),
        (["--output_format", "html"], {"document.html"}),
    ],
)
def test_selected_exports(
    file_cli, temp_doc, tmp_path, extraction_service, flags, expected
):
    destination = tmp_path / "exports"
    result = file_cli.invoke(
        convert.convert_cli,
        [
            temp_doc.name,
            str(destination),
            "--page_range",
            "1",
            "--disable_image_extraction",
            *flags,
        ],
    )
    assert result.exit_code == 0, result.output
    assert extraction_service.call_count == 1
    assert {
        p.relative_to(destination).as_posix()
        for p in destination.rglob("*")
        if p.is_file()
    } == expected
    for name in expected:
        if name.endswith(".json"):
            assert json.loads((destination / name).read_text())


def test_all_matches_gui_and_zip(
    file_cli, temp_doc, tmp_path, model_dict, extraction_service
):
    destination = tmp_path / "all"
    result = file_cli.invoke(
        convert.convert_cli, [temp_doc.name, str(destination), "--all"]
    )
    assert result.exit_code == 0, result.output
    assert extraction_service.call_count == 2
    with ZipFile(destination / "document.zip") as archive:
        names = set(archive.namelist())
        assert {
            "document.md",
            "document.html",
            "document.json",
            "chunks.json",
            "metadata.json",
            "annotated.pdf",
            "annotations/page-1.png",
            "annotations/page-2.png",
        } <= names
        for name in names:
            assert archive.read(name) == (destination / name).read_bytes()
        assert not any(
            name.endswith(".pdf") and name != "annotated.pdf" for name in names
        )
    assert (destination / "annotated.pdf").read_bytes().startswith(b"%PDF")
    gui = run_document(
        prepare_upload(Path(temp_doc.name).read_bytes(), "document.pdf"), {}, model_dict
    )
    assert (destination / "document.md").read_text(encoding="utf-8") == gui["markdown"]
    assert (destination / "document.html").read_text(encoding="utf-8") == markdown_html(
        gui["markdown"], gui["images"]
    )


def test_zip_only(file_cli, temp_doc, tmp_path, extraction_service):
    destination = tmp_path / "archive"
    result = file_cli.invoke(
        convert.convert_cli, [temp_doc.name, str(destination), "--zip"]
    )
    assert result.exit_code == 0, result.output
    assert {p.name for p in destination.iterdir()} == {"document.zip"}
    assert extraction_service.call_count == 2
    with ZipFile(destination / "document.zip") as archive:
        assert "document.html" in archive.namelist()
        assert "annotations/page-2.png" in archive.namelist()


def test_markdown_and_image_crops(file_cli, temp_doc, tmp_path):
    destination = tmp_path / "markdown"
    result = file_cli.invoke(convert.convert_cli, [temp_doc.name, str(destination)])
    assert result.exit_code == 0, result.output
    images = {
        p.name for p in destination.iterdir() if p.suffix in (".jpeg", ".jpg", ".png")
    }
    assert images
    assert all(
        name in (destination / "document.md").read_text(encoding="utf-8")
        for name in images
    )
    image_dir = tmp_path / "images"
    result = file_cli.invoke(
        convert.convert_cli, [temp_doc.name, str(image_dir), "--images"]
    )
    assert result.exit_code == 0, result.output
    assert {p.name for p in image_dir.iterdir()} == images


@pytest.mark.parametrize(
    "flags",
    [
        ["--all", "--html"],
        ["--all", "--output_format", "html"],
        ["--html", "--output_format", "json"],
        ["--workers", "2"],
        ["--output_dir", "elsewhere"],
    ],
)
def test_reject_ambiguous_options(
    file_cli, temp_doc, tmp_path, extraction_service, flags
):
    result = file_cli.invoke(
        convert.convert_cli, [temp_doc.name, str(tmp_path / "new"), *flags]
    )
    assert result.exit_code == 2
    extraction_service.assert_not_called()


def test_missing_destination_and_folder_flags(
    file_cli, temp_doc, tmp_path, extraction_service
):
    for args in ([temp_doc.name], [str(tmp_path), "--all"]):
        result = file_cli.invoke(convert.convert_cli, args)
        assert result.exit_code == 2, result.output
    extraction_service.assert_not_called()


def test_output_dir_compatibility_and_overwrite(file_cli, temp_doc, tmp_path):
    destination = tmp_path / "output"
    destination.mkdir()
    (destination / "document.md").write_text("old")
    (destination / "notes.txt").write_text("keep")
    result = file_cli.invoke(
        convert.convert_cli, [temp_doc.name, "--output_dir", str(destination)]
    )
    assert result.exit_code == 0, result.output
    assert "Hello, World!" in (destination / "document.md").read_text(encoding="utf-8")
    assert (destination / "notes.txt").read_text() == "keep"


@pytest.mark.parametrize("failure", ["extraction", "export", "range"])
def test_failure_preserves_existing_output(
    file_cli, temp_doc, tmp_path, extraction_service, monkeypatch, failure
):
    destination = tmp_path / "old"
    destination.mkdir()
    previous = destination / "document.md"
    previous.write_text("keep")
    flags = []
    if failure == "extraction":
        extraction_service.side_effect = ExtractionError("incomplete")
    elif failure == "export":
        monkeypatch.setattr(
            "doclayout.exports.document_exports",
            Mock(side_effect=ValueError("cannot export")),
        )
    else:
        flags = ["--page_range", "99"]
    result = file_cli.invoke(
        convert.convert_cli, [temp_doc.name, str(destination), *flags]
    )
    assert result.exit_code != 0
    assert previous.read_text() == "keep"


def test_missing_credentials(temp_doc, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = CliRunner().invoke(
        convert.convert_cli, [temp_doc.name, str(tmp_path / "new")]
    )
    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.output
    assert not (tmp_path / "new").exists()


def test_input_collision_before_extraction(
    file_cli, temp_doc, tmp_path, extraction_service
):
    source = tmp_path / "annotated.pdf"
    content = Path(temp_doc.name).read_bytes()
    source.write_bytes(content)
    result = file_cli.invoke(
        convert.convert_cli, [str(source), str(tmp_path), "--annotated-pdf"]
    )
    assert result.exit_code == 1
    assert "overwrite the input" in result.output
    assert source.read_bytes() == content
    extraction_service.assert_not_called()


def test_validate_all_paths_before_writing(temp_doc, tmp_path):
    destination = tmp_path / "outputs"
    destination.mkdir()
    previous = destination / "document.md"
    previous.write_bytes(b"keep")
    with pytest.raises(ValueError, match="Unsafe"):
        save_document_exports(
            {"document.md": b"new", "../outside.md": b"outside"},
            destination,
            temp_doc.name,
        )
    assert previous.read_bytes() == b"keep"


def test_gui_launcher_uses_environment_and_exit_code(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["doclayout_gui", "--page_range", "0"])
    monkeypatch.setattr(run_streamlit_app, "find_spec", lambda _: object())
    run = Mock(return_value=SimpleNamespace(returncode=7))
    monkeypatch.setattr(run_streamlit_app.subprocess, "run", run)
    with pytest.raises(SystemExit) as exit_info:
        run_streamlit_app.streamlit_app_cli()
    assert exit_info.value.code == 7
    args = run.call_args.args[0]
    assert args[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert args[-3:] == ["--", "--page_range", "0"]


def test_gui_launcher_missing_extra(monkeypatch):
    monkeypatch.setattr(run_streamlit_app, "find_spec", lambda _: None)
    with pytest.raises(SystemExit, match="gui.*extra"):
        run_streamlit_app.streamlit_app_cli()
