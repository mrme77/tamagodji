"""Tests for the USB message contract used by the micro:bits."""

from tamagodji.hardware.microbit import MicrobitSerial


def test_interaction_messages_parse_to_actions() -> None:
    """FEED and PLAY become the expected normalized events."""

    reader = object.__new__(MicrobitSerial)
    reader.source = "interaction"
    assert reader._parse("FEED").kind.value == "feed"
    assert reader._parse("PLAY").kind.value == "play"


def test_room_light_message_is_clamped() -> None:
    """A malformed or out-of-range room reading cannot corrupt pet state."""

    reader = object.__new__(MicrobitSerial)
    reader.source = "room"
    assert reader._parse("LIGHT:255").value == 100
    assert reader._parse("LIGHT:-5").value == 0
    assert reader._parse("LIGHT:not-a-number") is None

