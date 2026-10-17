"""OpenRouter client for optional Tamagodji personality responses."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class BrainReply:
    """Validated output from the language model."""

    reply: str
    action: str | None = None


class OpenRouterBrain:
    """Call OpenRouter while keeping state changes in the deterministic app."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o-mini",
        endpoint: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout: float = 20.0,
    ) -> None:
        """Create a client with a secret that must remain on the Pi."""

        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "OpenRouterBrain | None":
        """Create a brain only when an API key is configured."""

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(api_key, model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))

    def respond(self, message: str, state: dict[str, object]) -> BrainReply:
        """Return a short personality reply and one optional safe action."""

        request_body = {
            "model": self.model,
            "temperature": 0.7,
            "max_tokens": 120,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Tamagodji, a tiny friendly virtual pet. Be warm and concise. "
                        "Return only JSON with keys reply and action. reply must be at most 180 "
                        "characters. action must be exactly FEED, PLAY, or NONE. Never invent "
                        "other actions and never claim to control hardware. Current pet state: "
                        f"{json.dumps(state, separators=(',', ':'))}"
                    ),
                },
                {"role": "user", "content": message},
            ],
        }
        request = Request(
            self.endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError("OpenRouter request failed") from error
        content = self._content_from_response(payload)
        return self._parse_reply(content)

    @staticmethod
    def _content_from_response(payload: Any) -> str:
        """Extract assistant text from an OpenAI-compatible response."""

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("OpenRouter response did not contain assistant content") from error
        if not isinstance(content, str):
            raise RuntimeError("OpenRouter assistant content was not text")
        return content.strip()

    @staticmethod
    def _parse_reply(content: str) -> BrainReply:
        """Parse and constrain the model's structured response."""

        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            return BrainReply(reply=content[:180], action=None)
        if not isinstance(value, dict):
            return BrainReply(reply=content[:180], action=None)
        reply = str(value.get("reply", "")).strip()[:180]
        action = str(value.get("action", "NONE")).upper()
        return BrainReply(reply=reply, action=action if action in {"FEED", "PLAY"} else None)
