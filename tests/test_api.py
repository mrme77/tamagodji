"""Tests for the local Tamagodji JSON API."""

import json
from http.client import HTTPConnection
from queue import Queue

from tamagodji.api import ApiConfig, ApiServer


def test_api_returns_state_and_queues_interaction() -> None:
    """The public read route works while writes stay queued for the pet loop."""

    events: Queue[object] = Queue()
    server = ApiServer(
        lambda: {"mood": "happy", "fullness": 80},
        events.put,
        ApiConfig(port=0, api_token="test-token"),
    )
    server.start()
    assert server.address is not None
    connection = HTTPConnection(*server.address)
    try:
        connection.request("GET", "/api/pet")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {"mood": "happy", "fullness": 80}

        body = json.dumps({"action": "feed"})
        connection.request("POST", "/api/interactions", body=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer test-token",
        })
        response = connection.getresponse()
        assert response.status == 202
        assert events.get().kind.value == "feed"
    finally:
        connection.close()
        server.stop()


def test_api_rejects_writes_without_the_bearer_token() -> None:
    """A configured API token protects website-triggered interactions."""

    server = ApiServer(
        lambda: {},
        lambda event: None,
        ApiConfig(port=0, api_token="secret"),
    )
    server.start()
    assert server.address is not None
    connection = HTTPConnection(*server.address)
    try:
        connection.request(
            "POST",
            "/api/interactions",
            body=json.dumps({"action": "play"}),
            headers={"Content-Type": "application/json"},
        )
        assert connection.getresponse().status == 401
    finally:
        connection.close()
        server.stop()
