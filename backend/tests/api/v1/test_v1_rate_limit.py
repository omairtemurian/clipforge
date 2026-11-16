"""Tests of the rate limit of the public API: api_rate_limit_per_min
requests per key per minute, then 429 rate_limited with Retry-After."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from api_key_fakes import make_key
from apihelpers import assert_error
from clipforge import config
from clipforge.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def limited(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client of an app that allows 3 requests per key per minute."""
    settings = config.settings.model_copy(update={"api_rate_limit_per_min": 3})
    monkeypatch.setattr(config, "settings", settings)
    with TestClient(create_app(run_worker=False, caption_previews=False)) as client:
        yield client


def test_a_key_over_its_rate_is_429_with_retry_after(limited: TestClient) -> None:
    first, second = make_key(limited, "one"), make_key(limited, "two")

    answers = [
        limited.get("/api/v1/projects", headers={"X-API-Key": first}).status_code
        for _ in range(3)
    ]
    over = limited.get("/api/v1/posts", headers={"Authorization": f"Bearer {first}"})
    other = limited.get("/api/v1/projects", headers={"X-API-Key": second})
    own = [limited.get("/api/projects").status_code for _ in range(5)]

    assert answers == [200, 200, 200]
    assert "3 per minute" in assert_error(over, 429, "rate_limited")
    assert 1 <= int(over.headers["retry-after"]) <= 60
    assert other.status_code == 200
    assert own == [200] * 5
