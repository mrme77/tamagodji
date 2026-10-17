"""Small local HTTP API for the live Tamagodji process."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from typing import Any

from .events import Event, EventKind

LOGGER = logging.getLogger(__name__)
StateProvider = Callable[[], dict[str, object]]
EventSink = Callable[[Event], None]
MessageSink = Callable[[str], None]
Brain = Callable[[str, dict[str, object]], Any]


@dataclass(frozen=True)
class ApiConfig:
    """Configuration for the local API listener."""

    host: str = "127.0.0.1"
    port: int = 8080
    api_token: str | None = None
    cors_origin: str = "*"


class ApiServer:
    """Serve state and queue safe commands without owning pet state."""

    def __init__(
        self,
        state_provider: StateProvider,
        event_sink: EventSink,
        config: ApiConfig | None = None,
        brain: Brain | None = None,
        message_sink: MessageSink | None = None,
    ) -> None:
        """Create an API server around callbacks owned by the pet loop."""

        self.config = config or ApiConfig()
        self._state_provider = state_provider
        self._event_sink = event_sink
        self._brain = brain
        self._message_sink = message_sink
        self._server: ThreadingHTTPServer | None = None
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
        if self.config.host not in {"127.0.0.1", "localhost", "::1"} and not self.config.api_token:
            LOGGER.warning("API is exposed beyond localhost without TAMAGODJI_API_TOKEN")
        handler = self._handler_type()
        self._server = ThreadingHTTPServer((self.config.host, self.config.port), handler)
        self._server.daemon_threads = True
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

            def do_OPTIONS(self) -> None:
                """Respond to browser CORS preflight requests."""

                self.send_response(HTTPStatus.NO_CONTENT)
                self._write_cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                """Serve health and current-state endpoints."""

                if self.path == "/api/health":
                    self._send_json({"ok": True, "service": "tamagodji"})
                    return
                if self.path == "/api/pet":
                    self._send_json(api._state_provider())
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                """Queue an interaction or ask the optional LLM brain."""

                if not self._authorized():
                    self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                payload = self._read_json()
                if payload is None:
                    return
                if self.path == "/api/interactions":
                    self._handle_interaction(payload)
                    return
                if self.path == "/api/chat":
                    self._handle_chat(payload)
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def _handle_interaction(self, payload: dict[str, Any]) -> None:
                """Validate and queue a deterministic pet interaction."""

                action = str(payload.get("action", "")).lower()
                event_kind = {"feed": EventKind.FEED, "play": EventKind.PLAY}.get(action)
                if event_kind is None:
                    self._send_json({"error": "action must be feed or play"}, HTTPStatus.BAD_REQUEST)
                    return
                api._event_sink(Event(event_kind, source="web"))
                self._send_json({"accepted": True, "action": action}, HTTPStatus.ACCEPTED)

            def _handle_chat(self, payload: dict[str, Any]) -> None:
                """Ask OpenRouter for a reply and queue only allowed actions."""

                if api._brain is None:
                    self._send_json({"error": "OpenRouter is not configured"}, HTTPStatus.NOT_IMPLEMENTED)
                    return
                message = str(payload.get("message", "")).strip()
                if not message or len(message) > 500:
                    self._send_json({"error": "message must be 1-500 characters"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    result = api._brain(message, api._state_provider())
                except RuntimeError as error:
                    LOGGER.warning("OpenRouter request failed: %s", error)
                    self._send_json({"error": "the Tamagodji brain is unavailable"}, HTTPStatus.BAD_GATEWAY)
                    return
                action = getattr(result, "action", None)
                reply = str(getattr(result, "reply", "")).strip()
                if action in {"FEED", "PLAY"}:
                    api._event_sink(Event(EventKind(action.lower()), source="llm"))
                if reply and api._message_sink:
                    api._message_sink(reply)
                self._send_json({"reply": reply, "action": action})

            def _authorized(self) -> bool:
                """Check the optional bearer token for state-changing requests."""

                expected = api.config.api_token
                if not expected:
                    return True
                return self.headers.get("Authorization") == f"Bearer {expected}"

            def _read_json(self) -> dict[str, Any] | None:
                """Read a bounded JSON object from the request body."""

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send_json({"error": "invalid content length"}, HTTPStatus.BAD_REQUEST)
                    return None
                if length <= 0 or length > 16_384:
                    self._send_json({"error": "request body is missing or too large"}, HTTPStatus.BAD_REQUEST)
                    return None
                try:
                    value = json.loads(self.rfile.read(length))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    self._send_json({"error": f"invalid JSON: {error}"}, HTTPStatus.BAD_REQUEST)
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
