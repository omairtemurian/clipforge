"""Tests of GET /clips/{id}/filmstrip and /clips/{id}/waveform, the
pictures and sound of the editor's timeline."""

from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge.ffmpeg import probe_media
from clipforge.pipeline import preview_assets
from clipforge.pipeline.preview_assets import PEAKS_PER_SECOND, Waveform
from clipforge.preview import previews_dir
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine


@pytest.fixture
def ffmpeg_runs(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record the ffmpeg runs of preview_assets (they still run)."""
    runs: list[object] = []
    real = preview_assets.run_ffmpeg

    def spy(*args: Any, **kwargs: Any) -> Any:
        runs.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(preview_assets, "run_ffmpeg", spy)
    return runs


def test_the_filmstrip_covers_the_clip_with_30_s_around_it_once(
    client: TestClient, api_engine: Engine, sample_mp4: Path, ffmpeg_runs: list[object]
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    first = client.get(f"/api/clips/{clip_id}/filmstrip")

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    # Clip 10-12.5 s: the source from 0 to 42.5 s, a tile a second.
    assert first.headers["x-filmstrip-start"] == "0.000"
    assert float(first.headers["x-filmstrip-interval"]) == 1.0
    assert first.headers["x-filmstrip-count"] == "43"
    (sprite,) = previews_dir(project_id).glob(f"{clip_id}-filmstrip-*.jpg")
    assert first.content == sprite.read_bytes()
    assert probe_media(sprite).width == 43 * 160
    assert len(ffmpeg_runs) == 1

    second = client.get(f"/api/clips/{clip_id}/filmstrip")

    assert second.content == first.content
    assert second.headers["x-filmstrip-count"] == "43"
    assert len(ffmpeg_runs) == 1


def test_the_waveform_has_peaks_over_the_clip_with_30_s_around_it_once(
    client: TestClient, api_engine: Engine, sample_mp4: Path, ffmpeg_runs: list[object]
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    first = client.get(f"/api/clips/{clip_id}/waveform")

    assert first.status_code == 200
    wave = Waveform.model_validate(first.json())
    assert (wave.start, wave.end, wave.peaks_per_second) == (0.0, 42.5, 50)
    assert len(wave.peaks) == round(42.5 * PEAKS_PER_SECOND)
    assert 0.05 < max(wave.peaks) <= 1.0
    assert len(ffmpeg_runs) == 1

    second = client.get(f"/api/clips/{clip_id}/waveform")

    assert second.json() == first.json()
    assert len(ffmpeg_runs) == 1


def test_an_edited_clip_gets_a_new_filmstrip(
    client: TestClient, api_engine: Engine, sample_mp4: Path, ffmpeg_runs: list[object]
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    assert client.get(f"/api/clips/{clip_id}/filmstrip").status_code == 200

    assert client.patch(f"/api/clips/{clip_id}", json={"end": 20.0}).status_code == 200
    response = client.get(f"/api/clips/{clip_id}/filmstrip")

    assert response.headers["x-filmstrip-count"] == "50"
    assert len(ffmpeg_runs) == 2
    assert len(list(previews_dir(project_id).glob(f"{clip_id}-filmstrip-*"))) == 1


@pytest.mark.parametrize("asset", ["filmstrip", "waveform"])
def test_timeline_assets_need_a_clip_with_a_source(
    client: TestClient, api_engine: Engine, sample_mp4: Path, asset: str
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    assert_error(client.get(f"/api/clips/42/{asset}"), 404, "not_found")
    no_job = client.get(f"/api/clips/{clip_id}/{asset}")
    assert "no process job" in assert_error(no_job, 409, "conflict")
    work = add_work(api_engine, project_id, sample_mp4)
    (work / "source.mp4").unlink()
    missing = client.get(f"/api/clips/{clip_id}/{asset}")
    assert "source.mp4" in assert_error(missing, 409, "conflict")
    assert_error(client.get(f"/api/clips/x/{asset}"), 422, "validation_error")
