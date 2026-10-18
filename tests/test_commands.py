"""Regression checks for bounded work in the main hardware loop."""

from queue import Full

import pytest

from tamagodji.commands import CommandQueue
from tamagodji.events import Event, EventKind


def test_drains_only_budget_and_preserves_order() -> None:
    """An API backlog cannot monopolize a sensor iteration."""

    queue = CommandQueue()
    event = Event(EventKind.FEED)
    for command in [event, "hello", "later"]:
        queue.put(command)
    received: list[Event | str] = []
    queue.drain(received.append, received.append, limit=2)
    assert received == [event, "hello"]
    queue.drain(received.append, received.append)
    assert received == [event, "hello", "later"]
    queue.drain(received.append, received.append)
    assert len(received) == 3


def test_queue_overflow_is_immediate_and_recovers_after_drain() -> None:
    """Full is visible to HTTP instead of blocking a request indefinitely."""

    queue = CommandQueue(capacity=1)
    queue.put("first")
    with pytest.raises(Full):
        queue.put("overflow")
    queue.drain(lambda event: None, lambda message: None)
    queue.put("recovered")


def test_rejects_unbounded_capacity_and_invalid_budget() -> None:
    """Queue(maxsize=0) must not accidentally disable bounds."""

    with pytest.raises(ValueError):
        CommandQueue(capacity=0)
    with pytest.raises(ValueError):
        CommandQueue().drain(lambda event: None, lambda message: None, limit=0)


def test_chat_reply_and_action_use_one_atomic_queue_slot() -> None:
    """A saturated queue must not accept an action and then reject its reply."""

    queue = CommandQueue(capacity=1)
    event = Event(EventKind.FEED)
    queue.put_chat("Hello", event)
    with pytest.raises(Full):
        queue.put_chat("Rejected", Event(EventKind.PLAY))
    received: list[Event | str] = []
    queue.drain(received.append, received.append)
    assert received == [event, "Hello"]
    queue.put_chat("Just text", None)
    queue.drain(received.append, received.append)
    assert received[-1] == "Just text"
