"""Offline checks for readable extraction results and preserved saved values."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from doclayout.ui.field_summary import (
    display_value,
    field_label,
    request_label,
    saved_result_label,
    status_label,
    summary_sections,
)


def test_summary_preserves_values_and_hides_only_missing():
    fields = {
        "member": {"first_name": "Alex", "member_id": "00123", "date_of_birth": None},
        "expedited_requested": False,
        "requested_services": [
            {
                "code": "00100",
                "code_system": "CPT",
                "modifiers": ["AA", "QX"],
                "requested_units_or_visits": "0",
            },
            {"code": "99213", "code_system": None, "frequency": "Weekly"},
        ],
        "diagnoses": [{"code": "Z00.00", "code_system": "ICD-10", "description": None}],
        "additional_information": None,
        "legacy_count": 0,
    }
    original = deepcopy(fields)
    sections = {title: rows for title, rows, _ in summary_sections(fields)}
    assert sections["Member"] == {"First name": "Alex", "Member ID": "00123"}
    assert sections["Priority"] == {"Expedited request": "No"}
    assert sections["Legacy count"] == {"Legacy count": "0"}
    assert sections["Requested services"][0]["Code"] == "00100"
    assert sections["Requested services"][0]["Modifiers"] == "AA; QX"
    assert sections["Requested services"][1]["Code system"] == ""
    assert "Description" not in sections["Diagnoses"][0]
    assert "Additional information" not in sections
    expanded = {title: rows for title, rows, _ in summary_sections(fields, True)}
    assert expanded["Member"]["Date of birth"] == "Not found"
    assert expanded["Referring provider"]["NPI"] == "Not found"
    assert expanded["Requested services"][1]["Code system"] == "Not found"
    assert fields == original


def test_old_and_unknown_fields_remain_readable_without_schema(monkeypatch):
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=OSError))
    fields = {
        "additional_information": "Original text",
        "old_details": {"old_id": "0007"},
        "mixed": [{"code": "01"}, "02"],
    }
    sections = {title: rows for title, rows, _ in summary_sections(fields)}
    assert sections["Old details"] == {"Old ID": "0007"}
    assert sections["Mixed"]["Mixed"] == "Code: 01; 02"
    assert summary_sections({}) == []


def test_friendly_labels_keep_acronyms_and_array_positions():
    assert field_label("/request/request_date") == "Request · Requested service date"
    assert field_label("/member/member_id") == "Member · Member ID"
    assert field_label("/requested_services/0/code") == "Requested services · 1 · Code"
    assert field_label("/servicing_provider/npi") == "Servicing provider · NPI"
    assert field_label("/a~1b/~0value") == "A/b · ~value"
    assert display_value(True) == "Yes"
    assert display_value(0) == "0"
    assert display_value([]) == "Not found"
    assert request_label({"fields": {}}, 1) == "Request 2"
    assert (
        saved_result_label(
            {
                "filename": "example.pdf",
                "created_at": "2026-09-25T12:13:14+00:00",
                "status": "needs_review",
            }
        )
        == "example.pdf · 25 Sep 2026, 12:13:14 UTC · Needs review"
    )


@pytest.fixture
def review_app(monkeypatch):
    record = {
        "id": "record-1",
        "name": "example_001",
        "status": "needs_review",
        "fields": {
            "member": {
                "first_name": "Alex",
                "member_id": "00123",
                "date_of_birth": None,
            },
            "expedited_requested": False,
        },
        "issues": [
            {"field_path": "/member/date_of_birth", "reason": "Source is unclear."}
        ],
        "evidence": [],
    }
    run = {
        "id": "run-1",
        "document_id": "doc-1",
        "filename": "example.pdf",
        "created_at": "2026-09-25T12:13:14+00:00",
        "status": "needs_review",
        "definition_version": "version-1",
        "records": [record],
        "result": {
            "classification": {"status": "disabled"},
            "usage": [],
            "document_issues": [],
        },
    }
    store = SimpleNamespace(
        runs=lambda: [run], run=lambda _: run, document=lambda _: {"id": "doc-1"}
    )
    monkeypatch.setattr("doclayout.field_store.FieldStore", lambda: store)
    definition = Mock(
        side_effect=AssertionError("Browsing must not load model configuration")
    )
    retry = Mock(side_effect=AssertionError("Browsing must not request extraction"))
    monkeypatch.setattr("doclayout.fields.load_definition", definition)
    monkeypatch.setattr("doclayout.ui.batch.retry_fields", retry)
    app = AppTest.from_file("doclayout/scripts/app_pages/review.py", default_timeout=15)
    return app, run, store, definition, retry


def test_review_summary_toggle_issues_and_multiple_requests(review_app):
    app, run, _, definition, retry = review_app
    app.run()
    assert not app.exception
    assert app.title[0].value == "Extracted information"
    assert [tab.label for tab in app.tabs] == ["Summary", "Source document"]
    assert len(app.selectbox) == 1  # Single request needs no extra selector.
    assert "00123" in [item.value for item in app.text]
    assert "No" in [item.value for item in app.text]
    assert "Not found" not in [item.value for item in app.text]
    assert "Member · Date of birth: Source is unclear." in [
        item.value for item in app.text
    ]
    assert {"More actions", "Technical details"} <= {
        item.label for item in app.expander
    }
    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert "Not found" in [item.value for item in app.text]
    second = deepcopy(run["records"][0])
    second.update(
        id="record-2", name="example_002", fields={"member": {"first_name": "Sam"}}
    )
    run["records"].append(second)
    app.run()
    app.selectbox(key="request_run-1").select_index(1).run()
    assert not app.exception
    assert "Request 2 · Sam" in [heading.value for heading in app.subheader]
    assert "00123" not in [item.value for item in app.text]
    definition.assert_not_called()
    retry.assert_not_called()


@pytest.mark.parametrize(
    "status", ["failed", "fallout", "classified_no_extraction", "needs_review"]
)
def test_review_without_records_explains_outcome(review_app, status):
    app, run, _, definition, retry = review_app
    run.update(status=status, records=[])
    run["result"]["document_issues"] = ["Saved processing explanation."]
    app.run()
    assert not app.exception
    assert status_label(status) in app.selectbox[0].options[0]
    assert "no extracted requests" in app.info[0].value
    assert "Saved processing explanation." in [item.value for item in app.text]
    assert not app.tabs
    definition.assert_not_called()
    retry.assert_not_called()


def test_review_empty_store(review_app):
    app, _, store, _, _ = review_app
    store.runs = list
    app.run()
    assert not app.exception
    assert "Process documents" in app.info[0].value


@pytest.mark.parametrize(
    "run_id,saved_document,available",
    [
        (None, "doc-1", False),
        ("missing-run", "doc-1", False),
        ("run-1", "another-document", False),
        ("run-1", "doc-1", True),
    ],
)
def test_result_button_requires_matching_saved_run(
    monkeypatch, temp_doc, run_id, saved_document, available
):
    store = SimpleNamespace(
        document=lambda _: {"id": "doc-1"},
        runs=lambda: [{"id": "run-1", "document_id": saved_document}],
    )
    monkeypatch.setattr("doclayout.field_store.FieldStore", lambda: store)
    app = AppTest.from_file(
        "doclayout/scripts/streamlit_app.py", default_timeout=15
    ).run()
    app.file_uploader[0].set_value(
        [("source.pdf", Path(temp_doc.name).read_bytes(), "application/pdf")]
    ).run()
    upload = app.session_state["upload"]
    monkeypatch.setattr("doclayout.ui.batch.load_conversion", lambda *_: (upload, None))
    app.session_state["batch_receipts"] = [
        {
            "document_id": "doc-1",
            "filename": "source.pdf",
            "status": "failed",
            "run_id": run_id,
        }
    ]
    app.run()
    assert not app.exception
    assert any(b.label == "View extracted information" for b in app.button) == available
    if not available:
        assert any("No saved extraction" in item.value for item in app.info)
