"""Preserve the chat prompt text when relocating it to package resources."""

import hashlib

from doclayout.ui.chat import PROMPTS


def test_chat_prompts_match_original_text():
    # Captured from the original Python string literals before migration.
    expected = {
        "chat-answer": "3cce3f757c2a72e428429325e4e4c362c2e19ea9c518778ece4d09f8e33f1cf1",
        "chat-verify": "9d18ad5e3d376a7300fcd99db75408bf87c3f81fe04fc2e7a9313070d6ac2505",
    }
    assert {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for name, text in PROMPTS.items()
    } == expected
