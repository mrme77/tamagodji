"""Tests for the USB message contract used by the micro:bits."""

from tamagodji.hardware.microbit import MicrobitSerial
from unittest.mock import Mock


def test_serial_reader_waits_for_complete_light_message() -> None:
    """LIGHT:100 split across USB reads must never be mistaken for LIGHT:1."""

    reader = object.__new__(MicrobitSerial)
    reader.source = "room"
    reader._buffer = bytearray()
    reader._discarding = False
    reader._serial = Mock(in_waiting=7)
    reader._serial.read.side_effect = [b"LIGHT:1", b"00\nFEED\n"]
    assert reader.poll() == []
    events = reader.poll()
    assert events[0].value == 100
    assert events[1].kind.value == "feed"


def test_serial_reader_discards_oversize_line_and_recovers() -> None:
    """A noisy device cannot grow the receive buffer indefinitely."""

    reader = object.__new__(MicrobitSerial)
    reader.source = "room"
    reader._buffer = bytearray()
    reader._discarding = False
    reader._serial = Mock(in_waiting=10000)
    reader._serial.read.side_effect = [b"x" * 512, b"LIGHT:1\nLIGHT:80\n"]
    assert reader.poll() == []
    assert len(reader._buffer) == 0
    events = reader.poll()
    assert len(events) == 1
    assert events[0].value == 80
    reader._serial.read.assert_called_with(512)


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

