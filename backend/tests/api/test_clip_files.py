"""Tests of the clip file endpoints: render, preview and the downloads."""

import io
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from apihelpers import assert_error
from clipforge.ffmpeg import probe_media
from clipforge.models import Job
from clipforge.pipeline import render
from clipforge.pipeline.export import srt_path
from clipforge.pipeline.render import clip_output
from clipforge.preview import previews_dir
from fastapi.testclient import TestClient
from seed import add_clip, add_plan, add_project, add_work
from sqlalchemy import Engine


@pytest.fixture
def ffmpeg_runs(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record the ffmpeg runs of render_clip (they still run)."""
    runs: list[object] = []
    real = render.run_ffmpeg

    def spy(*args: Any, **kwargs: Any) -> Any:
        runs.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(render, "run_ffmpeg", spy)
    return runs


def rendered_clip(engine: Engine, project_id: int, title: str = "Pizza night!") -> int:
    """Add a rendered clip whose video file holds a few bytes; return its id."""
    clip_id = add_clip(engine, project_id, "rendered", 80, title)
    video = clip_output(project_id, clip_id)
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"not really an mp4")
    return clip_id


def test_render_queues_one_render_job_of_the_clip(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    response = client.post(f"/api/clips/{clip_id}/render")

    assert response.status_code == 202
    job = Job.model_validate(response.json())
    assert (job.kind, job.clip_id, job.project_id, job.status) == (
        "render",
        clip_id,
        project_id,
        "queued",
    )
    again = client.post(f"/api/clips/{clip_id}/render")
    assert Job.model_validate(again.json()).id == job.id


def test_render_needs_a_clip_of_a_processed_project(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    assert_error(client.post("/api/clips/42/render"), 404, "not_found")
    response = client.post(f"/api/clips/{clip_id}/render")
    assert "no process job" in assert_error(response, 409, "conflict")
    assert_error(client.post("/api/clips/x/render"), 422, "validation_error")


def test_the_preview_is_rendered_at_540p_once_per_edit(
    client: TestClient, api_engine: Engine, sample_mp4: Path, ffmpeg_runs: list[object]
) -> None:
    project_id = add_project(api_engine)
    work = add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    add_plan(work, clip_id)

    first = client.get(f"/api/clips/{clip_id}/preview")

    assert first.status_code == 200
    assert first.headers["content-type"] == "video/mp4"
    (preview,) = previews_dir(project_id).iterdir()
    info = probe_media(preview)
    assert (info.width, info.height, info.video_codec) == (540, 960, "h264")
    assert abs(info.duration - 2.5) <= 0.2
    assert first.content == preview.read_bytes()
    runs = len(ffmpeg_runs)
    assert runs >= 1

    second = client.get(f"/api/clips/{clip_id}/preview")

    assert second.content == first.content
    assert len(ffmpeg_runs) == runs

    edit = {"cut_ranges": [[11.0, 11.5]]}
    assert client.patch(f"/api/clips/{clip_id}", json=edit).status_code == 200
    third = client.get(f"/api/clips/{clip_id}/preview")

    assert len(ffmpeg_runs) > runs
    (edited,) = previews_dir(project_id).iterdir()
    assert edited != preview and third.content == edited.read_bytes()
    assert abs(probe_media(edited).duration - 2.0) <= 0.2
    assert not list(work.glob("*.ass"))


def test_a_preview_needs_a_clip_with_a_crop_plan(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    assert_error(client.get("/api/clips/42/preview"), 404, "not_found")
    assert_error(client.get(f"/api/clips/{clip_id}/preview"), 409, "conflict")
    add_work(api_engine, project_id, sample_mp4)
    response = client.get(f"/api/clips/{clip_id}/preview")
    assert "crop_" in assert_error(response, 409, "conflict")
    assert_error(client.get("/api/clips/x/preview"), 422, "validation_error")


def test_a_rendered_clip_is_downloaded_under_its_title(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    clip_id = rendered_clip(api_engine, project_id)

    response = client.get(f"/api/clips/{clip_id}/download")

    assert response.status_code == 200
    assert response.content == b"not really an mp4"
    assert response.headers["content-type"] == "video/mp4"
    disposition = response.headers["content-disposition"]
    assert disposition == f'attachment; filename="{clip_id}-pizza-night.mp4"'


def test_only_a_rendered_clip_with_its_file_is_downloaded(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    candidate = add_clip(api_engine, project_id, "candidate", 80)
    gone = add_clip(api_engine, project_id, "rendered", 80)

    assert_error(client.get("/api/clips/42/download"), 404, "not_found")
    for clip_id in (candidate, gone):
        response = client.get(f"/api/clips/{clip_id}/download")
        assert "no rendered video" in assert_error(response, 404, "not_found")
    assert_error(client.get("/api/clips/x/download"), 422, "validation_error")


def test_the_srt_of_a_rendered_clip_is_served_or_written(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = rendered_clip(api_engine, project_id, "!!!")
    srt = srt_path(clip_output(project_id, clip_id))

    written = client.get(f"/api/clips/{clip_id}/srt")

    assert written.status_code == 200
    assert written.headers["content-type"].startswith("application/x-subrip")
    assert f'filename="{clip_id}.srt"' in written.headers["content-disposition"]
    assert written.text.startswith("1\n00:00:00,090 --> 00:00:00,500\nsaid,\n")
    assert written.text == srt.read_text("utf-8")
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nKept\n", "utf-8")
    assert "Kept" in client.get(f"/api/clips/{clip_id}/srt").text


def test_an_srt_needs_a_rendered_clip(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    assert_error(client.get("/api/clips/42/srt"), 404, "not_found")
    assert_error(client.get(f"/api/clips/{clip_id}/srt"), 404, "not_found")
    assert_error(client.get("/api/clips/x/srt"), 422, "validation_error")


def test_the_zip_holds_the_rendered_clips(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = rendered_clip(api_engine, project_id)
    add_clip(api_engine, project_id, "candidate", 90)

    response = client.get(f"/api/projects/{project_id}/download.zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        f'filename="clipforge-{project_id}.zip"'
        in (response.headers["content-disposition"])
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert names == [f"{clip_id}.mp4", f"{clip_id}.srt", f"{clip_id}.json"]


def test_a_zip_needs_a_project_with_rendered_clips(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_clip(api_engine, project_id, "candidate", 90)
    url = f"/api/projects/{project_id}/download.zip"

    assert_error(client.get("/api/projects/42/download.zip"), 404, "not_found")
    assert "no process job" in assert_error(client.get(url), 409, "conflict")
    add_work(api_engine, project_id, sample_mp4)
    assert "no rendered clips" in assert_error(client.get(url), 409, "conflict")
    bad = client.get("/api/projects/x/download.zip")
    assert_error(bad, 422, "validation_error")


def test_the_premiere_xml_has_a_sequence_per_clip(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    add_clip(api_engine, project_id, "candidate", 70, "Second")
    add_clip(api_engine, project_id, "rendered", 90, "First")

    response = client.get(f"/api/projects/{project_id}/premiere.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ElementTree.fromstring(response.content)
    names = [seq.findtext("name") for seq in root.iter("sequence")]
    assert root.tag == "xmeml" and names == ["01 First", "02 Second"]


def test_a_premiere_xml_needs_a_project_with_clips(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    url = f"/api/projects/{project_id}/premiere.xml"

    assert_error(client.get("/api/projects/42/premiere.xml"), 404, "not_found")
    assert "no process job" in assert_error(client.get(url), 409, "conflict")
    add_work(api_engine, project_id, sample_mp4)
    assert "no clips" in assert_error(client.get(url), 409, "conflict")
    bad = client.get("/api/projects/x/premiere.xml")
    assert_error(bad, 422, "validation_error")
