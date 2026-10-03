"""Application orchestration shared by mock and hardware modes."""

from collections.abc import Iterable

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

    def render(self) -> None:
        """Persist and render the current state."""

        self.store.save(self.pet.state)
        self.display.show(frame_for_state(self.pet.state))

    def handle(self, event: Event) -> None:
        """Apply one event, then persist and render."""

        self.pet.apply(event)
        self.render()

    def handle_many(self, events: Iterable[Event]) -> None:
        """Apply a sequence of events and render after each one."""

        for event in events:
            self.handle(event)

    def tick(self) -> None:
        """Advance the pet by one runtime interval."""

        self.handle(Event(EventKind.TICK, source="clock"))

