"""Core package for the Tamagodji virtual pet."""

from .events import Event, EventKind
from .pet import Pet, PetState

__all__ = ["Event", "EventKind", "Pet", "PetState"]

