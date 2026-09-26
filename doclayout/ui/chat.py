"""Document-only chat: structured draft, source checks, then independent verification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from doclayout.credentials import CredentialsError, openai_credentials

CHAT_MODEL = "gpt-6-luna"

PROMPTS = {
    name: files("doclayout")
    .joinpath("prompts")
    .joinpath(f"{name}.md")
    .read_text(encoding="utf-8")
    for name in ("chat-answer", "chat-verify")
}

MAX_QUESTION = 2000
MAX_CONTEXT_BYTES = 200_000
OUT_OF_SCOPE = "I can only answer questions about this document."
NOT_FOUND = "That information is not in the parsed pages."
UNVERIFIED = "I couldn't verify an answer from the parsed pages."
UNAVAILABLE = "Document chat is temporarily unavailable."


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page: int
    quote: str


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str
    evidence: list[Evidence]


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["answer", "not_found", "out_of_scope"]
    statements: list[Statement]


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    approved: bool


@dataclass
class ChatResult:
    """Safe displayed answer/status strings, usage records, and stage diagnostics."""
    answer: str
    status: str
    usage: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)


def _token_count(value):
    return value if isinstance(value, int) and value >= 0 else None


def _payload(messages: list[dict], schema: type[BaseModel]) -> dict:
    payload = {
        "model": CHAT_MODEL,
        "reasoning": {"effort": "medium"},
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema.__name__,
                "strict": True,
                "schema": schema.model_json_schema(),
            }
        },
        "store": False,
        "max_output_tokens": 8192,
    }
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("context_limit")
    return payload


def _call(client, schema, prompt_name, data, result):
    messages = [
        {"role": "system", "content": PROMPTS[prompt_name]},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
    ]
    payload = _payload(messages, schema)
    metadata = None
    known = False
    diagnostic = {"stage": prompt_name, "status": "failed"}
    try:
        response = client.responses.create(**payload)
        diagnostic["request_id"] = None
        diagnostic["model"] = CHAT_MODEL
        data = response.model_dump()
        counts = data.get("usage") or {}
        inp, out = (
            _token_count(counts.get("input_tokens")),
            _token_count(counts.get("output_tokens")),
        )
        known = inp is not None and out is not None
        details = counts.get("input_tokens_details") or {}
        metadata = {
            "input_tokens": inp,
            "output_tokens": out,
            "input_token_details": {
                "cache_read": _token_count(details.get("cached_tokens")),
                "cache_write": _token_count(details.get("cache_write_tokens")),
            },
        }
        if data.get("status") != "completed":
            raise ValueError("incomplete")
        output = data.get("output") or []
        if any(item.get("type") not in ("message", "reasoning") for item in output):
            raise ValueError("unexpected_output")
        if any(
            part.get("type") != "output_text"
            for item in output
            if item.get("type") == "message"
            for part in item.get("content", [])
        ):
            raise ValueError("refused")
        parsed = schema.model_validate_json(response.output_text)
        diagnostic["status"] = "validated"
        return parsed
    finally:
        result.usage.append(
            {
                "stage": prompt_name,
                "model": CHAT_MODEL,
                "known": known,
                "tokens": metadata,
            }
        )
        result.diagnostics.append(diagnostic)


def _normalize(text):
    return " ".join(text.split())


def _validated_text(draft: Draft, pages: dict[int, str]) -> str:
    if not draft.statements or len(draft.statements) > 12:
        raise ValueError("empty_or_long_answer")
    rendered = []
    for statement in draft.statements:
        text = statement.text.strip()
        if not text or re.search(
            r"[\r\n]|^#|```|<[^>]+>|!?\[[^\]]*\]\(|https?://", text
        ):
            raise ValueError("invalid_style")
        if not statement.evidence or len(statement.evidence) > 12:
            raise ValueError("missing_evidence")
        for evidence in statement.evidence:
            quote = _normalize(evidence.quote)
            if (
                not quote
                or evidence.page not in pages
                or quote not in _normalize(pages[evidence.page])
            ):
                raise ValueError("invalid_evidence")
        refs = ", ".join(str(p) for p in sorted({e.page for e in statement.evidence}))
        rendered.append(f"{text} (p. {refs})")
    answer = " ".join(rendered)
    if len(answer.split()) > 120 or len(answer) > 2000:
        raise ValueError("answer_limit")
    return answer


def answer_document_question(
    pages: dict[int, str], question, history=(), *, client=None
) -> ChatResult:
    """Answer from parsed pages after quote checks and independent verification.

    Args:
        pages (dict[int, str]): Original page numbers mapped to parsed text.
        question (str): Nonempty document question, at most 2,000 characters.
        history (Iterable[dict]): Prior turns; only six latest answered turns are used.
        client (OpenAI | None): Borrowed client, or None to create and close one.

    Returns:
        ChatResult: Accepted answer or safe refusal/error status with reported
        usage. An accepted answer requires two Luna/medium requests. Invalid
        input and oversized context return before either paid request.
    """
    result = ChatResult(UNVERIFIED, "blocked")
    if not pages:
        return ChatResult("Parse document pages before using chat.", "no_document")
    if (
        not isinstance(question, str)
        or not question.strip()
        or len(question) > MAX_QUESTION
    ):
        return ChatResult(
            "Enter a document question of 1–2,000 characters.", "invalid_question"
        )
    recent = [
        {"question": turn["question"], "answer": turn["answer"]}
        for turn in history
        if turn.get("status") == "answered"
    ][-6:]
    data = {
        "pages": [{"page": p, "text": t} for p, t in sorted(pages.items())],
        "question": question,
        "history": recent,
    }
    owned = client is None
    try:
        # Reserve room for the verification candidate before either paid request.
        if (
            len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            > MAX_CONTEXT_BYTES - 30_000
        ):
            return ChatResult(
                "Parsed text is too large for chat. Parse a smaller page range.",
                "context_limit",
            )
        if owned:
            try:
                credentials = openai_credentials()
            except CredentialsError as exc:
                return ChatResult(str(exc), "configuration_error")
            client = OpenAI(
                **credentials,
                max_retries=0,
                timeout=60,
            )
        draft = _call(client, Draft, "chat-answer", data, result)
        if draft.decision != "answer":
            if draft.statements:
                return result
            result.answer = NOT_FOUND if draft.decision == "not_found" else OUT_OF_SCOPE
            result.status = draft.decision
            return result
        try:
            answer = _validated_text(draft, pages)
        except ValueError:
            return result
        verified = _call(
            client,
            Verification,
            "chat-verify",
            {**data, "candidate": draft.model_dump()},
            result,
        )
        if verified.approved:
            result.answer, result.status = answer, "answered"
    except Exception:  # noqa: BLE001 - provider errors must not expose credentials or drafts
        # Never expose provider errors, raw completions, or rejected candidates.
        result.answer, result.status = UNAVAILABLE, "error"
    finally:
        if owned and client is not None:
            client.close()
    return result
