"""Tests for USB microphone capture command construction."""

import struct
from types import SimpleNamespace
from unittest.mock import patch

from tamagodji.hardware.audio import AlsaMicrophone


def test_microphone_writes_raw_audio_to_stdout() -> None:
    """The capture command sends raw samples to the pipe Python reads."""

    result = SimpleNamespace(stdout=struct.pack("<hh", 100, -100))
    with patch("tamagodji.hardware.audio.subprocess.run", return_value=result) as run:
        event = AlsaMicrophone().read_event()

    command = run.call_args.args[0]
    assert command[-1] == "/dev/stdout"
    assert event.kind.value == "sound_level"


def test_microphone_uses_configured_alsa_device() -> None:
    """A configured USB ALSA device is passed to arecord."""

    result = SimpleNamespace(stdout=struct.pack("<hh", 100, -100))
    with patch.dict("os.environ", {"TAMAGODJI_AUDIO_DEVICE": "plughw:CARD=Device,DEV=0"}), patch(
        "tamagodji.hardware.audio.subprocess.run", return_value=result
    ) as run:
        AlsaMicrophone().read_event()

    command = run.call_args.args[0]
    assert command[2:4] == ["-D", "plughw:CARD=Device,DEV=0"]
