"""Fixtures of the publisher framework tests."""

from pathlib import Path

import pytest
from clipforge.token_store import TokenStore
from seed import add_clip, add_project
from social_fakes import clip_of, set_rights, write_video
from sqlalchemy import Engine


@pytest.fixture
def store(data_dir: Path) -> TokenStore:
    return TokenStore.from_settings()


@pytest.fixture
def clip_id(engine: Engine) -> int:
    """A rendered clip (its video exists) of a project with source rights."""
    project_id = add_project(engine)
    set_rights(engine, project_id, "own")
    clip_id = add_clip(engine, project_id, "rendered", 70)
    clip = clip_of(engine, clip_id)
    assert clip.output_path is not None
    write_video(Path(clip.output_path))
    return clip_id
