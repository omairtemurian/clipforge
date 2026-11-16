"""Tests of the Pro Edit renderer's freeze frames, flashes, LUT looks,
normalization and skin protection with ffmpeg (SPEC-v3 3.3/3.6, TASK-208).

The clip is 1-5 s of a 6 s 1280x720 30 fps source, framed 9:16 with no
faces (frame k starts at k / 30 s of the clip). Freezes and flashes render
an animated testsrc2, losslessly (libx264 crf 0: a frozen frame decodes to
the very same pixels), checked by frame hash and proedit/features. Looks
render a still of four color bands (skin, blue, green, gray), measured in
the middle of each band: the bundled LUT gives the colors luts.LOOKS
computes, skin protection keeps the skin band's saturation within
SKIN_MAX_CHANGE while other colors take the full look. Normalization
renders dim, warm gray bands and stretches their levels and evens their
channels. Colors measured in a video are off the LUT's by up to a few
levels (yuv420p round trips), so saturation ratios get VIDEO_SLACK.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import ffprobe_json
from clipforge.proedit.features.color import BW_SATURATION, frame_color
from clipforge.proedit.features.flashes import detect_flashes
from clipforge.proedit.render.luts import LOOKS
from clipforge.proedit.render.skin import SKIN_MAX_CHANGE
from edl_fakes import item
from frames import Pixels, frame_hashes, numbered_frames
from proedit_render import CLIP, all_frames, rendered, source_video

PLAIN = {"normalize": False, "skin_protect": False}
# Freeze 1.0-1.5 s holds frame 30 on frames 30-44, black and white from
# 1.2 s (frames 36-44); a white flash at 2.0 s (frame 60), a black one at
# 3.0 s (frame 90).
MOMENTS = [
    item(1, "freeze_frame", 1.0, 1.5),
    item(2, "grade_change", 1.2, 1.5, params={"look": "bw", "normalize": False}),
    item(3, "flash", 2.0, 2.3),
    item(4, "flash", 3.0, 3.3, params={"color": "black", "peak": 0.6}),
]
# Frames: plain teal_orange 15-29, protected teal_orange 36-47, protected
# desat 54-65, plain desat 72-83.
TEAL_ORANGE = {"look": "lut", "lut": "teal_orange"}
LOOK_ITEMS = [
    item(1, "grade_change", 0.5, 1.0, params={**TEAL_ORANGE, **PLAIN}),
    item(2, "grade_change", 1.2, 1.6, params={**TEAL_ORANGE, "normalize": False}),
    item(3, "grade_change", 1.8, 2.2, params={"look": "desat", "normalize": False}),
    item(4, "grade_change", 2.4, 2.8, params={"look": "desat", **PLAIN}),
]
BANDS = {
    "skin": "0xE0AC69",
    "blue": "0x3359CC",
    "green": "0x4C9A3A",
    "gray": "0x808080",
}
WARM_BANDS = ("0x403830", "0x806850", "0xB09878")
VIDEO_SLACK = 0.05
# The warm bands: normalized on frames 15-44, not on frames 60-89 (a desat
# so slight it changes nothing measurable).
FAINT = {"look": "desat", "amount": 0.01, "skin_protect": False}
NORMALIZE = [
    item(1, "grade_change", 0.5, 1.5, params=FAINT),
    item(2, "grade_change", 2.0, 3.0, params={**FAINT, "normalize": False}),
]


@pytest.fixture(scope="module")
def moments(tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path) -> Path:
    directory = tmp_path_factory.mktemp("moments")
    moving = source_video(directory, "testsrc2=size=1280x720:rate=30", still=False)
    return rendered(directory, moving, MOMENTS)


def stacked(colors: Sequence[str]) -> str:
    """Return the lavfi graph of 1280x720 horizontal bands of colors."""
    height = 720 // len(colors)
    bands = "".join(
        f"color=c={c}:size=1280x{height}[b{i}];" for i, c in enumerate(colors)
    )
    labels = "".join(f"[b{i}]" for i in range(len(colors)))
    return f"{bands}{labels}vstack=inputs={len(colors)}"


@pytest.fixture(scope="module")
def looks(tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path) -> Path:
    directory = tmp_path_factory.mktemp("looks")
    bands = source_video(directory, stacked(list(BANDS.values())), still=True)
    return rendered(directory, bands, LOOK_ITEMS)


@pytest.fixture(scope="module")
def normalized(tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path) -> Path:
    directory = tmp_path_factory.mktemp("normalized")
    warm = source_video(directory, stacked(WARM_BANDS), still=True)
    return rendered(directory, warm, NORMALIZE)


def band_colors(frame: Pixels) -> dict[str, np.ndarray]:
    """Return the mean RGB (0..1) of the middle of each band of frame."""
    height = frame.shape[0] // len(BANDS)
    return {
        name: frame[i * height + height // 3 : (i + 1) * height - height // 3, 20:-20]
        .reshape(-1, 3)
        .mean(axis=0)
        / 255
        for i, name in enumerate(BANDS)
    }


def chroma(rgb: np.ndarray) -> float:
    return float(rgb.max() - rgb.min())


def saturation_ratios(before: Pixels, after: Pixels) -> dict[str, float]:
    """Return each band's chroma in after as a share of its chroma in before."""
    old, new = band_colors(before), band_colors(after)
    return {
        name: chroma(new[name]) / chroma(old[name])
        for name in ("skin", "blue", "green")
    }


