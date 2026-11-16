"""The Phonk Edit / Pro style-trait acceptance test (SPEC-v3 2.1, TASK-220).

The fixture clip (clip 7 of sample.mp4, 16.5-34.5 s, whose signals are
fixtures/proedit_signals_expected.json) gets a plan from the rule-based
Director at Phonk Edit / Pro over a generated 140 BPM bed (kicks on every
beat, louder on the downbeats; SPEC-v3 9.8), whose beat grid is read with
beats.music_grid as the app reads a music asset's. The plan is rendered as
a proxy and the output and the source are measured with the extractors of
Style Learning (features/video.measure_video). The base has no caption
words, so the caption style item draws nothing; captions bear on none of
the five traits.

Traits (SPEC-v3 2.1; on-beat within one frame, SPEC-v3 9.6): the mean
interval between cuts or zoom changes (zooms in and out), zoom punches
(fast zooms in) per 3 s, the share of cuts and zoom changes on a beat,
flashes or shakes per 5 s, and the mean luma of the output against the
source's over the clip.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from audio_synth import times, write_wav
from clipforge.config import RenderSettings
from clipforge.models import FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.proedit.beats import music_grid
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.director_rules import rule_plan
from clipforge.proedit.features.cuts import mean_interval, on_beat_share
from clipforge.proedit.features.video import VideoFeatures, measure_video
from clipforge.proedit.preset_defs import get_preset
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.run import render_plan
from clipforge.proedit.signal_models import ProEditSignals
from fakes import FIXTURES

SIGNALS = ProEditSignals.model_validate_json(
    (FIXTURES / "proedit_signals_expected.json").read_text(encoding="utf-8")
)
CLIP = ClipSpan(SIGNALS.clip_id, 16.5, 34.5)
BPM = 140
BED_ID = "1"
X264 = RenderSettings(encoder="libx264")

MAX_MEAN_INTERVAL_S = 1.5
MIN_PUNCHES_PER_3_S = 1.0
MIN_ON_BEAT_SHARE = 0.6
MIN_FLASHES_OR_SHAKES_PER_5_S = 1.0


@dataclass(frozen=True)
class Traits:
    """The five measured traits of a Pro Edit (module docstring)."""

    mean_interval_s: float
    punches_per_3_s: float
    on_beat_share: float
    flashes_or_shakes_per_5_s: float
    output_luma: float
    source_luma: float


def phonk_bed(path: Path, bpm: float = BPM, seconds: float = 24.0) -> Path:
    """Write a bed of an 808-like kick (a sine falling from 115 to 55 Hz) on
    every beat of bpm, louder on the first beat of each bar of four, as a
    WAV file; return path."""
    out = np.zeros(len(times(seconds)))
    kick_t = times(0.25)
    sweep = 55 * kick_t + 2 * (1 - np.exp(-30 * kick_t))
    kick = np.sin(2 * np.pi * sweep) * np.exp(-12 * kick_t)
    step = 60.0 / bpm
    for k in range(int(seconds / step)):
        start = round(k * step * len(out) / seconds)
        end = min(start + len(kick), len(out))
        out[start:end] += (0.9 if k % 4 == 0 else 0.5) * kick[: end - start]
    return write_wav(path, out)


def fixture_base(bed: Path) -> ProEditBase:
    """The base of the fixture clip, centered 9:16, ducking under its
    words, with the bed as library sound BED_ID."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    crop = plan_crop(CLIP, "9:16", (SIGNALS.width, SIGNALS.height), faces, [])
    return ProEditBase(
        FIXTURES / "sample.mp4",
        CLIP.start,
        CLIP.end,
        crop,
        "fill",
        speech=tuple((w.start, w.end) for w in SIGNALS.words),
        sounds={BED_ID: bed},
    )


def traits_of(
    output: VideoFeatures, source: VideoFeatures, beats: tuple[float, ...]
) -> Traits:
    """The traits of output (a Pro Edit of source) over beats (clip s)."""
    zooms = output.motion.zooms
    changes = [*output.cuts.cuts, *(zoom.start for zoom in zooms)]
    punches = [z for z in zooms if z.kind == "punch" and z.scale > 1]
    hits = len(output.flashes.flashes) + len(output.motion.shakes)
    interval = mean_interval(changes)
    return Traits(
        mean_interval_s=output.duration if interval is None else interval,
        punches_per_3_s=round(len(punches) / output.duration * 3, 4),
        on_beat_share=on_beat_share(changes, beats, 1 / output.fps),
        flashes_or_shakes_per_5_s=round(hits / output.duration * 5, 4),
        output_luma=output.color.mean_luma,
        source_luma=source.color.mean_luma,
    )


@pytest.fixture(scope="module")
def traits(tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path) -> Traits:
    """Plan, render and measure the Phonk Edit / Pro of the fixture clip."""
    directory = tmp_path_factory.mktemp("phonk")
    bed = phonk_bed(directory / "bed.wav")
    grid = music_grid(bed)
    assert grid.bpm == pytest.approx(BPM, abs=1)
    music = MusicChoice(BED_ID, grid, 0.0)
    plan = rule_plan(
        SIGNALS, get_preset("phonk_edit"), "phonk_edit", "pro", music, plan_id=1
    ).plan
    video = render_plan(
        fixture_base(bed),
        plan,
        directory / "phonk.mp4",
        quality="proxy",
        settings=X264,
    )
    output = measure_video(video)
    source = measure_video(FIXTURES / "sample.mp4", start=CLIP.start, end=CLIP.end)
    assert output.duration == pytest.approx(SIGNALS.duration, abs=0.05)
    measured = traits_of(output, source, music.beats(SIGNALS.duration))
    print(f"\nPhonk Edit / Pro traits: {measured}")
    return measured


def test_cuts_or_zoom_changes_come_every_1_5_s_or_faster(traits: Traits) -> None:
    assert traits.mean_interval_s <= MAX_MEAN_INTERVAL_S


def test_at_least_one_zoom_punch_per_3_s(traits: Traits) -> None:
    assert traits.punches_per_3_s >= MIN_PUNCHES_PER_3_S


def test_most_cuts_and_zooms_land_on_a_music_beat(traits: Traits) -> None:
    assert traits.on_beat_share >= MIN_ON_BEAT_SHARE


def test_at_least_one_flash_or_shake_per_5_s(traits: Traits) -> None:
    assert traits.flashes_or_shakes_per_5_s >= MIN_FLASHES_OR_SHAKES_PER_5_S


def test_the_grade_is_darker_than_the_source(traits: Traits) -> None:
    assert traits.output_luma < traits.source_luma
