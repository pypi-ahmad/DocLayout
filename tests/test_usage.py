"""Offline billing estimates, failure accounting, and run isolation."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from doclayout.converters.pdf import PdfConverter
from doclayout.schema.extraction import ExtractedPage
from doclayout.services.openai import ExtractionError, OpenAIService
from doclayout.ui.documents import prepare_upload, run_document
from doclayout.usage import cost_summary, response_usage


@pytest.mark.parametrize(
    "model,expected",
    [("gpt-6.1-sol", 14.6), ("gpt-6-sol", 14.7), ("gpt-6-luna", 0.735)],
)
def test_rates_without_double_counting_cache(model, expected):
    entry = response_usage(
        {
            "input_tokens": 3_000_000,
            "output_tokens": 1_000_000,
            "input_tokens_details": {
                "cached_tokens": 1_000_000,
                "cache_write_tokens": 1_000_000,
            },
        },
        model,
    )
    summary = cost_summary([entry])
    assert summary["estimated_cost_usd"] == pytest.approx(expected)
    assert summary["complete"]
    assert summary["cached_tokens"] == summary["cache_write_tokens"] == 1_000_000


def test_unknown_usage_is_partial_not_free():
    valid = response_usage({"input_tokens": 100, "output_tokens": 20}, "gpt-6.1-sol")
    unknown = response_usage(None, "gpt-6.1-sol")
    summary = cost_summary([valid, unknown])
    assert summary["estimated_cost_usd"] == pytest.approx(0.0004)
    assert not summary["complete"]
    assert summary["unknown_requests"] == 1


def test_invalid_counts_and_unpriced_models():
    for usage, model in [
        ({"input_tokens": True, "output_tokens": 1}, "gpt-6.1-sol"),
        (
            {
                "input_tokens": 1,
                "output_tokens": 1,
                "input_tokens_details": {"cached_tokens": 2},
            },
            "gpt-6.1-sol",
        ),
        ({"input_tokens": 1, "output_tokens": 1}, "unknown-model"),
    ]:
        assert not cost_summary([response_usage(usage, model)])["complete"]


def mock_service(monkeypatch, page_result):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    response = SimpleNamespace(
        status="completed",
        output_parsed=ExtractedPage.model_validate(page_result),
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            input_tokens_details=SimpleNamespace(
                cached_tokens=30, cache_write_tokens=20
            ),
        ),
    )
    client = Mock()
    client.with_options.return_value = client
    client.responses.parse.return_value = response
    monkeypatch.setattr("doclayout.services.openai.OpenAI", lambda **_: client)
    return OpenAIService(), client, response


def test_conversion_cost_metadata_and_isolation(monkeypatch, page_result, temp_doc):
    service, _, _ = mock_service(monkeypatch, page_result)
    first = PdfConverter({"extraction_service": service})
    second = PdfConverter({"extraction_service": service})
    output = first(temp_doc.name)
    assert output.metadata["cost"]["requests"] == 2
    assert output.metadata["cost"]["estimated_cost_usd"] == pytest.approx(0.000706)
    assert output.metadata["cost"]["complete"]
    assert len(first.extraction_service.usage) == 2
    assert second.extraction_service.usage == service.usage == []
    # Reusing the converter starts a new run rather than duplicating prior costs.
    assert first(temp_doc.name).metadata["cost"]["requests"] == 2


@pytest.mark.parametrize("page_model", ["gpt-6-luna", "gpt-6.1-sol"])
@pytest.mark.parametrize("refinement_model", ["gpt-6-luna", "gpt-6.1-sol"])
@pytest.mark.parametrize("field_model", ["gpt-6-luna", "gpt-6.1-sol"])
def test_independent_stage_models(
    monkeypatch, page_result, temp_doc, page_model, refinement_model, field_model
):
    from doclayout.fields import extract_fields, load_definition

    service, client, _ = mock_service(monkeypatch, page_result)
    converter = PdfConverter(
        {"extraction_service": service},
        processor_list=[],
        config={
            "page_model": page_model,
            "refinement_model": refinement_model,
            "use_llm": True,
        },
    )
    refinement_service = converter.llm_service
    assert isinstance(refinement_service, OpenAIService)
    assert isinstance(converter.extraction_service, OpenAIService)
    converter.processor_list = [
        Mock(
            side_effect=lambda document: refinement_service(
                "refinement",
                document.pages[0].highres_image,
                document.pages[0],
                ExtractedPage,
            )
        )
    ]
    output = converter(temp_doc.name)
    requests = client.responses.parse.call_args_list
    assert [request.kwargs["model"] for request in requests] == [
        page_model,
        page_model,
        refinement_model,
    ]
    assert all(
        request.kwargs["reasoning"] == {"effort": "medium"} for request in requests
    )
    assert output.metadata["extraction"]["model"] == page_model
    assert output.metadata["refinement"] == {"enabled": True, "model": refinement_model}
    per_request = {"gpt-6.1-sol": 0.000353, "gpt-6-luna": 0.0000178}
    assert output.metadata["cost"]["estimated_cost_usd"] == pytest.approx(
        2 * per_request[page_model] + per_request[refinement_model]
    )
    assert refinement_service.usage is converter.extraction_service.usage
    assert service.model == "gpt-6.1-sol" and service.usage == []
    isolated = PdfConverter({"extraction_service": service})
    assert isinstance(isolated.extraction_service, OpenAIService)
    assert isolated.extraction_service.usage == []
    client.responses.create.return_value = SimpleNamespace(
        status="completed",
        output=[],
        output_text='{"records":[],"document_issues":[]}',
        usage=None,
    )
    usage = []
    definition = load_definition(enabled=False, extraction_model=field_model)
    extract_fields("Raw Markdown", {}, definition, client=client, usage=usage)
    assert client.responses.create.call_count == 1
    field_request = client.responses.create.call_args.kwargs
    assert field_request["model"] == field_model
    assert field_request["reasoning"] == {"effort": "medium"}
    assert field_request["input"][1] == {"role": "user", "content": "Raw Markdown"}
    assert usage[0]["model"] == field_model


@pytest.mark.parametrize("page_model", ["gpt-6-luna", "gpt-6.1-sol"])
def test_disabled_refinement_makes_only_page_calls(
    monkeypatch, page_result, temp_doc, page_model
):
    service, client, _ = mock_service(monkeypatch, page_result)
    converter = PdfConverter(
        {"extraction_service": service},
        config={"page_model": page_model, "refinement_model": "gpt-6-luna"},
    )
    assert converter.llm_service is None
    output = converter(temp_doc.name)
    assert client.responses.parse.call_count == 2
    assert all(
        call.kwargs["model"] == page_model
        for call in client.responses.parse.call_args_list
    )
    assert output.metadata["refinement"] == {"enabled": False, "model": None}


def test_failed_run_retains_reported_cost(monkeypatch, page_result, temp_doc):
    service, _, response = mock_service(monkeypatch, page_result)
    response.status = "incomplete"
    ledger = []
    upload = prepare_upload(Path(temp_doc.name).read_bytes(), "sample.pdf")
    with pytest.raises(ExtractionError):
        run_document(
            upload, {"page_range": "0"}, {"extraction_service": service}, ledger
        )
    assert cost_summary(ledger)["estimated_cost_usd"] == pytest.approx(0.000353)
    assert cost_summary(ledger)["complete"]


def test_transport_failure_marks_unknown_request(monkeypatch, page_result):
    service, client, _ = mock_service(monkeypatch, page_result)
    client.responses.parse.side_effect = TimeoutError("no usage")
    with pytest.raises(ExtractionError):
        service("prompt", None, None, ExtractedPage)
    assert cost_summary(service.usage)["unknown_requests"] == 1


@pytest.mark.parametrize("historical", [False, True])
def test_cost_panel_retains_total_across_reruns(historical):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string("""
import streamlit as st
from doclayout.ui.costs import show_costs
from doclayout.usage import response_usage
entries = st.session_state.setdefault("usage", [
    response_usage({"input_tokens": 1000000, "output_tokens": 0}, "gpt-6.1-sol"),
    response_usage({"input_tokens": 0, "output_tokens": 1000000}, "gpt-6-luna"),
])
st.button("Rerun")
show_costs(st.sidebar.empty(), entries)
""")
    if historical:
        app.session_state["usage"] = [
            response_usage(
                {"input_tokens": 1000000, "output_tokens": 0}, "gpt-6.1-sol"
            ),
            response_usage({"input_tokens": 0, "output_tokens": 1000000}, "gpt-6-luna"),
            response_usage(
                {
                    "input_tokens": 1000000,
                    "output_tokens": 0,
                    "input_tokens_details": {"cached_tokens": 1000000},
                },
                "gpt-6-sol",
            ),
        ]
    app.run()
    assert not app.exception
    expected = "$2.700000" if historical else "$2.500000"
    assert app.metric[0].value == expected
    labels = [element.value for element in app.markdown]
    assert "GPT-6.1 Sol: $2.000000" in labels
    assert ("GPT-6 Sol (historical): $0.200000" in labels) == historical
    app.button[0].click().run()
    assert app.metric[0].value == expected
