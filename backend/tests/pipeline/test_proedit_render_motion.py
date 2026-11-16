"""Tests of the Pro Edit zoom and pan with ffmpeg (SPEC-v3 3.3, TASK-209).

The source is a still (one grey testsrc2 frame, blurred noise added so
the frame tracker finds corners everywhere, for 6 s) with a pure red
64 px "face" sliding left (x = 760 - 25 t px at t s of the source) and a
tone; the clip is 1-5 s of it, framed 9:16 through a fixed window (x 400 to
804) whose crop plan sees that face as the subject, so the face starts at
the window's right edge. Each zoom and pan item's frames are measured
against a render with no items: the zoom scale (pair_motion's similarity
between the two frames) is the one its params plan within 3 %, and the red
face is whole inside every zoomed frame, away from its edges, even where
the item centers the zoom on the frame (a centered punch would cut it).
"""

from pathlib import Path

import cv2
import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CropKeyframe, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.proedit.features.motion import pair_motion
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.easing import ease
from clipforge.proedit.render.run import render_plan
from clipforge.proedit.render.timing import frame_range
from edl_fakes import item, plan
from frames import Pixels, numbered_frames

CLIP = ClipSpan(7, 1.0, 5.0)
X264 = RenderSettings(encoder="libx264")
FPS = 30
SIZE = (540, 960)
TOLERANCE = 0.03
# Pixels the face keeps from the frame's edges (FACE_MARGIN is 3 % of the
# window, ~16 px, less the even rounding of the crop and the h264 blur).
EDGE_PX = 8
ITEMS = [
    item(
        1,
        "zoom_punch",
        0.5,
        1.2,
        params={"scale": 1.3, "ease_frames": 3, "ease": "linear", "center": "frame"},
    ),
    item(2, "zoom_push", 1.4, 2.4, params={"scale_from": 1.0, "scale_to": 1.2}),
    item(
        3,
        "zoom_out_reveal",
        2.6,
        3.2,
        params={"scale_from": 1.25, "scale_to": 1.0, "ease": "back"},
    ),
    item(
        4,
        "pan",
        3.3,
        3.9,
        params={
            "from_x": 0.3,
            "from_y": 0.5,
            "to_x": 0.7,
            "to_y": 0.5,
            "scale": 1.2,
            "ease": "linear",
        },
    ),
]


def window(index: int) -> range:
    """The frames of ITEMS[index]."""
    found = ITEMS[index]
    return range(*frame_range(found.t_start, found.t_end, FPS))


def expected_scale(frame: int) -> float:
    """The zoom of frame that ITEMS' params plan (1 outside their windows)."""
    punch, push, reveal, pan = (window(i) for i in range(4))
    if frame in punch:
        k = frame - punch.start
        return 1 + 0.3 * min((k + 1) / 3, 1.0)
    if frame in push:
        return 1 + 0.2 * ease("ease_in_out", (frame - push.start) / (len(push) - 1))
    if frame in reveal:
        p = (frame - reveal.start) / (len(reveal) - 1)
        return max(1.25 - 0.25 * ease("back", p), 1.0)
    return 1.2 if frame in pan else 1.0


def face_at(time: float) -> FaceBox:
    """The red face at time seconds of the source."""
    return FaceBox(
        x=760 - 25 * time, y=300, width=64, height=64, score=1.0, track=0, subject=True
    )


