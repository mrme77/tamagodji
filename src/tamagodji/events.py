"""Events shared by sensors, controllers, and the pet state machine."""

from dataclasses import dataclass
from enum import Enum


class EventKind(str, Enum):
    """Supported inputs that can change the pet."""

    FEED = "feed"
    PLAY = "play"
    LIGHT_LEVEL = "light_level"
    SOUND_LEVEL = "sound_level"
    TICK = "tick"


@dataclass(frozen=True)
class Event:
    """A normalized input from a sensor or interaction device."""

    kind: EventKind
    value: int = 0
    source: str = "system"

