import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from pydantic import BaseModel

from doclayout.converters.pdf import PdfConverter
from doclayout.services.openai import ExtractionError, OpenAIService


class Result(BaseModel):
    text: str


def test_sdk_reads_process_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    instance = OpenAIService()
    try:
        assert str(instance.client.base_url) == "https://example.invalid/v1/"
        assert instance.client.api_key == "test-key"
    finally:
        instance.close()


def service(monkeypatch, response):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    client = Mock()
    client.with_options.return_value = client
    client.responses.parse.return_value = response
    factory = Mock(return_value=client)
    monkeypatch.setattr("doclayout.services.openai.OpenAI", factory)
    return OpenAIService(), client, factory


def test_responses_contract(monkeypatch):
    response = SimpleNamespace(
        status="completed", output_parsed=Result(text="hello"), usage=None
    )
    instance, client, factory = service(monkeypatch, response)
    assert instance("read", Image.new("RGB", (10, 10)), None, Result) == {
        "text": "hello"
    }
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["model"] == "gpt-6-sol"
    assert kwargs["text_format"] is Result
    assert kwargs["store"] is False
    assert kwargs["reasoning"] == {"effort": "medium"}
    # Original inline system prompt fingerprint, captured before moving the text.
    assert kwargs["input"][0]["role"] == "system"
    assert hashlib.sha256(
        kwargs["input"][0]["content"].encode("utf-8")
    ).hexdigest() == (
        "877e99bf83095f25fd037bc6f35db33edef803bd11ac3e6a25e6d157409e605d"
    )
    assert kwargs["input"][1]["content"][1]["type"] == "input_image"
    assert factory.call_args.kwargs["api_key"] == "test-key"
    assert factory.call_args.kwargs["base_url"] == "https://example.invalid/v1"


@pytest.mark.parametrize(
    "status,parsed", [("incomplete", None), ("completed", None), ("failed", None)]
)
def test_refusal_incomplete(monkeypatch, status, parsed):
    instance, _, _ = service(
        monkeypatch, SimpleNamespace(status=status, output_parsed=parsed, usage=None)
    )
    with pytest.raises(ExtractionError):
        instance("read", None, None, Result)


def test_error_metadata(monkeypatch, pdf_document):
    instance, client, _ = service(monkeypatch, None)
    client.responses.parse.side_effect = TimeoutError("secret response body")
    page = pdf_document.pages[0]
    with pytest.raises(ExtractionError, match="TimeoutError") as error:
        instance("read", None, page, Result)
    assert "secret" not in str(error.value)
    assert page.metadata.llm_error_count == 1


def test_refinement_opt_in(model_dict):
    first = PdfConverter(model_dict)
    second = PdfConverter(model_dict, config={"use_llm": True})
    assert first.llm_service is None
    assert second.llm_service is model_dict["extraction_service"]
    assert "llm_service" not in model_dict


def test_limits_are_per_converter(monkeypatch):
    instance, _, _ = service(monkeypatch, None)
    other = instance.configured({"timeout": 10, "max_output_tokens": 2048})
    assert other.timeout == 10 and other.max_output_tokens == 2048
    assert instance.timeout == 180
