"""Credential discovery uses launch-folder files and never changes environment."""

import os
from unittest.mock import Mock

import pytest

from doclayout.credentials import DEFAULT_BASE_URL, CredentialsError, openai_credentials
from doclayout.services.openai import OpenAIService
from doclayout.ui.chat import answer_document_question


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def test_dotenv_only_and_no_environment_mutation(tmp_path):
    (tmp_path / ".env").write_text(
        '\ufeffOPENAI_API_KEY="file-key-${LITERAL}"\n'
        'OPENAI_BASE_URL="https://file.invalid/v1"\nUNRELATED=value\n',
        encoding="utf-8",
    )
    before = dict(os.environ)
    assert openai_credentials() == {
        "api_key": "file-key-${LITERAL}",
        "base_url": "https://file.invalid/v1",
    }
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "environment",
    [
        {"OPENAI_API_KEY": "environment-key"},
        {"OPENAI_BASE_URL": "https://environment.invalid/v1"},
        {
            "OPENAI_API_KEY": "environment-key",
            "OPENAI_BASE_URL": "https://environment.invalid/v1",
        },
    ],
)
def test_environment_wins_per_variable(tmp_path, monkeypatch, environment):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=file-key\nOPENAI_BASE_URL=https://file.invalid/v1\n"
    )
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    result = openai_credentials()
    assert result["api_key"] == environment.get("OPENAI_API_KEY", "file-key")
    assert result["base_url"] == environment.get(
        "OPENAI_BASE_URL", "https://file.invalid/v1"
    )


@pytest.mark.parametrize("key", ["", "   "])
def test_empty_environment_key_blocks_file_fallback(tmp_path, monkeypatch, key):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=file-key\n")
    monkeypatch.setenv("OPENAI_API_KEY", key)
    with pytest.raises(CredentialsError, match="OPENAI_API_KEY") as error:
        openai_credentials()
    assert "file-key" not in str(error.value)


def test_no_parent_search_or_local_env_credentials(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=parent-key\n")
    child = tmp_path / "launch"
    child.mkdir()
    (child / "local.env").write_text("OPENAI_API_KEY=legacy-key\n")
    monkeypatch.chdir(child)
    with pytest.raises(CredentialsError, match="OPENAI_API_KEY"):
        openai_credentials()


@pytest.mark.parametrize("url", [None, "", "   "])
def test_optional_url_default(tmp_path, monkeypatch, url):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    if url is not None:
        (tmp_path / ".env").write_text("OPENAI_BASE_URL=https://file.invalid/v1\n")
        monkeypatch.setenv("OPENAI_BASE_URL", url)
    service = OpenAIService()
    try:
        assert str(service.client.base_url).rstrip("/") == DEFAULT_BASE_URL
    finally:
        service.close()


def test_extraction_and_chat_share_dotenv_resolution(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=file-key\nOPENAI_BASE_URL=https://file.invalid/v1\n"
    )
    extraction = Mock()
    chat = Mock()
    monkeypatch.setattr("doclayout.services.openai.OpenAI", extraction)
    monkeypatch.setattr("doclayout.ui.chat.OpenAI", chat)
    OpenAIService().close()
    answer_document_question({1: "Sample text."}, "What does it say?")
    for factory in (extraction, chat):
        assert factory.call_args.kwargs["api_key"] == "file-key"
        assert factory.call_args.kwargs["base_url"] == "https://file.invalid/v1"


def test_missing_chat_key_is_clear_configuration_error():
    answer = answer_document_question({1: "Text."}, "What does it say?")
    assert answer.status == "configuration_error"
    assert "OPENAI_API_KEY" in answer.answer
    assert not answer.usage


def test_client_initialization_error_does_not_expose_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-sensitive-value")
    monkeypatch.setattr(
        "doclayout.services.openai.OpenAI",
        Mock(side_effect=ValueError("dummy-sensitive-value")),
    )
    with pytest.raises(CredentialsError) as error:
        OpenAIService()
    assert "dummy-sensitive-value" not in str(error.value)
