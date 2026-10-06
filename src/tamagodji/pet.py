"""The deterministic Tamagodji state machine."""

from dataclasses import asdict, dataclass, field
import time
from typing import Any

from .events import Event, EventKind


def _clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    """Keep a pet meter within its valid range."""

    return max(minimum, min(maximum, value))


@dataclass
class PetState:
    """Persisted values describing the pet's current condition."""

    hunger: int = 20
    happiness: int = 60
    energy: int = 70
    light_level: int = 100
    asleep: bool = False
    sick: bool = False
    last_event: str = "born"
    last_updated: float = field(default_factory=time.time)
    hunger_progress: float = 0.0
    energy_progress: float = 0.0
    happiness_progress: float = 0.0
    neglect_seconds: float = 0.0

    @property
    def mood(self) -> str:
        """Return the most important human-readable mood."""

        if self.sick:
            return "sick"
        if self.asleep:
            return "sleeping"
        if self.hunger >= 75:
            return "hungry"
        if self.energy <= 20:
            return "tired"
        if self.happiness >= 75:
            return "happy"
        if self.happiness <= 25:
            return "sad"
        return "content"

    def to_dict(self) -> dict[str, Any]:
        """Convert the state into JSON- and SQLite-friendly data."""

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PetState":
        """Build a state from persisted data, applying safe defaults."""

        defaults = cls().to_dict()
        defaults.update(data)
        return cls(**{key: defaults[key] for key in cls.__dataclass_fields__})


class Pet:
    """Apply normalized events to a pet state."""

    DARK_THRESHOLD = 20
    WAKE_THRESHOLD = 35
    AWAKE_HUNGER_INTERVAL = 20 * 60
    SLEEP_HUNGER_INTERVAL = 2 * 60 * 60
    AWAKE_ENERGY_INTERVAL = 2 * 60 * 60
    SLEEP_ENERGY_INTERVAL = 30 * 60
    AWAKE_HAPPINESS_INTERVAL = 2 * 60 * 60
    SICKNESS_THRESHOLD = 6 * 60 * 60

    def __init__(self, state: PetState | None = None) -> None:
        """Create a pet with a new or restored state."""

        self.state = state or PetState()
        self._message: str | None = None

    def apply(self, event: Event) -> PetState:
        """Apply one event and return the updated state."""

        self.state.last_event = event.kind.value
        if event.kind is EventKind.LIGHT_LEVEL:
            self._apply_light(event.value)
        elif event.kind is EventKind.FEED:
            self._apply_feed()
        elif event.kind is EventKind.PLAY:
            self._apply_play()
        elif event.kind is EventKind.SOUND_LEVEL:
            self._apply_sound(event.value)
        elif event.kind is EventKind.TICK:
            self._apply_tick(event.value)
        return self.state

    def _apply_light(self, value: int) -> None:
        """Update sleep state using hysteresis to prevent flicker."""

        self.state.light_level = _clamp(value)
        if self.state.asleep and self.state.light_level > self.WAKE_THRESHOLD:
            self.state.asleep = False
            self.state.happiness = _clamp(self.state.happiness + 4)
            self._message = "Good morning, fellas! I am awake!"
        elif not self.state.asleep and self.state.light_level < self.DARK_THRESHOLD:
            self.state.asleep = True
            self._message = "Good night, fellas! I am going to sleep!"

    def _apply_feed(self) -> None:
        """Feed the pet when it is awake."""

        if not self.state.asleep:
            self.state.hunger = _clamp(self.state.hunger - 28)
            self.state.happiness = _clamp(self.state.happiness + 6)
            if self.state.sick and self.state.hunger <= 75:
                self.state.sick = False
                self.state.neglect_seconds = 0.0

    def _apply_play(self) -> None:
        """Play with the pet when it is awake."""

        if not self.state.asleep:
            self.state.energy = _clamp(self.state.energy - 8)
            self.state.hunger = _clamp(self.state.hunger + 5)
            self.state.happiness = _clamp(self.state.happiness + 14)

    def _apply_sound(self, value: int) -> None:
        """React positively to daytime sound and negatively when asleep."""

        if value < 10:
            return
        if self.state.asleep:
            self.state.happiness = _clamp(self.state.happiness - 4)
        else:
            self.state.happiness = _clamp(self.state.happiness + 3)

    def _apply_tick(self, elapsed_seconds: float) -> None:
        """Advance needs according to real elapsed time, not loop count."""

        elapsed = max(0.0, elapsed_seconds)
        if elapsed == 0:
            return
        if self.state.asleep:
            self._advance_meter("hunger", "hunger_progress", elapsed, self.SLEEP_HUNGER_INTERVAL, 1)
            self._advance_meter("energy", "energy_progress", elapsed, self.SLEEP_ENERGY_INTERVAL, 1)
        else:
            self._advance_meter("hunger", "hunger_progress", elapsed, self.AWAKE_HUNGER_INTERVAL, 1)
            self._advance_meter("energy", "energy_progress", elapsed, self.AWAKE_ENERGY_INTERVAL, -1)
            self._advance_meter(
                "happiness", "happiness_progress", elapsed, self.AWAKE_HAPPINESS_INTERVAL, -1
            )
        if self.state.hunger >= 95:
            self.state.neglect_seconds += elapsed
        else:
            self.state.neglect_seconds = max(0.0, self.state.neglect_seconds - elapsed)
        if self.state.neglect_seconds >= self.SICKNESS_THRESHOLD:
            self.state.sick = True

    def _advance_meter(
        self,
        meter_name: str,
        progress_name: str,
        elapsed: float,
        interval: float,
        direction: int,
    ) -> None:
        """Apply a fractional time-based change to one integer meter."""

        progress = getattr(self.state, progress_name) + elapsed / interval
        whole_units = int(progress)
        if whole_units:
            current = getattr(self.state, meter_name)
            setattr(self.state, meter_name, _clamp(current + direction * whole_units))
            progress -= whole_units
        setattr(self.state, progress_name, progress)

    def consume_message(self) -> str | None:
        """Return and clear the latest sleep/wake message."""

        message = self._message
        self._message = None
        return message
