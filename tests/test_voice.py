"""Tests for offline voice output."""

from unittest.mock import patch
import pytest

from tamagodji.hardware.voice import EspeakVoice


def test_espeak_speaks_message() -> None:
    """Voice output invokes espeak with the configured language."""

    with patch("tamagodji.hardware.voice.subprocess.run") as run:
        EspeakVoice().speak("Good morning!")

    run.assert_called_once_with(
        ["espeak-ng", "-v", "en", "--stdin"],
        input="Good morning!",
        text=True,
        check=True,
        timeout=10,
    )


def test_voice_treats_options_as_text_and_bounds_length() -> None:
    """Untrusted model text cannot become espeak flags or arbitrarily long speech."""

    with patch("tamagodji.hardware.voice.subprocess.run") as run:
        EspeakVoice().speak("-f/etc/passwd " + "x" * 200)
    assert run.call_args.args[0][-1] == "--stdin"
    assert run.call_args.kwargs["input"].startswith("-f/etc/passwd")
    assert len(run.call_args.kwargs["input"]) == 180


def test_voice_logs_missing_executable(caplog: pytest.LogCaptureFixture) -> None:
    """Unavailable audio must be reported without crashing the pet."""

    with patch("tamagodji.hardware.voice.subprocess.run", side_effect=FileNotFoundError):
        EspeakVoice().speak("Hello")
    assert "Could not speak pet message" in caplog.text
