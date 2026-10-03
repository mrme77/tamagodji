"""Local microphone level adapter using the Raspberry Pi ALSA utility."""

import math
import struct
import subprocess

from ..events import Event, EventKind


class AlsaMicrophone:
    """Capture a short raw PCM sample and convert it to a 0-100 level."""

    def __init__(self, seconds: float = 0.25) -> None:
        """Configure the sample duration used for each reading."""

        self.seconds = seconds

    def read_event(self) -> Event:
        """Capture one sample and return a sound-level event."""

        duration = max(1, math.ceil(self.seconds))
        command = [
            "arecord", "-q", "-f", "S16_LE", "-c", "1", "-r", "16000",
            "-d", str(duration), "-t", "raw",
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("Could not read the USB microphone with arecord") from error
        samples = struct.iter_unpack("<h", result.stdout)
        squared_total = 0
        count = 0
        for (sample,) in samples:
            squared_total += sample * sample
            count += 1
        rms = math.sqrt(squared_total / count) if count else 0.0
        level = max(0, min(100, round(rms / 327.68)))
        return Event(EventKind.SOUND_LEVEL, value=level, source="microphone")
