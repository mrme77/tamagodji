"""Bounded handoff from HTTP workers to the hardware loop."""

from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue

from .events import Event


@dataclass(frozen=True)
class ChatCommand:
    """Keep a model reply and its optional action in one atomic queue slot."""

    message: str
    event: Event | None = None


class CommandQueue:
    """Keep a finite backlog and reserve loop time for physical sensors."""

    def __init__(self, capacity: int = 16) -> None:
        """Allocate a bounded queue; overflow raises queue.Full immediately."""

        if capacity < 1:
            raise ValueError("Command capacity must be positive")
        self._queue: Queue[Event | str | ChatCommand] = Queue(maxsize=capacity)

    def put(self, command: Event | str) -> None:
        """Submit one command without blocking an HTTP worker."""

        self._queue.put_nowait(command)

    def put_chat(self, message: str, event: Event | None) -> None:
        """Accept all of a chat result or none, so a busy response cannot hide an action."""

        self._queue.put_nowait(ChatCommand(message=message, event=event))

    def drain(
        self, on_event: Callable[[Event], None], on_message: Callable[[str], None], limit: int = 4
    ) -> None:
        """Process at most limit commands before returning to sensor polling."""

        if limit < 1:
            raise ValueError("Drain limit must be positive")
        for _ in range(limit):
            try:
                command = self._queue.get_nowait()
            except Empty:
                return
            if isinstance(command, Event):
                on_event(command)
            elif isinstance(command, ChatCommand):
                if command.event is not None:
                    on_event(command.event)
                if command.message:
                    on_message(command.message)
            else:
                on_message(command)
