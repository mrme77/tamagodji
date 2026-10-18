"""Best-effort, bounded speech that cannot pause the hardware event loop."""

from collections.abc import Callable
import logging
from queue import Empty, Full, Queue
import threading

LOGGER = logging.getLogger(__name__)


class QueuedVoice:
    """Use one audio worker and drop excess announcements instead of queuing forever."""

    def __init__(self, speak: Callable[[str], None], capacity: int = 2) -> None:
        """Start a single worker around a time-bounded speech implementation."""

        if capacity < 1:
            raise ValueError("Speech capacity must be positive")
        self._speak = speak
        self._queue: Queue[str] = Queue(maxsize=capacity)
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="tamagodji-voice", daemon=True)
        self._thread.start()

    def submit(self, message: str) -> None:
        """Queue short text without blocking; report overload without logging text."""

        if self._stopping.is_set():
            LOGGER.warning("Ignoring speech after voice shutdown")
            return
        try:
            self._queue.put_nowait(message[:180])
        except Full:
            LOGGER.warning("Speech queue full; skipping announcement")

    def _run(self) -> None:
        """Consume speech serially until shutdown, discarding stale queued audio."""

        while not self._stopping.is_set():
            try:
                message = self._queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                self._speak(message)
            except (OSError, RuntimeError):
                LOGGER.warning("Speech worker could not play announcement")

    def close(self) -> None:
        """Allow the active espeak call's ten-second timeout to expire."""

        self._stopping.set()
        self._thread.join(timeout=11)
        if self._thread.is_alive():
            LOGGER.warning("Speech worker did not stop before the shutdown deadline")
