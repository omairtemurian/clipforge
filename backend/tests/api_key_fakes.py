"""Helpers of the public API tests (tests only): API keys made through the
owner's endpoint."""

from fastapi.testclient import TestClient


def make_key(client: TestClient, name: str = "agent") -> str:
    """Make an API key through the owner's endpoint and return the key."""
    response = client.post("/api/api-keys", json={"name": name})
    assert response.status_code == 201, response.text
    key: str = response.json()["key"]
    return key
