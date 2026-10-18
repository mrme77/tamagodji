"""Small local HTTP API for the live Tamagodji process."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from queue import Full
import threading
from typing import Any

from .events import Event, EventKind
from .http_limits import BoundedHTTPServer, RateLimit

LOGGER = logging.getLogger(__name__)
StateProvider = Callable[[], dict[str, object]]
EventSink = Callable[[Event], None]
ChatSink = Callable[[str, Event | None], None]
Brain = Callable[[str, dict[str, object]], Any]


@dataclass(frozen=True)
class ApiConfig:
    """Configuration for the local API listener."""

    host: str = "127.0.0.1"
    port: int = 8080
    api_token: str | None = None
    cors_origin: str = "*"
    max_connections: int = 8
    request_timeout: float = 5.0


class ApiServer:
    """Serve state and queue safe commands without owning pet state."""

    def __init__(
        self,
        state_provider: StateProvider,
        event_sink: EventSink,
        config: ApiConfig | None = None,
        brain: Brain | None = None,
        chat_sink: ChatSink | None = None,
    ) -> None:
        """Create an API server around callbacks owned by the pet loop."""

        self.config = config or ApiConfig()
        self._state_provider = state_provider
        self._event_sink = event_sink
        self._brain = brain
        self._chat_sink = chat_sink
        self._reads = RateLimit(interval=0.1, burst=20)
        self._writes = RateLimit(interval=5.0)
        self._chats = RateLimit(interval=60.0)
        self._chat_slot = threading.BoundedSemaphore(1)
        self._server: BoundedHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int] | None:
        """Return the bound address after startup."""

        if self._server is None:
            return None
        host, port = self._server.server_address[:2]
        return host, port

    def start(self) -> None:
        """Start serving requests in a daemon thread."""

        if self._server is not None:
            return
        if not self.config.api_token or not self.config.api_token.strip():
            LOGGER.warning("API writes disabled: TAMAGODJI_API_TOKEN is missing or blank")
        handler = self._handler_type()
        self._server = BoundedHTTPServer(
            (self.config.host, self.config.port), handler,
            self.config.max_connections, self.config.request_timeout,
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        LOGGER.info("Tamagodji API listening on http://%s:%s", *self.address)

    def stop(self) -> None:
        """Stop the listener and wait briefly for its thread."""

        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        """Build a request handler bound to this server's callbacks."""

        api = self

        class Handler(BaseHTTPRequestHandler):
            """Handle one JSON API request."""

            def handle(self) -> None:
                """Avoid exception tracebacks when an HTTP client disconnects normally."""

                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    LOGGER.debug("HTTP client disconnected or timed out")

            def do_OPTIONS(self) -> None:
                """Respond to browser CORS preflight requests."""

                self.send_response(HTTPStatus.NO_CONTENT)
                self._write_cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                """Serve health and current-state endpoints."""

                if not api._reads.allow():
                    self._send_json({"error": "too many reads"}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                if self.path == "/api/health":
                    self._send_json({"ok": True, "service": "tamagodji"})
                    return
                if self.path == "/api/pet":
                    try:
                        state = api._state_provider()
                    except RuntimeError:
                        LOGGER.exception("Could not read pet state")
                        self._send_json({"error": "state unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)
                        return
                    self._send_json(state)
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                """Queue an interaction or ask the optional LLM brain."""

                if not api.config.api_token or not api.config.api_token.strip():
                    self._send_json({"error": "API writes are disabled"}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                if not self._authorized():
                    self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                payload = self._read_json()
                if payload is None:
                    return
                try:
                    if self.path == "/api/interactions":
                        self._handle_interaction(payload)
                        return
                    if self.path == "/api/chat":
                        self._handle_chat(payload)
                        return
                except Full:
                    self._send_json({"error": "command queue is full"}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                except RuntimeError:
                    LOGGER.warning("Pet command could not be processed")
                    self._send_json({"error": "pet unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def _handle_interaction(self, payload: dict[str, Any]) -> None:
                """Validate and queue a deterministic pet interaction."""

                raw_action = payload.get("action")
                action = raw_action.lower() if isinstance(raw_action, str) else ""
                event_kind = {"feed": EventKind.FEED, "play": EventKind.PLAY}.get(action)
                if event_kind is None:
                    self._send_json({"error": "action must be feed or play"}, HTTPStatus.BAD_REQUEST)
                    return
                if not api._writes.allow():
                    self._send_json({"error": "please wait before another action"}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                if api._state_provider().get("asleep"):
                    self._send_json({"error": "Tamagodji is sleeping"}, HTTPStatus.CONFLICT)
                    return
                api._event_sink(Event(event_kind, source="web"))
                self._send_json({"accepted": True, "action": action}, HTTPStatus.ACCEPTED)

            def _handle_chat(self, payload: dict[str, Any]) -> None:
                """Ask OpenRouter for a reply and queue only allowed actions."""

                if api._brain is None:
                    self._send_json({"error": "OpenRouter is not configured"}, HTTPStatus.NOT_IMPLEMENTED)
                    return
                raw_message = payload.get("message")
                message = raw_message.strip() if isinstance(raw_message, str) else ""
                if not message or len(message) > 500:
                    self._send_json({"error": "message must be 1-500 characters"}, HTTPStatus.BAD_REQUEST)
                    return
                if not api._chats.allow() or not api._writes.allow():
                    self._send_json({"error": "please wait before another chat"}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                if not api._chat_slot.acquire(blocking=False):
                    self._send_json({"error": "brain is busy"}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                try:
                    try:
                        result = api._brain(message, api._state_provider())
                    except RuntimeError:
                        LOGGER.warning("OpenRouter request failed")
                        self._send_json({"error": "the Tamagodji brain is unavailable"}, HTTPStatus.BAD_GATEWAY)
                        return
                finally:
                    api._chat_slot.release()
                action = getattr(result, "action", None)
                reply = str(getattr(result, "reply", "")).strip()[:180]
                event = None
                if action in {"FEED", "PLAY"}:
                    event = Event(EventKind(action.lower()), source="llm")
                else:
                    action = None
                if api._chat_sink:
                    api._chat_sink(reply, event)
                elif event is not None:
                    api._event_sink(event)
                self._send_json({"reply": reply, "action": action})

            def _authorized(self) -> bool:
                """Fail closed and compare the bearer token in constant time."""

                expected = api.config.api_token
                if not expected or not expected.strip() or len(self.headers.get_all("Authorization", [])) != 1:
                    return False
                return hmac.compare_digest(
                    self.headers.get("Authorization", "").encode("utf-8"),
                    f"Bearer {expected}".encode("utf-8"),
                )

            def _read_json(self) -> dict[str, Any] | None:
                """Read a bounded JSON object from the request body."""

                if self.headers.get_content_type() != "application/json":
                    self._send_json({"error": "use application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                    return None
                if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                    self._send_json({"error": "invalid body framing"}, HTTPStatus.BAD_REQUEST)
                    return None
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send_json({"error": "invalid content length"}, HTTPStatus.BAD_REQUEST)
                    return None
                if length <= 0 or length > 16_384:
                    self._send_json({"error": "request body is missing or too large"}, HTTPStatus.BAD_REQUEST)
                    return None
                try:
                    body = self.rfile.read(length)
                    if len(body) != length:
                        self._send_json({"error": "incomplete body"}, HTTPStatus.BAD_REQUEST)
                        return None
                    value = json.loads(body)
                except TimeoutError:
                    self._send_json({"error": "request body timed out"}, HTTPStatus.REQUEST_TIMEOUT)
                    return None
                except (ValueError, RecursionError):
                    self._send_json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
                    return None
                if not isinstance(value, dict):
                    self._send_json({"error": "JSON body must be an object"}, HTTPStatus.BAD_REQUEST)
                    return None
                return value

            def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
                """Write one JSON response with CORS headers."""

                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self._write_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if status in {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}:
                    self.send_header("Retry-After", "60" if self.path == "/api/chat" else "5")
                self.end_headers()
                self.wfile.write(body)

            def _write_cors_headers(self) -> None:
                """Allow the configured website origin to call the API."""

                self.send_header("Access-Control-Allow-Origin", api.config.cors_origin)
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def log_message(self, format_string: str, *args: object) -> None:
                """Send request logs through the application logger."""

                LOGGER.info("API " + format_string, *args)

        return Handler
