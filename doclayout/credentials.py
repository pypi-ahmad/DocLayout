"""Resolve API credentials without changing the process environment."""

import os
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class CredentialsError(ValueError):
    """A configuration error safe to display without credential values."""


def api_configuration():
    """Caller credentials, with the same explicit-empty precedence as OpenAI."""
    names = ("DOCLAYOUT_API_TOKEN", "DOCLAYOUT_INPUT_ROOT")
    values = {}
    if any(name not in os.environ for name in names):
        try:
            values = dotenv_values(
                Path.cwd() / ".env", encoding="utf-8-sig", interpolate=False
            )
        except (OSError, UnicodeError):
            raise CredentialsError("Could not read API configuration.") from None
    token, root = (
        (os.environ[name] if name in os.environ else values.get(name)) or ""
        for name in names
    )
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise CredentialsError(
            "DOCLAYOUT_API_TOKEN must contain at least 32 non-whitespace ASCII characters."
        )
    input_root = None
    if root:
        try:
            input_root = Path(root).resolve(strict=True)
            if not input_root.is_dir() or input_root == Path(input_root.anchor):
                raise ValueError
        except (OSError, ValueError):
            raise CredentialsError(
                "DOCLAYOUT_INPUT_ROOT must be an existing dedicated directory."
            ) from None
    return token, input_root


def openai_credentials() -> dict[str, str]:
    names = ("OPENAI_API_KEY", "OPENAI_BASE_URL")
    values = {}
    if any(name not in os.environ for name in names):
        try:
            values = dotenv_values(
                Path.cwd() / ".env", encoding="utf-8-sig", interpolate=False
            )
        except (OSError, UnicodeError):
            raise CredentialsError(
                "Could not read .env in the launch folder."
            ) from None

    key, base_url = (
        (os.environ[name] if name in os.environ else values.get(name)) or ""
        for name in names
    )
    if not key.strip():
        raise CredentialsError(
            "OPENAI_API_KEY is not set. Configure it in the environment or the launch folder's .env file."
        )
    return {"api_key": key.strip(), "base_url": base_url.strip() or DEFAULT_BASE_URL}
