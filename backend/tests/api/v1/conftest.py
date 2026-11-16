"""Fixtures of the public API (/api/v1) tests: an API key made by the owner."""

import pytest
from api_key_fakes import make_key
from fastapi.testclient import TestClient


@pytest.fixture
def api_key(client: TestClient) -> str:
    """A valid API key of the app under test."""
    return make_key(client)


@pytest.fixture
def agent(api_key: str) -> dict[str, str]:
    """The headers of an agent's request with a valid key."""
    return {"X-API-Key": api_key}
