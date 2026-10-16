"""Homework 2: the endpoint takes identity from the database and the session.

Offline: no Langfuse, Docker, or model key. Both requests are rejected before
the agent runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import app as server_app


@pytest.fixture
def client(world: dict, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    server_app._SESSIONS.clear()

    async def no_model(*args, **kwargs):
        raise AssertionError("the agent must not run for a rejected request")

    monkeypatch.setattr(server_app.Runner, "run", no_model)
    return TestClient(server_app.app)  # no `with`: skips the tracing setup


def test_create_session_rejects_role_that_differs_from_database(client: TestClient) -> None:
    # User 1 is a shopper in the database and claims to be support.
    response = client.post("/sessions", json={"user_id": 1, "role": "support"})

    assert response.status_code == 403
    assert server_app._SESSIONS == {}


def test_token_for_one_session_cannot_authorize_another(client: TestClient) -> None:
    first = client.post("/sessions", json={"user_id": 1, "role": "shopper"}).json()
    second = client.post("/sessions", json={"user_id": 2, "role": "shopper"}).json()

    response = client.post(
        f"/sessions/{second['session_id']}/messages",
        json={"message": "Show my recent orders."},
        headers={"Authorization": f"Bearer {first['token']}"},
    )

    assert response.status_code == 403
