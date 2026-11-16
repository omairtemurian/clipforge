"""Fixtures of the scheduler tests that publish: a token store, a rendered
clip with source rights and a fake wall clock."""

from pathlib import Path

import pytest
from clipforge.token_store import TokenStore
from fake_clock import FakeWallClock
from post_api_fakes import rendered_clip
from post_worker_fakes import START
from sqlalchemy import Engine


@pytest.fixture
def store(data_dir: Path) -> TokenStore:
    return TokenStore.from_settings()


@pytest.fixture
def clip_id(engine: Engine) -> int:
    """A rendered clip (its video exists) of a project with source rights."""
    return rendered_clip(engine)


@pytest.fixture
def clock() -> FakeWallClock:
    return FakeWallClock(START)
