"""Tests of the clip API on a migrated v1 database and of PATCH moving a
clip's segments (migration 004_v2_timeline)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.db import ClipRow, create_db_engine
from clipforge.models import Clip, TrackItem
from clipforge.timeline import timeline_of, video_items
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import V1_SPANS, migrate_to_v1, seed_v1


def stored_segments(engine: Engine, clip_id: int) -> list[tuple[float, float]]:
    """Return the segments of clip clip_id as the database has them."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id).segments


@pytest.fixture
def v1_clip_ids(data_dir: Path, tmp_path: Path) -> list[int]:
    """Clips of a v1 database in the data directory, not yet migrated."""
    engine = create_db_engine()
    try:
        migrate_to_v1(engine, tmp_path)
        return seed_v1(engine)
    finally:
        engine.dispose()


@pytest.fixture
def v1_client(v1_clip_ids: list[int]) -> Iterator[TestClient]:
    """A client of an app started on the v1 database, which it migrates."""
    app = create_app(run_worker=False, caption_previews=False)
    with TestClient(app) as test_client:
        yield test_client


def test_migrated_v1_clips_keep_their_start_and_end_in_the_api(
    v1_client: TestClient, v1_clip_ids: list[int]
) -> None:
    for clip_id, (start, end) in zip(v1_clip_ids, V1_SPANS, strict=True):
        response = v1_client.get(f"/api/clips/{clip_id}")

        assert response.status_code == 200
        body = response.json()
        assert (body["start"], body["end"]) == (start, end)
        assert body["segments"] == [[start, end]]
        item = {"id": "video-0", "kind": "source", "asset_id": None, "props": {}}
        assert body["tracks"]["video"] == [item | {"start": start, "end": end}]
    listed = v1_client.get("/api/projects/1/clips?sort=duration").json()
    assert [item["id"] for item in listed] == v1_clip_ids


def test_patching_start_and_end_moves_the_segment_and_video_track(
    v1_client: TestClient, v1_clip_ids: list[int]
) -> None:
    clip_id = v1_clip_ids[0]

    response = v1_client.patch(f"/api/clips/{clip_id}", json={"end": 14.0})

    assert response.status_code == 200
    clip = Clip.model_validate(response.json())
    assert clip.segments == [(10.0, 14.0)]
    assert clip.tracks == timeline_of([(10.0, 14.0)])
    assert (response.json()["start"], response.json()["end"]) == (10.0, 14.0)


def test_patching_the_span_keeps_the_other_tracks_and_inner_segments(
    client: TestClient, api_engine: Engine
) -> None:
    segments = [(10.0, 12.0), (20.0, 25.0)]
    voiceover = TrackItem(id="vo-0", kind="source", start=1.0, end=2.0)
    tracks = timeline_of(segments).model_copy(update={"voiceover": [voiceover]})
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    with Session(api_engine) as session:
        row = session.get_one(ClipRow, clip_id)
        row.segments, row.tracks = segments, tracks
        session.add(row)
        session.commit()

    response = client.patch(f"/api/clips/{clip_id}", json={"start": 9.0, "end": 23.0})

    assert response.status_code == 200
    clip = Clip.model_validate(response.json())
    assert clip.segments == [(9.0, 12.0), (20.0, 23.0)]
    assert clip.tracks.video == video_items(clip.segments)
    assert clip.tracks.voiceover == [voiceover]

    emptied = client.patch(f"/api/clips/{clip_id}", json={"start": 12.0})
    assert "not valid" in assert_error(emptied, 422, "validation_error")
    assert stored_segments(api_engine, clip_id) == clip.segments
