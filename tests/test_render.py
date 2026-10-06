"""Tests for compact OLED and mock display frames."""

from tamagodji.pet import PetState
from tamagodji.render import frame_for_state


def test_frame_includes_pi_temperature_when_available() -> None:
    """Hardware telemetry appears as a compact OLED line."""

    frame = frame_for_state(PetState(), temperature_c=37.6)
    assert "Pi: 37.6C" in frame


def test_frame_works_without_temperature() -> None:
    """Mock mode remains independent of Raspberry Pi sensors."""

    frame = frame_for_state(PetState())
    assert "Pi:" not in frame


def test_long_message_wraps_for_oled() -> None:
    """Long spoken messages are split into readable OLED lines."""

    frame = frame_for_state(
        PetState(asleep=True),
        message="Good night, fellas! I am going to sleep!",
    )
    assert "Good night, fellas!" in frame
    assert "I am going to sleep!" in frame
