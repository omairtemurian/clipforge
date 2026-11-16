"""Tests of the Pro Edit shake, speed ramps and slow motion with ffmpeg
(SPEC-v3 3.3 pacing, TASK-210).

Timing: the source is dark with a white bar sliding right 2 px a frame
(60 px/s) and, at 2.7 s and 4.75 s, a white frame and a 1 kHz beep at once;
the clip is 1-5 s of it, framed 9:16 in the middle. The bar's place in a
frame tells the clip time the frame shows (read off a render with no
items), so each frame's content time and speed are measured: the slow-mo
window lasts as planned within a frame and plays at its speed, the ramps
show the clip where their planned speeds take it (within POSITION_FRAMES),
frames outside the windows play the clip as it is, and every flash after a
ramp is within 40 ms of its beep.

Shake: the source is a textured still (grey testsrc2 frame with blurred
noise, so the tracker finds corners everywhere); consecutive frames of the
render go through the affine extractor (features.motion.shake_spans),
which must find a shake in each planned window and none elsewhere.
"""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.proedit.edl import SlowmoItem, SpeedRampItem, parse_item
from clipforge.proedit.features.motion import pair_motion, shake_spans
from clipforge.proedit.render.motion_time import SHAKE_MAX, content_times
from clipforge.proedit.render.run import render_plan
from clipforge.proedit.render.timing import frame_range
from edl_fakes import item, plan
from flashes import beep_times, flash_times, onsets
from frames import Pixels
from proedit_render import base_of

X264 = RenderSettings(encoder="libx264")
FPS = 30
FRAMES = 120
SIZE = (540, 960)
# Motion-compensated frames put the bar within 0.22 frame of plan.
POSITION_FRAMES = 0.35
EVENTS = "between(t,2.6999,2.76)+between(t,4.7499,4.81)"
SLOWMO = item(1, "slowmo", 0.4, 1.4, params={"speed": 0.5, "ramp_s": 0})
RAMP = item(
    2,
    "speed_ramp",
    1.9,
    2.9,
    params={"speed_from": 1.0, "speed_to": 0.3, "ease": "linear"},
)
FAST = item(
    3,
    "speed_ramp",
    3.0,
    3.4,
    params={"speed_from": 1.0, "speed_to": 2.5, "ease": "linear"},
)
TIMED = [SLOWMO, RAMP, FAST]
SHAKE = item(
    1, "shake", 1.0, 2.0, params={"strength": 0.5, "frequency_hz": 8, "seed": 3}
)
SHAKE_ON_ZOOM = item(
    2, "shake", 2.5, 3.3, params={"strength": 0.4, "frequency_hz": 12, "seed": 9}
)
PUNCH = item(3, "zoom_punch", 2.5, 3.3, params={"scale": 1.2, "center": "frame"})
SHAKES = [SHAKE, SHAKE_ON_ZOOM, PUNCH]


def frames_of(found: EdlItem) -> range:
    return range(*frame_range(found.t_start, found.t_end, FPS))


def render_pair(source: Path, items: list[EdlItem]) -> tuple[Path, Path]:
    """The proxies of CLIP of source with no items and with items."""
    rendered = []
    for name, chosen in (("base", []), ("pro", items)):
        output = source.with_name(f"{name}.mp4")
        rendered.append(
            render_plan(
                base_of(source), plan(chosen, "pro"), output, quality="proxy",
                settings=X264,
            )
        )  # fmt: skip
    return rendered[0], rendered[1]


@pytest.fixture(scope="module")
def timed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """The base and the TIMED renders of the sliding-bar source."""
    source = tmp_path_factory.mktemp("proedit_speed") / "bar.mp4"
    bar = "overlay=x='460+60*t':y=0:format=rgb,"
    white = f"drawbox=color=white:thickness=fill:enable='{EVENTS}'"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=0x202020:s=1280x720:r=30:d=6,format=rgb24"]
        + ["-f", "lavfi", "-i", "color=c=white:s=6x720:r=30,format=rgb24"]
        + ["-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*1000*t)*({EVENTS})':d=6"]
        + ["-filter_complex", f"[0:v][1:v]{bar}{white},format=yuv420p[v]"]
        + ["-map", "[v]", "-map", "2:a", "-shortest"]
        + ["-c:v", "libx264", "-crf", "10", "-c:a", "aac", source]
    )
    return render_pair(source, TIMED)


def grey_frames(video: Path) -> Pixels:
    """Every frame of video (a SIZE proxy) in grey, (frame, height, width)."""
    raw = run_ffmpeg(
        ["-i", video, "-vf", "format=gray", "-f", "rawvideo", "pipe:1"]
    ).stdout
    width, height = SIZE
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width)


