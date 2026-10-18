"""Limits on anonymous resource consumption and incomplete HTTP requests."""

from http.client import HTTPConnection
import socket
import threading
from unittest.mock import patch

import pytest

from tamagodji.api import ApiConfig, ApiServer
from tamagodji.http_limits import RateLimit


def test_rate_bucket_refills_and_caps_saved_tokens() -> None:
    """Idle time restores capacity but cannot accumulate an unlimited burst."""

    now = [0.0]
    limit = RateLimit(interval=5, burst=2, clock=lambda: now[0])
    assert limit.allow()
    assert limit.allow()
    assert not limit.allow()
    now[0] = 4
    assert not limit.allow()
    now[0] = 5
    assert limit.allow()
    now[0] = 1000
    assert limit.allow()
    assert limit.allow()
    assert not limit.allow()


def test_rate_bucket_is_atomic_across_threads() -> None:
    """Concurrent request threads cannot spend the same token twice."""

    limit = RateLimit(interval=1000)
    results: list[bool] = []
    threads = [threading.Thread(target=lambda: results.append(limit.allow())) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(results) == 1


def test_invalid_rate_limits_are_rejected() -> None:
    """Bad limits fail at construction rather than disabling protection."""

    with pytest.raises(ValueError):
        RateLimit(0)
    with pytest.raises(ValueError):
        RateLimit(1, burst=0)


def test_incomplete_body_times_out_without_enqueuing() -> None:
    """A client that advertises more bytes than it sends releases its worker."""

    events: list[object] = []
    api = ApiServer(lambda: {}, events.append, ApiConfig(port=0, api_token="test", request_timeout=0.1))
    api.start()
    connection = HTTPConnection(*api.address, timeout=2)
    try:
        connection.request("POST", "/api/interactions", body="{", headers={
            "Content-Type": "application/json", "Authorization": "Bearer test", "Content-Length": "100",
        })
        assert connection.getresponse().status == 408
        assert not events
    finally:
        connection.close()
        api.stop()


def test_connection_limit_rejects_overflow_before_starting_worker() -> None:
    """A slow-header connection cannot cause unlimited worker allocation."""

    api = ApiServer(lambda: {}, lambda event: None, ApiConfig(port=0, max_connections=1))
    api.start()
    admitted = threading.Event()
    original = api._server.process_request_thread

    def track_worker(*args: object) -> None:
        """Signal once the first connection owns the sole worker slot."""
        admitted.set()
        original(*args)

    with patch.object(api._server, "process_request_thread", side_effect=track_worker):
        first = socket.create_connection(api.address, timeout=2)
        second = HTTPConnection(*api.address, timeout=2)
        try:
            first.sendall(b"GET /api/health HTTP/1.0\r\n")
            assert admitted.wait(1)
            second.request("GET", "/api/health")
            assert second.getresponse().status == 503
            first.sendall(b"\r\n")
            assert b"200 OK" in first.recv(4096)
        finally:
            first.close()
            second.close()
            api.stop()
