"""Tests of Pro Edit overlays with ffmpeg (SPEC-v3 1.3/3.3, TASK-212).

Window: a still testsrc2 clip with a screen-anchored skull (pop) and an
emoji (fade) is compared with a render without items (both lossless): the
frames that differ are exactly the items' windows, and the skull's bone
color is at its planned place.

Face anchor: a still grey frame with a pure blue 64 px "face" sliding left
(x = 600 - 25 t px at t s of the source); the clip is 1-5 s of it, framed
9:16 through a fixed window (x 400 to 804) whose crop plan sees the face
as the subject. A red ring (procedural "circle") is anchored to the face
through a zoom punch and a shake: on every frame of its window the ring's
center (the mean of its red pixels) is within FACE_TOLERANCE_PX of the
face's center (the mean of its blue pixels), and no frame outside the
window has red in it. The face is drawn in RGB (overlay format=rgb): on
yuv420p, overlay would move it in steps of 2 pixels.
"""

from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CropKeyframe, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import plan_crop
from clipforge.proedit.overlays.procedural import BONE
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.run import render_plan
from clipforge.proedit.render.timing import frame_range
from edl_fakes import item, plan
from frames import Pixels
from proedit_render import CLIP, LOSSLESS, all_frames, rendered, source_video

FPS = 30
SIZE = (540, 960)
FRAMES = 120
# The ring's center from the face's: the face moves in whole source pixels
# (1.34 px here), the ring in whole frame pixels, and h264's chroma blurs
# both edges (measured: at most 1.9 px; docs/decisions.md).
FACE_TOLERANCE_PX = 3.0
BONE_TOLERANCE = 16
SKULL = item(
    1,
    "overlay",
    1.0,
    2.0,
    params={"asset": "skull", "x": 0.5, "y": 0.4, "scale": 0.4, "animation": "pop"},
)
EMOJI = item(
    2,
    "overlay",
    2.5,
    3.2,
    params={"asset": "emoji:💀", "x": 0.3, "y": 0.75, "animation": "fade"},
)
RING = item(
    3,
    "overlay",
    0.3,
    2.4,
    params={"asset": "circle", "anchor": "face", "scale": 2.0, "animation": "none"},
)
FACE_ITEMS = [
    RING,
    item(4, "zoom_punch", 0.6, 1.2, params={"scale": 1.3, "ease_frames": 3}),
    item(5, "shake", 1.5, 2.1, params={"strength": 0.8, "seed": 7}),
]


def window(found: object) -> range:
    """The frames of an item."""
    assert hasattr(found, "t_start") and hasattr(found, "t_end")
    return range(*frame_range(found.t_start, found.t_end, FPS))


@pytest.fixture(scope="module")
def screen_renders(
    tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path
) -> tuple[list[Pixels], list[Pixels]]:
    """Every frame of the clip without items and with SKULL and EMOJI."""
    directory = tmp_path_factory.mktemp("proedit_overlay_screen")
    source = source_video(directory, "testsrc2=size=1280x720", still=True)
    clean = rendered(directory, source, [], "clean")
    drawn = rendered(directory, source, [SKULL, EMOJI], "drawn")
    return all_frames(clean, SIZE), all_frames(drawn, SIZE)


def test_overlays_show_on_their_windows_only(
    screen_renders: tuple[list[Pixels], list[Pixels]],
) -> None:
    clean, drawn = screen_renders
    assert len(clean) == len(drawn) == FRAMES
    changed = {n for n in range(FRAMES) if not np.array_equal(clean[n], drawn[n])}
    assert changed == set(window(SKULL)) | set(window(EMOJI))


def test_the_skull_is_drawn_where_planned(
    screen_renders: tuple[list[Pixels], list[Pixels]],
) -> None:
    _, drawn = screen_renders
    frame = drawn[window(SKULL)[-1]].astype(np.int16)
    # The skull's forehead: 0.4 * 960 px down, 30 px above its middle.
    forehead = frame[int(0.4 * 960) - 30, 270]
    assert np.abs(forehead - np.array(BONE[:3])).max() <= BONE_TOLERANCE


def test_a_popping_overlay_grows_into_place(
    screen_renders: tuple[list[Pixels], list[Pixels]],
) -> None:
    clean, drawn = screen_renders
    frames = window(SKULL)
    areas = [int(np.any(drawn[n] != clean[n], axis=2).sum()) for n in frames[:8]]
    # Grows, overshoots (ease "back"), then settles at its planned size.
    assert areas[0] < areas[1] < areas[2]
    assert max(areas) > areas[-1] > areas[0]


def face_at(time: float) -> FaceBox:
    """The blue face at time seconds of the source."""
    return FaceBox(
        x=600 - 25 * time, y=300, width=64, height=64, score=1.0, track=0, subject=True
    )


@pytest.fixture(scope="module")
def face_frames(
    tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path
) -> list[Pixels]:
    """Every frame of the clip of the sliding face with FACE_ITEMS."""
    directory = tmp_path_factory.mktemp("proedit_overlay_face")
    source = directory / "source.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=gray:s=1280x720:r=30"]
        + ["-f", "lavfi", "-i", "color=c=blue:s=64x64:r=30"]
        + ["-f", "lavfi", "-i", "sine=frequency=440"]
        + ["-filter_complex", "[0:v][1:v]overlay=x='600-25*t':y=300:format=rgb[v]"]
        + ["-map", "[v]", "-map", "2:a", "-t", "6"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source]
    )
    times = sample_times(CLIP.start, CLIP.end)
    crop = plan_crop(CLIP, "9:16", (1280, 720), [[face_at(t)] for t in times], [])
    keyframes = [CropKeyframe(t=t, x=400, faces=[face_at(t)]) for t in times]
    crop = crop.model_copy(update={"keyframes": keyframes, "y": 0})
    base = ProEditBase(source, CLIP.start, CLIP.end, crop, "fill")
    output = directory / "ring.mp4"
    video = render_plan(
        base, plan(FACE_ITEMS, "pro"), output, quality="proxy", settings=LOSSLESS
    )
    return all_frames(video, SIZE)


def center_of(mask: np.ndarray) -> tuple[float, float]:
    """The mean (x, y) of the true pixels of mask."""
    rows, cols = np.nonzero(mask)
    assert rows.size, "nothing of that color in the frame"
    return float(cols.mean()), float(rows.mean())


def test_a_face_anchored_overlay_follows_the_face(face_frames: list[Pixels]) -> None:
    assert len(face_frames) == FRAMES
    ring = set(window(RING))
    offsets = []
    for n, frame in enumerate(face_frames):
        pixels = frame.astype(np.int16)
        red = (pixels[..., 0] - np.maximum(pixels[..., 1], pixels[..., 2])) > 100
        if n not in ring:
            assert not red.any(), f"frame {n}: red outside the ring's window"
            continue
        blue = (pixels[..., 2] - np.maximum(pixels[..., 0], pixels[..., 1])) > 100
        (rx, ry), (fx, fy) = center_of(red), center_of(blue)
        offsets.append(np.hypot(rx - fx, ry - fy))
        assert offsets[-1] <= FACE_TOLERANCE_PX, f"frame {n}: {offsets[-1]:.2f} px"
    assert len(offsets) == len(ring)
