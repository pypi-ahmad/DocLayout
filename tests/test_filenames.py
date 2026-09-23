"""Source-based filenames and compatibility with retained CLI outputs."""

import re
from datetime import datetime, timezone

from doclayout.converters.pdf import PdfConverter
from doclayout.filenames import export_basename
from doclayout.output import output_exists, save_output


def test_timestamp_explicitly_uses_utc_seconds(monkeypatch):
    class FixedClock:
        @staticmethod
        def now(tz):
            assert tz is timezone.utc
            return datetime(2026, 9, 23, 15, 30, 45, 987654, tzinfo=tz)

    monkeypatch.setattr("doclayout.filenames.datetime", FixedClock)
    assert export_basename("invoice.pdf") == "invoice_20260923_153045"


def test_filename_uses_original_stem_and_safe_utc_timestamp():
    base = export_basename(r"C:\uploads\résumé draft.v2.pdf")
    assert re.fullmatch(r"résumé_draft\.v2_\d{8}_\d{6}", base)
    assert len(export_basename("a" * 250 + ".pdf")) == 156


def test_legacy_save_names_and_crop_links(tmp_path, model_dict, temp_doc):
    rendered = PdfConverter(model_dict)(temp_doc.name)
    save_output(rendered, str(tmp_path), "annual report.v2")
    markdown = next(tmp_path.glob("*.md"))
    base = markdown.stem
    assert re.fullmatch(r"annual_report\.v2_\d{8}_\d{6}", base)
    assert (tmp_path / f"{base}_metadata.json").exists()
    crops = list(tmp_path.glob("*.jpeg"))
    assert crops
    for crop in crops:
        assert crop.name.startswith(base + "_")
        assert crop.name in markdown.read_text(encoding="utf-8")
    assert output_exists(str(tmp_path), "annual report.v2")
    assert not output_exists(str(tmp_path), "another report")


def test_skip_existing_ignores_metadata_only_and_accepts_old_outputs(tmp_path):
    (tmp_path / "report_20260923_143052_metadata.json").write_text("{}")
    assert not output_exists(str(tmp_path), "report")
    (tmp_path / "report.md").write_text("previous version")
    assert output_exists(str(tmp_path), "report")
