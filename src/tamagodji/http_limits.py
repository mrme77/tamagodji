"""Bound HTTP concurrency and request rates without tracking visitor identities."""

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import socket
import threading
import time

LOGGER = logging.getLogger(__name__)


class RateLimit:
    """A process-wide, thread-safe token bucket using monotonic time."""

    def __init__(
        self, interval: float, burst: int = 1, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Allow one request per interval, with at most burst saved requests."""

        if interval <= 0 or burst < 1:
            raise ValueError("Rate limits must be positive")
        self._interval = interval
        self._burst = burst
        self._clock = clock
        self._tokens = float(burst)
        self._updated = clock()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Consume one token, returning False immediately when exhausted."""

        with self._lock:
            now = self._clock()
            self._tokens = min(
                self._burst, self._tokens + max(0.0, now - self._updated) / self._interval
            )
            self._updated = now
            if self._tokens < 1:
                return False
            self._tokens -= 1
            return True


class BoundedHTTPServer(ThreadingHTTPServer):
    """Limit active connections before allocating request worker threads."""

    daemon_threads = True
    request_queue_size = 8

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        max_connections: int = 8,
        timeout: float = 5.0,
    ) -> None:
        """Configure small limits appropriate for the Raspberry Pi."""

        if max_connections < 1 or timeout <= 0:
            raise ValueError("HTTP limits must be positive")
        self._slots = threading.BoundedSemaphore(max_connections)
        self._request_timeout = timeout
        super().__init__(address, handler)

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        """Set an inactivity deadline on headers, bodies, and responses."""

        connection, address = super().get_request()
        connection.settimeout(self._request_timeout)
        return connection, address

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        """Reject overflow instead of spawning an unbounded number of threads."""

        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                request.sendall(
                    b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\n"
                    b"Connection: close\r\nCache-Control: no-store\r\nRetry-After: 5\r\n\r\n"
                )
            except OSError:
                # The client may already have disconnected; always free the socket.
                LOGGER.debug("Overloaded HTTP client disconnected before rejection")
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except (OSError, RuntimeError):
            self._slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        """Return a connection slot even if a handler fails."""

        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()
