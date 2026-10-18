"""Local-only API abuse and validation regression tests; no external requests."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
import json
from queue import Queue
from unittest.mock import Mock

import pytest

from tamagodji.api import ApiConfig, ApiServer
from tamagodji.commands import CommandQueue
from tamagodji.events import Event
from tamagodji.llm.openrouter import BrainReply


@contextmanager
def running_api(token: str | None = "test-token") -> Iterator[tuple[ApiServer, Queue[Event]]]:
    """Run an isolated listener with a small queue on an ephemeral local port."""

    events: Queue[Event] = Queue(maxsize=1)
    api = ApiServer(lambda: {"asleep": False}, events.put_nowait, ApiConfig(port=0, api_token=token))
    api.start()
    try:
        yield api, events
    finally:
        api.stop()


def request(
    api: ApiServer, body: str = '{"action":"feed"}', token: str | None = "test-token",
    path: str = "/api/interactions", content_type: str = "application/json", method: str = "POST",
) -> tuple[int, dict[str, object], dict[str, str]]:
    """Send one bounded local request and fully consume its response."""

    assert api.address is not None
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    connection = HTTPConnection(*api.address, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read()), dict(response.getheaders())
    finally:
        connection.close()


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_configuration_disables_writes_but_keeps_reads(token: str | None) -> None:
    """A tunnel to localhost cannot turn an unconfigured API into public writes."""

    with running_api(token) as (api, events):
        assert request(api)[0] == 503
        assert request(api, method="GET", path="/api/pet")[0] == 200
        assert events.empty()


@pytest.mark.parametrize("token", [None, "wrong", "test-token-extra"])
def test_invalid_credentials_never_enqueue(token: str | None) -> None:
    """Only the complete configured bearer token permits a write."""

    with running_api() as (api, events):
        assert request(api, token=token)[0] == 401
        assert events.empty()


@pytest.mark.parametrize("body", [
    "{", "[]", '{"action":1}', '{"action":"delete"}', "x" * 16385,
    '{"action":' + "1" * 5000 + "}",
])
def test_invalid_payload_is_rejected_without_consuming_action_budget(body: str) -> None:
    """Malformed input cannot change state or exhaust the valid-action token."""

    with running_api() as (api, events):
        assert request(api, body=body)[0] == 400
        assert events.empty()
        assert request(api)[0] == 202


def test_requires_json_content_type() -> None:
    """A form or text POST cannot submit commands."""

    with running_api() as (api, events):
        assert request(api, content_type="text/plain")[0] == 415
        assert events.empty()


def test_rate_limit_applies_globally_and_returns_retry_guidance() -> None:
    """New connections and a shared website token cannot bypass the cooldown."""

    with running_api() as (api, events):
        assert request(api)[0] == 202
        status, _, headers = request(api)
        assert status == 429
        assert headers["Retry-After"] == "5"
        assert headers["Cache-Control"] == "no-store"
        assert events.qsize() == 1


def test_full_queue_returns_busy_instead_of_blocking() -> None:
    """The API must not wait on a stalled hardware loop."""

    with running_api() as (api, events):
        events.put(Mock())
        assert request(api)[0] == 503
        assert events.qsize() == 1


def test_sleeping_pet_is_reported_without_queuing() -> None:
    """Direct callers receive the same sleep restriction as the website UI."""

    with running_api() as (api, events):
        api._state_provider = lambda: {"asleep": True}
        assert request(api)[0] == 409
        assert events.empty()


def test_read_burst_is_bounded() -> None:
    """Public polling has a global budget without storing IP addresses."""

    with running_api() as (api, events):
        api._reads._clock = lambda: api._reads._updated
        statuses = [request(api, method="GET", path="/api/pet")[0] for _ in range(21)]
        assert statuses == [200] * 20 + [429]
        assert events.empty()


def test_chat_calls_are_limited_before_paid_inference() -> None:
    """A repeated chat request must not start another paid model call."""

    with running_api() as (api, events):
        brain = Mock(return_value=BrainReply("Hello", "FEED"))
        api._brain = brain
        assert request(api, path="/api/chat", body='{"message":"Hi"}')[0] == 200
        assert request(api, path="/api/chat", body='{"message":"Again"}')[0] == 429
        brain.assert_called_once()
        assert events.qsize() == 1


@pytest.mark.parametrize("body", ['{"message":42}', '{"message":""}', json.dumps({"message": "x" * 501})])
def test_chat_rejects_invalid_messages_before_inference(body: str) -> None:
    """Coercing arbitrary JSON into text must not trigger a model call."""

    with running_api() as (api, _):
        brain = Mock()
        api._brain = brain
        assert request(api, path="/api/chat", body=body)[0] == 400
        brain.assert_not_called()


def test_brain_failure_is_redacted_and_releases_inference_slot() -> None:
    """Upstream error details must not leak to clients or wedge inference."""

    with running_api() as (api, _):
        api._brain = Mock(side_effect=RuntimeError("private upstream details"))
        status, body, _ = request(api, path="/api/chat", body='{"message":"Hi"}')
        assert status == 502
        assert "private" not in str(body)
        assert api._chat_slot.acquire(blocking=False)
        api._chat_slot.release()


def test_chat_queue_overflow_cannot_partially_apply_action() -> None:
    """A failed chat submission does not secretly enqueue a separate action."""

    with running_api() as (api, events):
        commands = CommandQueue(capacity=1)
        commands.put("existing")
        api._chat_sink = commands.put_chat
        api._brain = Mock(return_value=BrainReply("Hello", "FEED"))
        assert request(api, path="/api/chat", body='{"message":"Hi"}')[0] == 503
        assert events.empty()
        received: list[Event | str] = []
        commands.drain(received.append, received.append)
        assert received == ["existing"]