@pytest.fixture(scope="module")
def renders(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """The proxy of CLIP with no items and with ITEMS."""
    directory = tmp_path_factory.mktemp("proedit_motion")
    png, source = directory / "still.png", directory / "source.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=size=1280x720", "-frames:v", "1"]
        + ["-vf", "noise=alls=100:allf=u,gblur=sigma=2", png]
    )
    run_ffmpeg(
        ["-loop", "1", "-framerate", "30", "-i", png]
        + ["-f", "lavfi", "-i", "color=c=red:s=64x64:r=30"]
        + ["-f", "lavfi", "-i", "sine=frequency=440"]
        + ["-filter_complex", "[0:v]hue=s=0[g];[g][1:v]overlay=x='760-25*t':y=300[v]"]
        + ["-map", "[v]", "-map", "2:a", "-t", "6"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source]
    )
    times = sample_times(CLIP.start, CLIP.end)
    crop = plan_crop(CLIP, "9:16", (1280, 720), [[face_at(t)] for t in times], [])
    keyframes = [CropKeyframe(t=t, x=400, faces=[face_at(t)]) for t in times]
    crop = crop.model_copy(update={"keyframes": keyframes, "y": 0})
    base = ProEditBase(source, CLIP.start, CLIP.end, crop, "fill")
    rendered = []
    for name, items in (("base", []), ("zoomed", ITEMS)):
        output = directory / f"{name}.mp4"
        rendered.append(
            render_plan(
                base, plan(items, "pro"), output, quality="proxy", settings=X264
            )
        )
    return rendered[0], rendered[1]


def frames_of(video: Path, numbers: list[int]) -> dict[int, Pixels]:
    """Return frames numbers of video, read 30 at a time (a long select
    expression is too deep for ffmpeg)."""
    found: dict[int, Pixels] = {}
    for start in range(0, len(numbers), 30):
        found |= numbered_frames(video, numbers[start : start + 30])
    return found


def red_box(frame: Pixels) -> tuple[int, int, int, int, int]:
    """Return the left, top, right and bottom pixels of frame's red face and
    its area in pixels."""
    pixels = frame.astype(np.int16)
    red = (pixels[..., 0] - np.maximum(pixels[..., 1], pixels[..., 2])) > 100
    rows, cols = np.flatnonzero(red.any(axis=1)), np.flatnonzero(red.any(axis=0))
    assert rows.size and cols.size, "no red face in the frame"
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]), int(red.sum())


def grey(frame: Pixels) -> Pixels:
    return np.asarray(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), np.uint8)


@pytest.fixture(scope="module")
def measured(
    renders: tuple[Path, Path],
) -> dict[int, tuple[float, tuple[int, int, int, int, int], int]]:
    """For each frame of the items' windows and a few frames around them:
    the measured zoom scale, the zoomed frame's red box and the base
    frame's red area."""
    numbers = sorted(
        {n for i in range(4) for n in window(i)} | {5, 14, 37, 41, 74, 97, 117, 119}
    )
    base, zoomed = (frames_of(video, numbers) for video in renders)
    found = {}
    for n in numbers:
        motion = pair_motion(grey(base[n]), grey(zoomed[n]))
        assert motion is not None, f"frame {n}: no motion estimate"
        found[n] = (motion.scale, red_box(zoomed[n]), red_box(base[n])[4])
    return found


def test_each_frame_zooms_as_planned(
    measured: dict[int, tuple[float, tuple[int, int, int, int, int], int]],
) -> None:
    for n, (scale, _, _) in measured.items():
        assert scale == pytest.approx(expected_scale(n), rel=TOLERANCE), f"frame {n}"
    assert max(measured[n][0] for n in window(0)) == pytest.approx(1.3, rel=0.01)
    assert measured[5][0] == pytest.approx(1.0, abs=0.005)


def test_the_face_is_whole_inside_every_zoomed_frame(
    measured: dict[int, tuple[float, tuple[int, int, int, int, int], int]],
) -> None:
    width, height = SIZE
    for n, (_, (left, top, right, bottom, area), base_area) in measured.items():
        assert left >= EDGE_PX and right <= width - 1 - EDGE_PX, f"frame {n}"
        assert top >= EDGE_PX and bottom <= height - 1 - EDGE_PX, f"frame {n}"
        planned = expected_scale(n) ** 2
        assert area / base_area == pytest.approx(planned, rel=0.1), f"frame {n}"


def test_a_centered_punch_would_have_cut_the_face(renders: tuple[Path, Path]) -> None:
    punch = window(0)
    frames = numbered_frames(renders[0], [punch.start + 5, punch.stop - 1])
    for frame in frames.values():
        right = red_box(frame)[2]
        assert (right - SIZE[0] / 2) * 1.3 + SIZE[0] / 2 > SIZE[0]
