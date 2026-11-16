"""Tests of a clip rendered with one item on each track of its timeline
(SPEC-v2 3.5, pipeline/timeline_graph): with ffmpeg, the B-roll, overlay
and text show only in their items' windows of the rendered clip (after its
cuts), the music, sound effect and voiceover sound only in theirs, and
ffprobe sees the clip's length (within 0.2 s)."""

import re
from pathlib import Path

import pytest
from builders import make_clip
from clipforge.assets import add_asset
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import FaceBox, TrackItem
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.timeline import clip_layers, timeline_of
from sqlalchemy import Engine
from sqlmodel import Session

SIZE = (180, 320)
# The clip is 0-4 s of the source; the cut 0.2-0.6 s leaves 3.6 s.
CUTS = [(0.2, 0.6)]
LENGTH = 3.6
# ffmpeg's colours: "green" is #008000.
BLUE, RED, GREEN, WHITE = (0, 0, 255), (255, 0, 0), (0, 128, 0), (255, 255, 255)


def lavfi(path: Path, *sources: str, args: tuple[str, ...] = ()) -> Path:
    """Encode the lavfi sources into path and return it."""
    inputs = [arg for source in sources for arg in ("-f", "lavfi", "-i", source)]
    run_ffmpeg([*inputs, *args, path])
    return path


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """A 4 s blue 320x240 source with silence, a red video, a green PNG and
    a 1 kHz tone at 48 kHz."""
    folder = tmp_path_factory.mktemp("timeline")
    h264 = ("-c:v", "libx264", "-pix_fmt", "yuv420p")
    return {
        "source": lavfi(
            folder / "source.mp4",
            "color=c=blue:size=320x240:rate=30:duration=4",
            "anullsrc=channel_layout=mono:sample_rate=48000:duration=4",
            args=(*h264, "-c:a", "aac", "-shortest"),
        ),
        "red": lavfi(
            folder / "red.mp4", "color=c=red:size=200x100:rate=25:duration=3", args=h264
        ),
        "green": lavfi(
            folder / "green.png", "color=c=green:size=64x64", args=("-frames:v", "1")
        ),
        "tone": lavfi(
            folder / "tone.m4a", "sine=frequency=1000:sample_rate=48000:duration=3"
        ),
    }


def pixel(video: Path, t: float, x: int, y: int) -> tuple[int, ...]:
    """Return the RGB colour of video's frame at t seconds around (x, y)."""
    raw = run_ffmpeg(
        ["-ss", f"{t}", "-i", video, "-frames:v", "1"]
        + ["-vf", f"crop=4:4:{x - 2}:{y - 2},scale=1:1"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    ).stdout
    return tuple(raw[:3])


def near(colour: tuple[int, ...], expected: tuple[int, int, int]) -> bool:
    """Return whether colour is expected, give or take compression."""
    return all(abs(a - b) <= 40 for a, b in zip(colour, expected, strict=True))


def rms_db(video: Path, start: float, length: float) -> float:
    """Return the RMS level in dBFS of video's sound from start for length
    seconds, as astats measures it."""
    stderr = run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{length}", "-i", video, "-map", "0:a:0"]
        + ["-af", "astats=measure_perchannel=none:measure_overall=RMS_level"]
        + ["-f", "null", "-"],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"RMS level dB: (\S+)", stderr)[-1])


def entry(
    item_id: str, kind: str, start: float, end: float, **fields: object
) -> TrackItem:
    """Return a track item."""
    return TrackItem.model_validate(
        {"id": item_id, "kind": kind, "start": start, "end": end} | fields
    )


@pytest.fixture
def rendered(engine: Engine, media: dict[str, Path], tmp_path: Path) -> Path:
    """The clip 0-4 s of the source with CUTS and one item on each track,
    rendered at SIZE with its layers from the asset library."""
    with Session(engine) as session:
        ids = {
            name: add_asset(session, kind, str(media[name]), "CC0-1.0").id
            for name, kind in (("red", "video"), ("green", "image"), ("tone", "music"))
        }
        tracks = timeline_of([(0.0, 4.0)]).model_copy(
            update={
                "broll": [entry("b", "video", 0.5, 1.5, asset_id=ids["red"])],
                "overlays": [
                    entry("o", "image", 2.0, 3.0, asset_id=ids["green"],
                          props={"width": 0.5, "y": 0.75}),
                ],
                "text": [
                    entry("t", "text", 0.0, 3.6,
                          props={"text": "WWWW", "size": 0.2, "y": 0.25}),
                ],
                "music": [entry("m", "audio", 1.0, 1.8, asset_id=ids["tone"])],
                "sfx": [entry("s", "audio", 2.2, 2.4, asset_id=ids["tone"])],
                "voiceover": [
                    entry("v", "audio", 2.8, 3.4, asset_id=ids["tone"],
                          props={"volume": 0.5}),
                ],
            }
        )  # fmt: skip
        clip = make_clip("minimal", start=0.0, end=4.0, cut_ranges=CUTS, tracks=tracks)
        layers = clip_layers(session, clip, 30)
    assert len(layers) == 6
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 4.0)]
    plan = plan_crop(ClipSpan(7, 0.0, 4.0), "9:16", (320, 240), faces, [])
    return render_clip(
        media["source"],
        tmp_path / "clip.mp4",
        clip.start,
        clip.end,
        plan,
        "fill",
        RenderSettings(),
        cut_ranges=CUTS,
        size=SIZE,
        layers=layers,
    )


def test_one_item_per_track_renders_at_the_clips_length(rendered: Path) -> None:
    info = probe_media(rendered)

    assert (info.width, info.height) == SIZE
    assert abs(info.duration - LENGTH) <= 0.2
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")


def test_visual_layers_show_in_their_windows(rendered: Path) -> None:
    # The middle of the frame: B-roll at 0.5-1.5 s, then the source; the
    # overlay 90 px wide at 3/4 of the height from 2 to 3 s.
    assert near(pixel(rendered, 0.25, 90, 160), BLUE)
    assert near(pixel(rendered, 1.0, 90, 160), RED)
    assert near(pixel(rendered, 1.8, 90, 160), BLUE)
    assert near(pixel(rendered, 1.8, 90, 240), BLUE)
    assert near(pixel(rendered, 2.5, 90, 240), GREEN)
    assert near(pixel(rendered, 3.3, 90, 240), BLUE)
    # The text's white strokes at a quarter of the height, over the B-roll.
    text_row = [pixel(rendered, 1.0, x, 80) for x in range(30, 150, 4)]
    assert any(near(colour, WHITE) for colour in text_row)


def test_sound_layers_play_in_their_windows(rendered: Path) -> None:
    silent = rms_db(rendered, 0.3, 0.5)
    music = rms_db(rendered, 1.1, 0.6)
    sfx = rms_db(rendered, 2.22, 0.15)
    voiceover = rms_db(rendered, 2.9, 0.4)
    between = rms_db(rendered, 2.5, 0.25)

    assert silent < -80 and between < -80
    # sine's tone is 1/8 full scale: about -21 dBFS RMS.
    assert music == pytest.approx(-21.0, abs=1.0)
    assert sfx == pytest.approx(-21.0, abs=1.0)
    # Half the volume: about 6 dB below the music.
    assert voiceover == pytest.approx(music - 6.0, abs=1.0)
