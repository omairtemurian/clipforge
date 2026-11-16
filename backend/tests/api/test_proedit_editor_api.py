"""Tests of the Pro Edit editor endpoints (SPEC-v3 3.8): the timing a dragged
item snaps to (frame rate, length, words, the beats of the plan's music
beds) and the variant's rendered video, with their errors."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import config
from clipforge.db import ClipRow
from clipforge.models import EdlItem
from clipforge.proedit.config import ProEditConfig
from fastapi.testclient import TestClient
from proedit_run_fakes import Processed, processed_clip, store_plan, zoom
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

API = "/api/proedit"


@pytest.fixture
def original(api_engine: Engine, sample_mp4: Path) -> Processed:
    return processed_clip(api_engine, sample_mp4)


def bed(id: int, t_start: float, t_end: float, offset: float | None) -> EdlItem:
    return EdlItem(
        id=id,
        kind="music_bed",
        t_start=t_start,
        t_end=t_end,
        params={"asset": "bright_steps", "offset": offset},
        reason="the bed",
    )


def test_the_timing_has_the_clips_words_in_clip_seconds(
    client: TestClient, original: Processed
) -> None:
    response = client.get(f"{API}/clips/{original.clip_id}/timing")

    assert response.status_code == 200, response.text
    timing = response.json()
    assert timing["fps"] == config.settings.render.fps
    assert timing["duration"] == pytest.approx(2.5)
    assert [(w["text"], w["start"]) for w in timing["words"]] == [
        ("said,", pytest.approx(0.09)),
        ("why", pytest.approx(1.1)),
        ("are", pytest.approx(1.51)),
        ("we", pytest.approx(1.92)),
        ("on", pytest.approx(2.25)),
    ]
    assert timing["beats"] == []


def test_the_timing_has_the_beats_of_the_plans_music_beds(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    store_plan(api_engine, original.clip_id, bed(1, 0.0, 1.0, None), zoom(2, 0.5))
    one_bed = client.get(f"{API}/clips/{original.clip_id}/timing").json()["beats"]
    store_plan(
        api_engine,
        original.clip_id,
        bed(1, 0.0, 1.0, None),
        bed(2, 1.4, 2.5, None),
    )

    two_beds = client.get(f"{API}/clips/{original.clip_id}/timing").json()["beats"]

    # Bright Steps is 120 BPM (a beat every 0.5 s from 0), only within each
    # bed; the second bed continues the music, so its beats keep the grid.
    assert one_bed == pytest.approx([0.0, 0.5], abs=0.01)
    assert two_beds == pytest.approx([0.0, 0.5, 1.5, 2.0, 2.5], abs=0.01)
    assert max(two_beds) < 2.5


def test_the_video_is_the_rendered_file_inline(
    client: TestClient, api_engine: Engine, original: Processed, sample_mp4: Path
) -> None:
    with Session(api_engine) as session:
        output = session.get_one(ClipRow, original.clip_id).output_path
    assert output is not None
    missing = client.get(f"{API}/clips/{original.clip_id}/video")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_bytes(sample_mp4.read_bytes())

    response = client.get(f"{API}/clips/{original.clip_id}/video")

    assert_error(missing, 404, "not_found")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert "attachment" not in response.headers.get("content-disposition", "")
    assert response.content == sample_mp4.read_bytes()


def test_the_editor_endpoints_answer_404_and_409(
    client: TestClient, api_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = add_clip(api_engine, add_project(api_engine), "candidate", 50)

    assert_error(client.get(f"{API}/clips/999/timing"), 404, "not_found")
    assert_error(client.get(f"{API}/clips/999/video"), 404, "not_found")
    assert_error(client.get(f"{API}/clips/{bare}/timing"), 409, "conflict")
    assert_error(client.get(f"{API}/clips/{bare}/video"), 404, "not_found")
    off = config.settings.model_copy(update={"proedit": ProEditConfig(enabled=False)})
    monkeypatch.setattr(config, "settings", off)
    assert_error(client.get(f"{API}/clips/{bare}/timing"), 404, "proedit_disabled")
