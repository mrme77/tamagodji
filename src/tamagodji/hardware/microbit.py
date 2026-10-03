"""USB serial adapter for micro:bit event messages."""

import logging

from ..events import Event, EventKind

LOGGER = logging.getLogger(__name__)


class MicrobitSerial:
    """Read simple newline-delimited events from one micro:bit."""

    def __init__(self, port: str, source: str) -> None:
        """Open a non-blocking serial connection."""

        try:
            import serial
        except ImportError as error:
            raise RuntimeError("USB micro:bit support needs pyserial installed") from error
        try:
            self._serial = serial.Serial(port, baudrate=115200, timeout=0)
        except serial.SerialException as error:
            raise RuntimeError(f"Could not open micro:bit serial port: {port}") from error
        self.source = source

    def poll(self) -> list[Event]:
        """Read and parse all complete messages currently available."""

        events: list[Event] = []
        while self._serial.in_waiting:
            line = self._serial.readline().decode("utf-8", errors="replace").strip()
            event = self._parse(line)
            if event is not None:
                events.append(event)
        return events

    def _parse(self, line: str) -> Event | None:
        """Convert one micro:bit protocol line into a normalized event."""

        if not line:
            return None
        command, _, raw_value = line.upper().partition(":")
        simple_events = {"FEED": EventKind.FEED, "PLAY": EventKind.PLAY}
        if command in simple_events:
            return Event(simple_events[command], source=self.source)
        numeric_events = {"LIGHT": EventKind.LIGHT_LEVEL, "SOUND": EventKind.SOUND_LEVEL}
        if command in numeric_events:
            try:
                value = max(0, min(100, int(raw_value)))
            except ValueError:
                LOGGER.warning("Ignoring malformed micro:bit message: %r", line)
                return None
            return Event(numeric_events[command], value=value, source=self.source)
        LOGGER.warning("Ignoring unknown micro:bit message: %r", line)
        return None

