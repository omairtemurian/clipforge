"""Tests of clips.export_project (SPEC 6.12): the zip of a project's rendered
clips, best first, each with its subtitles and fresh metadata."""

import json
import zipfile
from pathlib import Path

import pytest
from builders import SIX, source_meta
from clipforge.clips import ZIP_NAME, export_project
from clipforge.models import Transcript
from clipforge.pipeline.export import metadata_path, srt_path
from clipforge.pipeline.render import clip_output
from clipforge.pipeline.step import META, TRANSCRIPT, StepError, write_json
from seed import add_clip, add_project
from sqlalchemy import Engine

# The meta.json of a downloaded video: config.yaml's credit_template credits
# its channel.
META_DATA = source_meta().model_copy(update={"channel": "Sample Comedian"})


def write_work(work: Path) -> Path:
    """Write the transcript of builders.SIX and META_DATA into work; return it."""
    work.mkdir(parents=True)
    write_json(
        work / TRANSCRIPT, Transcript(language="en", duration=60, segments=[SIX])
    )
    write_json(work / META, META_DATA)
    return work


def test_export_project_zips_the_rendered_clips_best_first(
    engine: Engine, data_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    work = write_work(tmp_path / "work")
    project_id = add_project(engine)
    good = add_clip(engine, project_id, "rendered", 70, "Good")
    best = add_clip(engine, project_id, "rendered", 90, "Best")
    add_clip(engine, project_id, "failed", 95)
    add_clip(engine, project_id, "candidate", 99)
    gone = add_clip(engine, project_id, "rendered", 80)
    clip_output(project_id, good).parent.mkdir(parents=True)
    for clip_id in (good, best):
        clip_output(project_id, clip_id).write_bytes(f"video {clip_id}".encode())
    # The best clip's subtitles belong to its render and stay; its metadata
    # is old and is written again.
    best_video = clip_output(project_id, best)
    srt_path(best_video).write_text("render-time subtitles", encoding="utf-8")
    metadata_path(best_video).write_text('{"title": "Old"}', encoding="utf-8")

    path = export_project(engine, project_id, work)

    assert path == data_dir / "output" / str(project_id) / ZIP_NAME
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == [
            f"{clip_id}{suffix}"
            for clip_id in (best, good)
            for suffix in (".mp4", ".srt", ".json")
        ]
        assert archive.read(f"{best}.mp4") == f"video {best}".encode()
        assert archive.read(f"{best}.srt") == b"render-time subtitles"
        srt = archive.read(f"{good}.srt").decode()
        metadata = json.loads(archive.read(f"{best}.json"))
    assert srt.startswith("1\n00:00:00,000 --> 00:00:00,360\nWait,\n\n2\n")
    assert metadata == {
        "title": "Best",
        "description": "",
        "hashtags": ["food", "pizza", "funny"],
        "credit": "Credit: Sample Comedian",
    }
    assert f"clip {gone} has no rendered video; not zipped" in caplog.messages


def test_export_project_of_no_rendered_clips_is_an_empty_zip(
    engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    add_clip(engine, project_id, "failed", 95)

    path = export_project(engine, project_id, tmp_path)

    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == []
    assert list(path.parent.iterdir()) == [path]


def test_export_project_needs_the_project_and_its_meta(
    engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    with pytest.raises(StepError, match="project 42 not found"):
        export_project(engine, 42, tmp_path)

    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "rendered", 70)
    clip_output(project_id, clip_id).parent.mkdir(parents=True)
    clip_output(project_id, clip_id).write_bytes(b"video")
    srt_path(clip_output(project_id, clip_id)).write_text("subtitles")

    with pytest.raises(StepError, match="meta.json not found; run the ingest"):
        export_project(engine, project_id, tmp_path)
    assert not (data_dir / "output" / str(project_id) / ZIP_NAME).exists()
