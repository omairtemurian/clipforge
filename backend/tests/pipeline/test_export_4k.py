"""Tests of exporting a clip at the source's resolution (4K) and for a
platform (SPEC-v2 3.9): export_size, the preset limits and a real export of
a 4K source video."""

import shutil
from fractions import Fraction
from pathlib import Path

import pytest
from clipforge import config
from clipforge.clip_export import ExportedClip, export_clip
from clipforge.db import ClipRow
from clipforge.export_presets import (
    PRESETS,
    RESOLUTIONS,
    check_export,
    export_size,
    get_preset,
)
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import FaceBox
from clipforge.pipeline.export import export_output
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.render import clip_output
from clipforge.pipeline.step import SOURCE, TRANSCRIPT, write_json
from fakes import FIXTURES
from frames import caption_frame, drawn_extent
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

UHD, FHD = (3840, 2160), (1920, 1080)
START, END = 0.0, 2.5


def test_a_4k_source_exports_at_3840x2160() -> None:
    assert export_size("16:9", UHD) == (3840, 2160)
    assert export_size("16:9", UHD, "2160p") == (3840, 2160)


def test_an_export_is_never_scaled_up_beyond_its_source() -> None:
    assert export_size("16:9", FHD, "2160p") == FHD
    assert export_size("16:9", (1280, 720)) == (1280, 720)
    # 9:16 from 16:9 crops a window of 1215x2160 of a 4K frame.
    width, height = export_size("9:16", UHD)
    assert (width, height) == (1214, 2158)
    assert width <= 1215 and height <= 2160
    assert export_size("9:16", FHD, "2160p") == (606, 1076)


def test_a_resolution_caps_the_shorter_side() -> None:
    assert export_size("16:9", UHD, "1080p") == FHD
    assert export_size("16:9", UHD, "720p") == (1280, 720)
    assert export_size("9:16", UHD, "1080p") == (1080, 1920)
    assert export_size("1:1", UHD, "1440p") == (1440, 1440)
    assert list(RESOLUTIONS) == ["source", "2160p", "1440p", "1080p", "720p"]


@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5", "16:9", "2:1"])
def test_every_export_size_is_even_and_inside_the_source(aspect: str) -> None:
    width, height = export_size(aspect, (3841, 2161))

    assert width % 2 == 0 and height % 2 == 0
    assert width <= 3841 and height <= 2161


def test_a_preset_bounds_the_frame() -> None:
    reels, x, tiktok = (get_preset(name) for name in ("reels", "x", "tiktok"))

    assert export_size("9:16", UHD, preset=reels) == (1214, 2158)
    assert export_size("16:9", UHD, preset=reels) == (1920, 1080)
    assert export_size("9:16", UHD, preset=x) == (720, 1280)
    assert export_size("16:9", UHD, preset=x) == (1280, 720)
    assert export_size("1:1", UHD, preset=x) == (720, 720)
    assert export_size("16:9", UHD, preset=tiktok) == (3840, 2160)


def test_the_presets_hold_the_official_limits() -> None:
    limits = {
        name: (p.max_duration_s, p.max_bytes, p.min_duration_s)
        for name, p in PRESETS.items()
    }

    assert limits == {
        "shorts": (180, 256 * 1000**3, 0),
        "tiktok": (600, 4 * 1000**3, 0),
        "reels": (900, 300 * 1000**2, 3),
        "linkedin": (1800, 500 * 1000**2, 3),
        "x": (1200, 8 * 1000**3, 0.5),
    }
    for preset in PRESETS.values():
        assert preset.source_url.startswith("https://")
        assert preset.checked == "2026-11-02"


def test_check_export_names_what_breaks_a_limit() -> None:
    reels = get_preset("reels")
    shorts = get_preset("shorts")

    assert check_export(reels, (1080, 1920), 30.0, 100 * 1000**2) == []
    assert check_export(reels, (1080, 1920), 901.0, 301 * 1000**2) == [
        "901.0 s is longer than the 900 s Instagram Reels takes",
        "301 MB is larger than the 300 MB Instagram Reels takes",
    ]
    assert check_export(reels, (1080, 1920), 2.0, 1000) == [
        "2.0 s is shorter than the 3 s Instagram Reels needs"
    ]
    assert check_export(shorts, (1080, 1920), 179.0, 1000) == []
    assert check_export(shorts, (1920, 1080), 60.0, 1000) == [
        "a 1920x1080 frame has a shape YouTube Shorts refuses"
    ]
    assert check_export(get_preset("tiktok"), (300, 400), 10.0, 1000) == [
        "300x400 is under the 360 pixels a side TikTok needs"
    ]


