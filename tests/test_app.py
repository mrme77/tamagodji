"""HTTP snapshots must remain cheap, read-only, and independent of audio."""

from threading import Event as Signal, Thread
from unittest.mock import Mock

from tamagodji.app import TamagodjiApp
from tamagodji.events import Event, EventKind
from tamagodji.pet import Pet, PetState


def test_snapshot_does_not_write_advance_time_or_read_sensors() -> None:
    """Repeated website polling must not cause database writes or state changes."""

    store, display, temperature = Mock(), Mock(), Mock(return_value=36.5)
    pet = Pet(PetState(last_updated=100))
    app = TamagodjiApp(pet, store, display, temperature)
    app.render()
    store.reset_mock()
    temperature.reset_mock()
    initial = pet.state.to_dict()
    for _ in range(100):
        result = app.snapshot()
        assert result["temperature_c"] == 36.5
    assert pet.state.to_dict() == initial
    store.save.assert_not_called()
    temperature.assert_not_called()


def test_snapshot_before_first_render_handles_unknown_temperature() -> None:
    """Uninitialized sensor state is represented explicitly rather than fabricated."""

    app = TamagodjiApp(Pet(), Mock(), Mock())
    assert app.snapshot()["temperature_c"] is None


def test_speech_does_not_hold_state_lock() -> None:
    """A stalled audio callback cannot stop another thread reading the pet."""

    entered, release, read_done = Signal(), Signal(), Signal()

    def speak(message: str) -> None:
        """Hold audio until the test has attempted a concurrent read."""
        entered.set()
        assert release.wait(3)

    app = TamagodjiApp(Pet(), Mock(), Mock(), voice=speak)
    writer = Thread(target=app.handle, args=(Event(EventKind.FEED),))
    reader = Thread(target=lambda: (app.snapshot(), read_done.set()))
    writer.start()
    try:
        assert entered.wait(1)
        reader.start()
        assert read_done.wait(1)
    finally:
        release.set()
        writer.join(3)
        if reader.ident is not None:
            reader.join(3)


def test_present_message_renders_before_speaking() -> None:
    """The display updates immediately, even when speech is slow."""

    display = Mock()
    app = TamagodjiApp(Pet(), Mock(), display)

    def speak(message: str) -> None:
        """Verify display work has completed before calling the audio driver."""
        display.show.assert_called_once()

    app.voice = speak
    app.present_message("Hello")
