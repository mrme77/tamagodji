"""Tests for the optional OpenRouter Tamagodji brain."""

import json
from io import BytesIO
from unittest.mock import patch
import pytest

from tamagodji.llm.openrouter import OpenRouterBrain


class FakeResponse(BytesIO):
    """Minimal context-manager response used by the HTTP client test."""

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_openrouter_reply_is_constrained_to_safe_actions() -> None:
    """A model cannot introduce an unsupported state-changing command."""

    payload = {"choices": [{"message": {"content": '{"reply":"Yum!","action":"DELETE"}'}}]}
    with patch(
        "tamagodji.llm.openrouter.urlopen",
        return_value=FakeResponse(json.dumps(payload).encode("utf-8")),
    ):
        result = OpenRouterBrain("test-key").respond("I fed you", {"mood": "happy"})

    assert result.reply == "Yum!"
    assert result.action is None


def test_openrouter_plain_text_has_no_action() -> None:
    """An unexpected non-JSON model response remains displayable but inert."""

    result = OpenRouterBrain._parse_reply("Hello from Tamagodji")
    assert result.reply == "Hello from Tamagodji"
    assert result.action is None


def test_openrouter_rejects_oversized_response() -> None:
    """A remote response cannot be read into unbounded memory."""

    with patch("tamagodji.llm.openrouter.urlopen", return_value=FakeResponse(b"x" * 65537)):
        with pytest.raises(RuntimeError, match="size limit"):
            OpenRouterBrain("test-key").respond("Hi", {})


def test_openrouter_wraps_invalid_json_response() -> None:
    """Invalid JSON remains a controlled upstream failure, not a handler crash."""

    with patch("tamagodji.llm.openrouter.urlopen", return_value=FakeResponse(b"not-json")):
        with pytest.raises(RuntimeError, match="request failed"):
            OpenRouterBrain("test-key").respond("Hi", {})