def bar_places(video: Path) -> list[float | None]:
    """The middle of the bar along the middle row of each frame of video
    (None on white frames)."""
    width, height = SIZE
    places: list[float | None] = []
    for frame in grey_frames(video):
        row = frame[height // 2].astype(float)
        if np.median(row) > 128:
            places.append(None)
            continue
        weights = np.clip(row - 80, 0, None)
        places.append(float((weights * np.arange(width)).sum() / weights.sum()))
    return places


@pytest.fixture(scope="module")
def content(timed: tuple[Path, Path]) -> list[float | None]:
    """The clip time (s) each frame of the TIMED render shows, by the bar's
    place in the base render (None on white frames)."""
    base, pro = (bar_places(video) for video in timed)
    known = [(place, n / FPS) for n, place in enumerate(base) if place is not None]
    xs, ts = (np.array(values) for values in zip(*known, strict=True))
    assert np.all(np.diff(xs) > 0), "the bar must move right every frame"
    return [None if p is None else float(np.interp(p, xs, ts)) for p in pro]


def speed_of(content: list[float | None], n: int) -> float:
    """The measured speed of frame n: how far the clip moves to frame n + 1."""
    now, after = content[n], content[n + 1]
    assert now is not None and after is not None, f"frame {n} or {n + 1} is white"
    return (after - now) * FPS


def test_the_slow_motion_window_lasts_as_planned(content: list[float | None]) -> None:
    window = frames_of(SLOWMO)
    slow = [n for n in range(FRAMES - 1) if speed_of_or_one(content, n) < 0.75]
    first = slow[0]
    in_sync = [
        n
        for n in range(first + 1, FRAMES)
        if content[n] is not None and abs(content[n] - n / FPS) < 0.5 / FPS
    ]
    duration = (in_sync[0] - first) / FPS
    assert duration == pytest.approx(SLOWMO.t_end - SLOWMO.t_start, abs=1 / FPS)
    assert abs(first - window.start) <= 1
    measured = [speed_of(content, n) for n in window[:-1]]
    assert float(np.median(measured)) == pytest.approx(0.5, abs=0.05)


def speed_of_or_one(content: list[float | None], n: int) -> float:
    """speed_of frame n, 1 where it or the next frame is white."""
    if content[n] is None or content[n + 1] is None:
        return 1.0
    return speed_of(content, n)


def test_the_windows_show_the_clip_where_their_speeds_take_it(
    content: list[float | None],
) -> None:
    for timed_item in TIMED:
        typed = parse_item(timed_item)
        assert isinstance(typed, SlowmoItem | SpeedRampItem)
        planned = content_times(typed, FPS)
        for k, n in enumerate(frames_of(timed_item)):
            shown = content[n]
            assert shown is not None, f"frame {n} is white"
            expected = timed_item.t_start + planned[k]
            assert shown == pytest.approx(expected, abs=POSITION_FRAMES / FPS), n
    fast = frames_of(FAST)
    first, last = content[fast.start], content[fast.stop - 1]
    assert first is not None and last is not None
    assert (last - first) * FPS / (len(fast) - 1) > 1.5


def test_frames_outside_the_windows_play_the_clip_as_it_is(
    content: list[float | None],
) -> None:
    inside = {n for found in TIMED for n in frames_of(found)}
    for n, shown in enumerate(content):
        if n not in inside and shown is not None:
            assert shown == pytest.approx(n / FPS, abs=0.5 / FPS), n


def test_picture_and_sound_are_in_sync_after_the_ramps(
    timed: tuple[Path, Path],
) -> None:
    base, pro = timed
    flashes, beeps = onsets(flash_times(pro)), onsets(beep_times(pro))
    assert len(flashes) == len(beeps) == 2
    assert flashes[0] > SLOWMO.t_end and flashes[1] > FAST.t_end
    for flash, beep in zip(flashes, beeps, strict=True):
        assert abs(flash - beep) < 0.04
    assert beeps == pytest.approx(onsets(beep_times(base)), abs=0.001)


@pytest.fixture(scope="module")
def shaken(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """The base and the SHAKES renders of a textured still."""
    directory = tmp_path_factory.mktemp("proedit_shake")
    png, source = directory / "still.png", directory / "still.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=size=1280x720", "-frames:v", "1"]
        + ["-vf", "hue=s=0,noise=alls=100:allf=u,gblur=sigma=2", png]
    )
    run_ffmpeg(
        ["-loop", "1", "-framerate", "30", "-i", png]
        + ["-f", "lavfi", "-i", "sine=frequency=440", "-t", "6"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source]
    )
    return render_pair(source, SHAKES)


def test_the_affine_extractor_finds_each_shake_in_its_window(
    shaken: tuple[Path, Path],
) -> None:
    frames = grey_frames(shaken[1])
    assert len(frames) == FRAMES
    pairs = [None] + [pair_motion(frames[n - 1], frames[n]) for n in range(1, FRAMES)]
    spans = shake_spans(pairs, FPS)
    windows = [(s.t_start, s.t_end) for s in (SHAKE, SHAKE_ON_ZOOM)]
    for start, end in windows:
        inside = [s for s in spans if s.start < end and s.end > start]
        assert inside, f"no shake found in {start}-{end} s: {spans}"
        assert min(s.start for s in inside) <= start + 2 / FPS
        assert max(s.end for s in inside) >= end - 2 / FPS
        for span in inside:
            assert span.start >= start - 1 / FPS and span.end <= end + 2 / FPS
            assert span.amplitude <= 2 * SHAKE_MAX * 0.5 + 0.01
    assert all(any(s.start < e and s.end > b for b, e in windows) for s in spans)
