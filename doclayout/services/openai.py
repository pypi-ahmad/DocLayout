# Modified for DocLayout; see NOTICE for a summary of changes.
"""Shared GPT-6 Sol client for extraction and optional refinement."""

from copy import copy
from importlib.resources import files
from threading import BoundedSemaphore
from typing import Annotated, ClassVar

from openai import OpenAI

from doclayout.config.validation import validate_config
from doclayout.services import BaseService
from doclayout.util import assign_config

SYSTEM_PROMPT = (
    files("doclayout")
    .joinpath("prompts")
    .joinpath("system.md")
    .read_text(encoding="utf-8")
)


class ExtractionError(RuntimeError):
    """The API did not produce a complete, validated extraction."""


class OpenAIService(BaseService):
    model: ClassVar[str] = "gpt-6-sol"
    timeout: Annotated[int, "API request timeout in seconds."] = 180
    max_output_tokens: Annotated[int, "Maximum output tokens per request."] = 32768
    _requests = BoundedSemaphore(3)

    def __init__(self, config=None):
        validate_config(config)
        super().__init__(config)
        if self.timeout <= 0 or self.max_output_tokens <= 0 or self.max_retries < 0:
            raise ValueError(
                "API timeout/output limits must be positive; retries nonnegative"
            )
        self.client = OpenAI(timeout=self.timeout, max_retries=self.max_retries)

    def configured(self, config):
        """Share the HTTP client without mutating another converter's settings."""
        validate_config(config)
        service = copy(self)
        assign_config(service, config)
        if (
            service.timeout <= 0
            or service.max_output_tokens <= 0
            or service.max_retries < 0
        ):
            raise ValueError("Invalid API limits")
        return service

    def process_images(self, images):
        return [
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,"
                + self.img_to_base64(image, "PNG"),
                "detail": "auto",
            }
            for image in images
        ]

    def __call__(
        self, prompt, image, block, response_schema, max_retries=None, timeout=None
    ):
        client = self.client.with_options(
            timeout=self.timeout if timeout is None else timeout,
            max_retries=self.max_retries if max_retries is None else max_retries,
        )
        if block is not None:
            block.update_metadata(llm_request_count=1)
        try:
            with self._requests:
                response = client.responses.parse(
                    model="gpt-6-sol",
                    input=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                *self.format_image_for_llm(image),
                            ],
                        },
                    ],
                    text_format=response_schema,
                    reasoning={"effort": "medium"},
                    max_output_tokens=self.max_output_tokens,
                    store=False,
                )
            if block is not None and response.usage is not None:
                block.update_metadata(llm_tokens_used=response.usage.total_tokens)
            if response.status != "completed" or response.output_parsed is None:
                raise ExtractionError(
                    f"GPT-6 Sol returned {response.status} without a complete parsed result (refusal or output limit)"
                )
            return response.output_parsed.model_dump()
        except Exception as exc:
            if block is not None:
                block.update_metadata(llm_error_count=1)
            if isinstance(exc, ExtractionError):
                raise
            raise ExtractionError(
                f"GPT-6 Sol request failed: {type(exc).__name__}"
            ) from None

    def close(self):
        self.client.close()