def test_unknown_resolutions_and_presets_are_refused() -> None:
    with pytest.raises(ValueError, match="unknown resolution '8k'"):
        export_size("16:9", UHD, "8k")
    with pytest.raises(ValueError, match="unknown export preset 'vine'"):
        get_preset("vine")


def test_the_shapes_a_preset_takes_are_fractions() -> None:
    assert get_preset("shorts").ratio == (Fraction(0), Fraction(1))


@pytest.fixture(scope="module")
def source_4k(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3 s 3840x2160 video at 10 frames a second, with silent sound."""
    path = tmp_path_factory.mktemp("uhd") / "uhd.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=size=3840x2160:rate=10:duration=3"]
        + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "3"]
        + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", "-shortest", path]
    )
    return path


@pytest.fixture
def staged(
    engine: Engine, tmp_path: Path, source_4k: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, Path]:
    """A project with one clip (0-2.5 s, 16:9) whose work directory holds the
    4K source, the transcript and the clip's crop plan; returns the clip id
    and the work directory. Renders use the fastest x264 preset."""
    render = config.settings.render.model_copy(update={"preset": "ultrafast"})
    monkeypatch.setattr(
        config, "settings", config.settings.model_copy(update={"render": render})
    )
    work = tmp_path / "work"
    work.mkdir()
    shutil.copyfile(source_4k, work / SOURCE)
    shutil.copyfile(FIXTURES / TRANSCRIPT, work / TRANSCRIPT)
    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "candidate", 70, start=START, end=END)
    no_faces: list[list[FaceBox]] = [[] for _ in sample_times(START, END)]
    plan = plan_crop(ClipSpan(clip_id, START, END), "16:9", UHD, no_faces, [])
    write_json(crop_path(work, clip_id), plan)
    return clip_id, work


def test_a_4k_clip_exports_at_3840x2160_and_leaves_its_own_video_alone(
    engine: Engine, staged: tuple[int, Path]
) -> None:
    clip_id, work = staged

    exported = export_clip(engine, clip_id, work)

    info = probe_media(exported.path)
    assert (info.width, info.height) == (3840, 2160)
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == (
        "h264",
        "yuv420p",
        "aac",
    )
    assert info.duration == pytest.approx(END - START, abs=0.2)
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        project_id = row.project_id
        assert (row.status, row.output_path) == ("candidate", None)
    assert exported.path == export_output(project_id, clip_id, "source")
    assert exported == ExportedClip(
        exported.path, 3840, 2160, info.duration, exported.size_bytes, None, []
    )
    assert exported.size_bytes == exported.path.stat().st_size
    assert not clip_output(project_id, clip_id).exists()


def test_the_resolution_chooses_the_frame_of_the_export(
    engine: Engine, staged: tuple[int, Path]
) -> None:
    clip_id, work = staged

    exported = export_clip(engine, clip_id, work, resolution="1080p")

    assert (exported.width, exported.height) == FHD
    assert exported.path.name == f"{clip_id}-1080p.mp4"


def test_a_preset_export_fits_the_platform_and_reports_what_does_not(
    engine: Engine, staged: tuple[int, Path]
) -> None:
    clip_id, work = staged

    reels = export_clip(engine, clip_id, work, preset="reels")
    shorts = export_clip(engine, clip_id, work, preset="shorts")

    assert (reels.width, reels.height) == (1920, 1080)
    assert reels.path.name == f"{clip_id}-reels.mp4"
    # 2.5 s is under the 3 s that Reels needs; a 16:9 frame is not a Short.
    assert reels.problems == ["2.5 s is shorter than the 3 s Instagram Reels needs"]
    assert shorts.problems == ["a 3840x2160 frame has a shape YouTube Shorts refuses"]


def test_an_export_with_an_unknown_resolution_or_preset_renders_nothing(
    engine: Engine, staged: tuple[int, Path]
) -> None:
    clip_id, work = staged

    with pytest.raises(ValueError, match="unknown resolution"):
        export_clip(engine, clip_id, work, resolution="8k")
    with pytest.raises(ValueError, match="unknown export preset"):
        export_clip(engine, clip_id, work, preset="vine")

    assert not export_output(1, clip_id, "8k").parent.exists()


def test_captions_keep_their_share_of_the_frame_at_4k(
    engine: Engine, staged: tuple[int, Path]
) -> None:
    clip_id, work = staged
    export_clip(engine, clip_id, work)
    ass = work / f"captions_{clip_id}.ass"

    small = drawn_extent(caption_frame(ass, FHD, 1.0))
    large = drawn_extent(caption_frame(ass, UHD, 1.0))

    assert small[0] > 100 and small[1] > 20
    assert large[0] == pytest.approx(small[0] * 2, rel=0.03)
    assert large[1] == pytest.approx(small[1] * 2, rel=0.05)
