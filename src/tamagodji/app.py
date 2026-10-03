"""Application orchestration shared by mock and hardware modes."""

from collections.abc import Iterable
import time

from .events import Event, EventKind
from .pet import Pet
from .render import frame_for_state
from .storage import PetStore


class TamagodjiApp:
    """Connect the pet, persistence, event sources, and display."""

    def __init__(self, pet: Pet, store: PetStore, display: object) -> None:
        """Create an application controller."""

        self.pet = pet
        self.store = store
        self.display = display

    def render(self, message: str | None = None) -> None:
        """Persist and render the current state."""

        self.store.save(self.pet.state)
        self.display.show(frame_for_state(self.pet.state, message=message))

    def _advance_time(self) -> None:
        """Apply need decay since the last persisted state update."""

        now = time.time()
        elapsed = max(0.0, now - self.pet.state.last_updated)
        self.pet.apply(Event(EventKind.TICK, value=elapsed, source="clock"))
        self.pet.state.last_updated = now

    def handle(self, event: Event) -> None:
        """Apply one event, then persist and render."""

        self._advance_time()
        if event.kind is not EventKind.TICK:
            self.pet.apply(event)
        self.render(message=self.pet.consume_message())

    def handle_many(self, events: Iterable[Event]) -> None:
        """Apply a sequence of events and render after each one."""

        for event in events:
            self.handle(event)

    def tick(self) -> None:
        """Advance the pet by one runtime interval."""

        self.handle(Event(EventKind.TICK, source="clock"))
