"""Regression checks for bounded, asynchronous audio delivery."""

from threading import Event

import pytest

from tamagodji.hardware.queued_voice import QueuedVoice


def test_speech_backlog_is_bounded_and_reported(caplog: pytest.LogCaptureFixture) -> None:
    """Slow audio cannot grow the queue or block the caller."""

    entered, release = Event(), Event()
    received: list[str] = []

    def speak(message: str) -> None:
        """Block the first announcement to simulate busy hardware."""
        received.append(message)
        entered.set()
        assert release.wait(3)

    worker = QueuedVoice(speak, capacity=1)
    try:
        worker.submit("first")
        assert entered.wait(1)
        worker.submit("second")
        worker.submit("overflow")
        assert "Speech queue full" in caplog.text
        assert received == ["first"]
    finally:
        release.set()
        worker.close()
    assert not worker._thread.is_alive()
    worker.submit("after close")
    assert "after voice shutdown" in caplog.text


def test_worker_recovers_from_expected_audio_failure(caplog: pytest.LogCaptureFixture) -> None:
    """A failed announcement does not terminate the worker."""

    failed, recovered = Event(), Event()

    def speak(message: str) -> None:
        """Fail one request and acknowledge the next."""
        if message == "fail":
            failed.set()
            raise OSError("audio unavailable")
        recovered.set()

    worker = QueuedVoice(speak)
    try:
        worker.submit("fail")
        assert failed.wait(1)
        worker.submit("recover")
        assert recovered.wait(1)
        assert "could not play" in caplog.text
    finally:
        worker.close()


def test_rejects_unbounded_speech_capacity() -> None:
    """A zero capacity must not create an unlimited Queue."""

    with pytest.raises(ValueError):
        QueuedVoice(lambda message: None, capacity=0)
