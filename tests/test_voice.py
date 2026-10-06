"""Tests for offline voice output."""

from unittest.mock import patch

from tamagodji.hardware.voice import EspeakVoice


def test_espeak_speaks_message() -> None:
    """Voice output invokes espeak with the configured language."""

    with patch("tamagodji.hardware.voice.subprocess.run") as run:
        EspeakVoice().speak("Good morning!")

    run.assert_called_once_with(
        ["espeak-ng", "-v", "en", "Good morning!"],
        check=True,
        timeout=10,
    )
