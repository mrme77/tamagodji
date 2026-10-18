"""Application orchestration shared by mock and hardware modes."""

from collections.abc import Callable, Iterable
import threading
import time

from .events import Event, EventKind
from .pet import Pet
from .render import frame_for_state
from .storage import PetStore


class TamagodjiApp:
    """Connect the pet, persistence, event sources, and display."""

    def __init__(
        self,
        pet: Pet,
        store: PetStore,
        display: object,
        temperature_reader: Callable[[], float | None] | None = None,
        voice: Callable[[str], None] | None = None,
    ) -> None:
        """Create an application controller."""

        self.pet = pet
        self.store = store
        self.display = display
        self.temperature_reader = temperature_reader
        self.voice = voice
        self._lock = threading.RLock()
        self._temperature: float | None = None

    def render(self, message: str | None = None) -> None:
        """Persist and render the current state."""

        with self._lock:
            self.store.save(self.pet.state)
            self._temperature = self.temperature_reader() if self.temperature_reader else None
            self.display.show(
                frame_for_state(self.pet.state, message=message, temperature_c=self._temperature)
            )

    def _advance_time(self) -> None:
        """Apply need decay since the last persisted state update."""

        now = time.time()
        elapsed = max(0.0, now - self.pet.state.last_updated)
        self.pet.apply(Event(EventKind.TICK, value=elapsed, source="clock"))
        self.pet.state.last_updated = now

    def handle(self, event: Event) -> None:
        """Apply one event, then persist and render."""

        with self._lock:
            self._advance_time()
            if event.kind is not EventKind.TICK:
                self.pet.apply(event)
            message = self.pet.consume_message()
            self.render(message=message)
        # External audio must never hold the state lock used by HTTP readers.
        if message and self.voice:
            self.voice(message)

    def handle_many(self, events: Iterable[Event]) -> None:
        """Apply a sequence of events and render after each one."""

        for event in events:
            self.handle(event)

    def tick(self) -> None:
        """Advance the pet by one runtime interval."""

        self.handle(Event(EventKind.TICK, source="clock"))

    def present_message(self, message: str) -> None:
        """Speak and render a message queued by an external interface."""

        with self._lock:
            self.render(message=message)
        if self.voice:
            self.voice(message)

    def snapshot(self) -> dict[str, object]:
        """Read the latest loop state without advancing time or touching SQLite."""

        with self._lock:
            state = self.pet.state
            return {
                "mood": state.mood,
                "fullness": 100 - state.hunger,
                "hunger": state.hunger,
                "happiness": state.happiness,
                "energy": state.energy,
                "light_level": state.light_level,
                "asleep": state.asleep,
                "sick": state.sick,
                "last_event": state.last_event,
                "last_updated": state.last_updated,
                "temperature_c": self._temperature,
                "display": frame_for_state(state, temperature_c=self._temperature),
                "interaction_counts": {
                    "feed": state.web_feed_count,
                    "play": state.web_play_count,
                    "total": state.web_feed_count + state.web_play_count,
                },
            }
