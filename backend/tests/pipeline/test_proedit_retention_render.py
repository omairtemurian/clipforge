"""J and L cuts and the loop-friendly ending in a Pro Edit render with
ffmpeg (SPEC-v3 3.3, TASK-233).

The source is red with a 440 Hz tone until 2.5 s, then blue with a 1000 Hz
tone; the clip is 1-5 s of it with 2-3 s cut out, so its picture turns
blue at 1.0 s of the render, the cut. The sound turns to 1000 Hz with a J
cut 6 frames (pro) before it, with an L cut 6 frames after it when a word
lies before the next part, and with the picture when words sit on both
sides. The loop ending blends the last frames into the first (red) and the
sound into the opening tone.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.proedit.render.run import render_plan
from edl_fakes import item, plan
from proedit_render import LOSSLESS, all_frames, base_of
from proedit_sound import RATE, Samples, decoded

FPS = 30
CUT_S = 1.0
LOW_HZ, HIGH_HZ = 440, 1000
STEP_S = 0.005


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 30 fps video: red and 440 Hz, then from 2.5 s blue
    and 1000 Hz."""
    video = tmp_path_factory.mktemp("retention") / "source.mp4"
    parts = [("red", LOW_HZ, 2.5), ("blue", HIGH_HZ, 3.5)]
    inputs: list[str | Path] = []
    for color, hz, seconds in parts:
        inputs += ["-f", "lavfi", "-i", f"color={color}:s=1280x720:r={FPS}:d={seconds}"]
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}"]
    graph = "[0:v][1:a][2:v][3:a]concat=n=2:v=1:a=1[v][a]"
    run_ffmpeg(
        [*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video]
    )
    return video


def tone(samples: Samples, hz: float, at: float) -> float:
    """The level of hz in the 10 ms of samples from at seconds."""
    chunk = samples[round(at * RATE) : round((at + 0.01) * RATE)]
    t = np.arange(len(chunk)) / RATE
    return float(abs(np.dot(chunk, np.exp(-2j * np.pi * hz * t))))


def sound_switch(samples: Samples, start: float, end: float) -> float:
    """The first time from start to end at which HIGH_HZ is louder than
    LOW_HZ."""
    for at in np.arange(start, end, STEP_S):
        if tone(samples, HIGH_HZ, at) > tone(samples, LOW_HZ, at):
            return float(at)
    raise AssertionError("the sound never switches")


def blue_from(frames: list[np.ndarray]) -> int:
    """The first frame whose blue outweighs its red."""
    return next(n for n, f in enumerate(frames) if f[..., 2].mean() > f[..., 0].mean())


@pytest.mark.parametrize(
    ("words", "shift"),
    [
        ((), -6),  # J cut: the 1000 Hz leads the blue picture
        (((1.75, 1.95),), 6),  # a word before the next part: L cut
        (((0.9, 1.0), (1.9, 2.1)), 0),  # words on both sides: straight
    ],
    ids=["j_cut", "l_cut", "straight"],
)
def test_the_sound_switches_frames_before_or_after_the_picture(
    source: Path, tmp_path: Path, words: tuple[tuple[float, float], ...], shift: int
) -> None:
    base = replace(base_of(source, [(2.0, 3.0)]), source_words=words)
    output = render_plan(
        base, plan([], "pro"), tmp_path / "jl.mp4", quality="proxy", settings=LOSSLESS
    )
    assert blue_from(all_frames(output)) == round(CUT_S * FPS)
    switch = sound_switch(decoded(output), 0.5, 1.5)
    # The 10 ms window turns at the switch's middle: about 5 ms early.
    assert switch == pytest.approx(CUT_S + shift / FPS - 0.005, abs=0.012)


def test_the_loop_ending_turns_the_last_frame_into_the_first(
    source: Path, tmp_path: Path
) -> None:
    base = base_of(source)
    loop = item(1, "transition", 3.7, 4.0, params={"type": "loop", "whoosh": False})
    looped = render_plan(
        base,
        plan([loop], "pro"),
        tmp_path / "loop.mp4",
        quality="proxy",
        settings=LOSSLESS,
    )
    straight = render_plan(
        base,
        plan([], "pro"),
        tmp_path / "plain.mp4",
        quality="proxy",
        settings=LOSSLESS,
    )
    frames, plain = all_frames(looped), all_frames(straight)
    assert len(frames) == len(plain) == 4 * FPS

    def difference(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())

    assert difference(frames[-1], frames[0]) < 2
    assert difference(plain[-1], plain[0]) > 100
    # Before the window the frames are untouched; inside it they blend.
    assert difference(frames[110], plain[110]) == 0
    middle = difference(frames[115], frames[0])
    assert 20 < middle < difference(plain[115], plain[0]) - 20

    sound, plain_sound = decoded(looped), decoded(straight)
    tail = 4.0 - 0.02
    assert tone(sound, LOW_HZ, tail) > 3 * tone(sound, HIGH_HZ, tail)
    assert tone(plain_sound, HIGH_HZ, tail) > 3 * tone(plain_sound, LOW_HZ, tail)
    assert tone(sound, HIGH_HZ, 3.5) == pytest.approx(
        tone(plain_sound, HIGH_HZ, 3.5), rel=0.05
    )
