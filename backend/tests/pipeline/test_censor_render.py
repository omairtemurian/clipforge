"""Tests of censored sound in rendered clips (SPEC-v2 3.4, pipeline/censor,
censor_audio): with ffmpeg, the RMS level at the censored word's time
(astats) spikes with a beep and drops to silence with mute, after the cuts
that come before the word."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from builders import make_clip, said
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CaptionCensor, CaptionStyle, CensorMode, FaceBox
from clipforge.pipeline.censor_audio import clip_censor_filter
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.step import TRANSCRIPT, write_json

MakeMedia = Callable[..., Path]
# A quiet 440 Hz tone, about -37 dBFS RMS, as the clip's speech.
QUIET_TONE = "aevalsrc=0.02*sin(2*PI*440*t)"
CLIP = ClipSpan(7, 0.0, 4.0)
# "shit" at 1.5-2.0 s of the source; the cut 0.2-0.6 s brings it to
# 1.1-1.6 s of the rendered clip, censored from 1.05 to 1.65 s.
TRANSCRIPT_WORDS = said(("so", 0.8, 1.0), ("shit", 1.5, 2.0), ("ok", 2.8, 3.2))
CUTS = [(0.2, 0.6)]
WORD = (1.15, 0.4)
OUTSIDE = (2.2, 0.6)
SIZE = (180, 320)


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


@pytest.fixture(scope="module")
def tone(make_media: MakeMedia) -> Path:
    """A 4 s 320x240 h264/aac video with the quiet tone."""
    return make_media(
        "censor_tone.mp4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        audio_source=QUIET_TONE,
        duration=4.0,
    )  # fmt: skip


def render_censored(
    tone: Path, work: Path, mode: CensorMode, target_lufs: float | None
) -> Path:
    """Render the clip of CLIP with CUTS and "shit" censored by mode."""
    work.mkdir(exist_ok=True)
    write_json(work / TRANSCRIPT, TRANSCRIPT_WORDS)
    style = CaptionStyle(censor=CaptionCensor(mode=mode))
    clip = make_clip(
        "minimal", start=CLIP.start, end=CLIP.end, cut_ranges=CUTS, caption_style=style
    )
    censor = clip_censor_filter(work, clip, 30)
    assert "between(t,1.050,1.650)" in censor
    faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    plan = plan_crop(CLIP, "9:16", (320, 240), faces, [])
    output = work / f"{mode}.mp4"
    return render_clip(
        tone,
        output,
        clip.start,
        clip.end,
        plan,
        "fill",
        RenderSettings(),
        cut_ranges=CUTS,
        target_lufs=target_lufs,
        size=SIZE,
        censor=censor,
    )


def test_a_beep_spikes_the_level_at_the_censored_word(
    tone: Path, tmp_path: Path, data_dir: Path
) -> None:
    video = render_censored(tone, tmp_path / "work", "beep", None)

    word, outside = rms_db(video, *WORD), rms_db(video, *OUTSIDE)

    assert word == pytest.approx(-13.5, abs=1.5)
    assert outside == pytest.approx(-37.0, abs=2.0)


def test_a_beep_survives_loudness_normalization(
    tone: Path, tmp_path: Path, data_dir: Path
) -> None:
    video = render_censored(tone, tmp_path / "work", "beep", -14.0)

    assert rms_db(video, *WORD) > rms_db(video, *OUTSIDE) + 10


def test_mute_silences_the_censored_word(
    tone: Path, tmp_path: Path, data_dir: Path
) -> None:
    video = render_censored(tone, tmp_path / "work", "mute", None)

    assert rms_db(video, *WORD) < -60
    assert rms_db(video, *OUTSIDE) == pytest.approx(-37.0, abs=2.0)