def test_a_freeze_holds_exactly_the_frames_of_its_window(moments: Path) -> None:
    hashes = frame_hashes(moments)
    assert len(set(hashes[30:45])) == 2
    assert len(set(hashes[30:36])) == 1 and len(set(hashes[36:45])) == 1
    assert hashes[29] != hashes[30] and hashes[45] != hashes[44]
    assert len(set(hashes[45:55])) == 10
    duration = float(ffprobe_json(moments)["format"]["duration"])
    assert duration == pytest.approx(CLIP.end - CLIP.start, abs=0.1)


def test_the_held_frame_is_graded_inside_the_grade_window(moments: Path) -> None:
    frames = numbered_frames(moments, [30, 35, 36, 44])
    assert frame_color(frames[30]).saturation > 0.5
    assert frame_color(frames[44]).saturation < BW_SATURATION
    assert np.array_equal(frames[30], frames[35])


def test_flashes_peak_on_their_first_frame_and_fade(moments: Path) -> None:
    colors = [frame_color(frame) for frame in all_frames(moments)]
    luma = np.array([color.luma for color in colors])
    assert int(np.argmax(luma)) == 60
    assert luma[60] > luma[59] + 0.3 and luma[60] > luma[61] > luma[62]
    assert luma[70] == pytest.approx(luma[58], abs=0.05)
    assert int(np.argmin(luma[80:110])) + 80 == 90
    assert luma[90] < luma[89] - 0.2
    starts = [flash.start for flash in detect_flashes(colors, 30).flashes]
    assert any(abs(start - 2.0) <= 1 / 30 for start in starts)


def test_the_bundled_lut_gives_its_colors_only_in_its_window(looks: Path) -> None:
    frames = numbered_frames(looks, [0, 14, 15, 29, 30, 110])
    plain = band_colors(frames[0])
    for k in (15, 29):
        graded = band_colors(frames[k])
        for name, color in plain.items():
            expected = LOOKS["teal_orange"](color[None, :])[0]
            assert np.abs(graded[name] - expected).max() < 5 / 255, name
    for k in (14, 30, 110):
        assert np.abs(frames[k].astype(np.int16) - frames[0]).mean() < 0.5


def test_skin_protection_keeps_skin_saturation_within_its_cap(looks: Path) -> None:
    frames = numbered_frames(looks, [0, 20, 40, 60, 78])
    cap = SKIN_MAX_CHANGE + VIDEO_SLACK
    look, protected_look = (
        saturation_ratios(frames[0], frames[20]),
        saturation_ratios(frames[0], frames[40]),
    )
    desat, protected_desat = (
        saturation_ratios(frames[0], frames[78]),
        saturation_ratios(frames[0], frames[60]),
    )
    assert look["skin"] > protected_look["skin"] + 0.1
    assert abs(protected_look["skin"] - 1) <= cap
    assert protected_look["blue"] == pytest.approx(look["blue"], abs=0.03)
    assert desat["skin"] == pytest.approx(0.4, abs=0.08)
    assert protected_desat["skin"] >= 1 - cap
    for name in ("blue", "green"):
        assert desat[name] == pytest.approx(0.4, abs=0.08)
        assert protected_desat[name] == pytest.approx(0.4, abs=0.08)


def spread(frame: Pixels) -> float:
    """Return the 2nd-98th percentile range of the luma of frame (0..1)."""
    low, high = np.percentile(frame_luma(frame), [2, 98])
    return float(high - low)


def frame_luma(frame: Pixels) -> np.ndarray:
    return np.asarray(frame.astype(np.float32) @ np.array([0.299, 0.587, 0.114]) / 255)


def channel_balance(frame: Pixels) -> float:
    """Return the blue channel's mean as a share of the red channel's."""
    means = frame.reshape(-1, 3).mean(axis=0)
    return float(means[2] / means[0])


def test_normalization_stretches_levels_and_evens_the_channels(
    normalized: Path,
) -> None:
    frames = numbered_frames(normalized, [10, 30, 75])
    assert spread(frames[30]) > spread(frames[75]) + 0.1
    assert abs(channel_balance(frames[30]) - 1) < abs(channel_balance(frames[75]) - 1)
    assert np.abs(frames[10].astype(np.int16) - frames[75]).mean() < 1.5


def video_streams(video: Path) -> Sequence[dict[str, object]]:
    return [s for s in ffprobe_json(video)["streams"] if s["codec_type"] == "video"]


def test_renders_with_rgb_filters_stay_yuv420p(looks: Path, normalized: Path) -> None:
    for video in (looks, normalized):
        (picture,) = video_streams(video)
        assert picture["pix_fmt"] == "yuv420p"
