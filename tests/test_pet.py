"""Tests for the deterministic pet behavior."""

from tamagodji.events import Event, EventKind
from tamagodji.pet import Pet, PetState


def test_feed_reduces_hunger_and_increases_happiness() -> None:
    """Feeding an awake pet improves its two relevant meters."""

    pet = Pet(PetState(hunger=70, happiness=40))
    pet.apply(Event(EventKind.FEED))
    assert pet.state.hunger == 42
    assert pet.state.happiness == 46


def test_darkness_puts_pet_to_sleep_and_night_noise_is_negative() -> None:
    """Noise should not make a sleeping pet happy."""

    pet = Pet(PetState(happiness=60))
    pet.apply(Event(EventKind.LIGHT_LEVEL, value=5))
    pet.apply(Event(EventKind.SOUND_LEVEL, value=80))
    assert pet.state.asleep is True
    assert pet.state.happiness == 56


def test_light_hysteresis_prevents_flickering() -> None:
    """A dim transition should not immediately wake the pet."""

    pet = Pet(PetState(asleep=True, light_level=5))
    pet.apply(Event(EventKind.LIGHT_LEVEL, value=25))
    assert pet.state.asleep is True
    pet.apply(Event(EventKind.LIGHT_LEVEL, value=50))
    assert pet.state.asleep is False

