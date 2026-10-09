"""Tests for the deterministic pet behavior."""

from tamagodji.events import Event, EventKind
from tamagodji.pet import Pet, PetState


def test_feed_reduces_hunger_and_increases_happiness() -> None:
    """Feeding an awake pet improves its two relevant meters."""

    pet = Pet(PetState(hunger=70, happiness=40))
    pet.apply(Event(EventKind.FEED))
    assert pet.state.hunger == 42
    assert pet.state.happiness == 46
    assert pet.consume_message() in Pet.FEED_MESSAGES


def test_feed_messages_do_not_repeat_immediately(monkeypatch) -> None:
    """Repeated feeding uses a different phrase when alternatives exist."""

    monkeypatch.setattr("tamagodji.pet.random.choice", lambda choices: choices[0])
    pet = Pet(PetState(hunger=70))

    pet.apply(Event(EventKind.FEED))
    first_message = pet.consume_message()
    pet.apply(Event(EventKind.FEED))
    second_message = pet.consume_message()

    assert first_message in Pet.FEED_MESSAGES
    assert second_message in Pet.FEED_MESSAGES
    assert second_message != first_message


def test_petting_creates_a_random_pet_message() -> None:
    """The second interaction produces a petting response."""

    pet = Pet(PetState())
    pet.apply(Event(EventKind.PLAY))

    assert pet.consume_message() in Pet.PET_MESSAGES


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


def test_needs_change_with_elapsed_time_not_event_count() -> None:
    """A long elapsed period changes needs by a predictable amount."""

    pet = Pet(PetState(hunger=20, energy=70, happiness=60))
    pet.apply(Event(EventKind.TICK, value=2 * 60 * 60))
    assert pet.state.hunger == 26
    assert pet.state.energy == 69
    assert pet.state.happiness == 59


def test_sleep_and_wake_create_one_time_messages() -> None:
    """Light transitions produce human-friendly messages once."""

    pet = Pet(PetState(light_level=100))
    pet.apply(Event(EventKind.LIGHT_LEVEL, value=5))
    assert pet.consume_message() == "Good night, fellas! I am going to sleep!"
    assert pet.consume_message() is None
    pet.apply(Event(EventKind.LIGHT_LEVEL, value=80))
    assert pet.consume_message() == "Good morning, fellas! I am awake!"


def test_prolonged_hunger_makes_pet_sick_but_not_dead() -> None:
    """Neglect creates a recoverable sickness state."""

    pet = Pet(PetState(hunger=95))
    pet.apply(Event(EventKind.TICK, value=6 * 60 * 60))
    assert pet.state.sick is True
    pet.apply(Event(EventKind.FEED))
    assert pet.state.sick is False
