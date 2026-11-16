"""Assertions shared by the API tests (tests only)."""

import httpx


def assert_error(response: httpx.Response, status: int, code: str) -> str:
    """Check that response is the JSON error {error, message}; return message."""
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error", "message"}
    assert body["error"] == code
    assert isinstance(body["message"], str) and body["message"]
    return str(body["message"])
