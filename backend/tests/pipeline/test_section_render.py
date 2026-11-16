"""Tests of a clip whose sections play out of source order (SPEC-v2 3.5
section ops), rendered with ffmpeg: the flashes of the fixture video come
section by section in the sections' order, pictures and sound together, and
the render lasts the sections less their cuts (ffprobe)."""

from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media
from clipforge.models import CropPlan, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from flashes import beep_times, flash_times, make_flashes, onsets

# Sections of the flashes video (flashes at 2, 5 and 8 s) in the order they
# play, the second without CUTS: the flash at 8 s plays at 1 s, the one at
# 2 s at 2 + (1 - 0.4) = 2.6 s and the one at 5 s at 2 + 1.6 + 0.5 = 4.1 s;
# the clip lasts 2 + 1.6 + 1 = 4.6 s.
SECTIONS = [(7.0, 9.0), (1.0, 3.0), (4.5, 5.5)]
CUTS = [(1.2, 1.6)]
SPAN = ClipSpan(1, 1.0, 9.0)


def crop_plan(size: tuple[int, int]) -> CropPlan:
    """Return the 1:1 crop plan of SPAN of a source of size, with no faces."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(SPAN.start, SPAN.end)]
    return plan_crop(SPAN, "1:1", size, faces, [])


@pytest.fixture(scope="module")
def flashes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The flashes video (flashes.make_flashes)."""
    return make_flashes(tmp_path_factory.mktemp("sections") / "flashes.mp4")


@pytest.mark.parametrize("target_lufs", [None, -14.0])
def test_sections_play_in_their_order(
    flashes: Path,
    tmp_path: Path,
    target_lufs: float | None,
    render_settings: RenderSettings,
) -> None:
    output = tmp_path / "sections.mp4"

    render_clip(
        flashes,
        output,
        SPAN.start,
        SPAN.end,
        crop_plan((640, 360)),
        "fill",
        render_settings,
        cut_ranges=CUTS,
        segments=SECTIONS,
        target_lufs=target_lufs,
    )

    assert probe_media(output).duration == pytest.approx(4.6, abs=0.05)
    assert onsets(flash_times(output)) == pytest.approx([1.0, 2.6, 4.1], abs=1e-6)
    assert onsets(beep_times(output)) == pytest.approx([1.0, 2.6, 4.1], abs=0.005)


def test_sections_in_source_order_leave_out_their_gaps(
    flashes: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    output = tmp_path / "gaps.mp4"

    render_clip(
        flashes,
        output,
        SPAN.start,
        SPAN.end,
        crop_plan((640, 360)),
        "fill",
        render_settings,
        segments=sorted(SECTIONS),
    )

    # 1-3 s, 4.5-5.5 s and 7-9 s: flashes at 1, 2.5 and 4 s; 5 s long.
    assert probe_media(output).duration == pytest.approx(5.0, abs=0.05)
    assert onsets(flash_times(output)) == pytest.approx([1.0, 2.5, 4.0], abs=1e-6)
