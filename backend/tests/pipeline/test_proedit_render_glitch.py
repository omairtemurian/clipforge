"""Tests of the Pro Edit renderer's glitches, RGB splits and transitions with
ffmpeg (SPEC-v3 3.3, TASK-211).

The clip is 1-5 s of a 6 s 1280x720 30 fps source, framed 9:16 (540x960)
with no faces, rendered losslessly next to a clean render (no items), so
frames outside an effect's window are the very same pixels. An animated
testsrc2 takes RGB splits (found by proedit/features/glitches), a glitch
(checked against fx_glitch.glitch_window, its plan), a whip and a glitch
transition. Four solid colors (cuts at frames 30, 60 and 105) take a
crossfade, a flash and a zoom transition, centred on those cuts (a flash
turns white before its cut, then fades into the next scene; a solid color
zoomed in is the same color, so a zoom shows only as its fade).
"""

from pathlib import Path

import numpy as np
import pytest
from clipforge.proedit.edl_params import GlitchParams
from clipforge.proedit.features.glitches import channel_offset
from clipforge.proedit.render.fx_glitch import glitch_window
from edl_fakes import item
from frames import Pixels, frame_hashes
from proedit_render import all_frames, rendered, source_video

SIZE = (540, 960)
# Windows by frame: splits 15-29 (8 px right) and 36-41 (6 px up), glitch
# 60-74, whip 84-89, glitch transition 102-113.
EFFECTS = [
    item(1, "rgb_split", 0.5, 1.0, params={"offset_px": 16}),
    item(2, "rgb_split", 1.2, 1.4, params={"offset_px": 12, "angle_deg": 90}),
    item(3, "glitch", 2.0, 2.5, params={"strength": 1.0, "seed": 3}),
    item(4, "transition", 2.8, 3.0, params={"type": "whip"}),
    item(5, "transition", 3.4, 3.8, params={"type": "glitch"}),
]
WINDOWS = [(15, 30), (36, 42), (60, 75), (84, 90), (102, 114)]
SCENES = [("0x2040C0", 2.0), ("0xC04020", 1.0), ("0x20A040", 1.5), ("0x808080", 1.5)]
# Crossfade frames 24-35, flash 54-65, zoom 99-110.
TRANSITIONS = [
    item(1, "transition", 0.8, 1.2, params={"type": "crossfade"}),
    item(2, "transition", 1.8, 2.2, params={"type": "flash"}),
    item(3, "transition", 3.3, 3.7, params={"type": "zoom"}),
]
SAME = 2.0


@pytest.fixture(scope="module")
def effects(
    tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path
) -> tuple[Path, Path]:
    """The clean and the effects render of the testsrc2 clip."""
    directory = tmp_path_factory.mktemp("glitches")
    moving = source_video(directory, "testsrc2=size=1280x720:rate=30", still=False)
    return rendered(directory, moving, [], "clean"), rendered(
        directory, moving, EFFECTS
    )


@pytest.fixture(scope="module")
def scenes(
    tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path
) -> tuple[list[Pixels], list[Pixels]]:
    """The frames of the clean and the transitions render of the scenes."""
    directory = tmp_path_factory.mktemp("scenes")
    colors = "".join(
        f"color=c={c}:size=1280x720:rate=30:duration={d}[s{n}];"
        for n, (c, d) in enumerate(SCENES)
    )
    graph = colors + "".join(f"[s{n}]" for n in range(len(SCENES))) + "concat=n=4"
    source = source_video(directory, graph, still=False)
    return all_frames(rendered(directory, source, [], "clean")), all_frames(
        rendered(directory, source, TRANSITIONS)
    )


def difference(a: Pixels, b: Pixels) -> float:
    return float(np.abs(a.astype(np.int16) - b).mean())


def mean_color(frame: Pixels) -> np.ndarray:
    return np.asarray(frame.reshape(-1, 3).mean(axis=0), dtype=np.float64)


def test_effects_change_exactly_the_frames_of_their_windows(
    effects: tuple[Path, Path],
) -> None:
    clean, drawn = (frame_hashes(video) for video in effects)
    assert len(clean) == len(drawn) == 120
    changed = {k for k in range(120) if clean[k] != drawn[k]}
    assert changed == {k for first, end in WINDOWS for k in range(first, end)}


def test_rgb_splits_are_found_in_their_windows_only(
    effects: tuple[Path, Path],
) -> None:
    frames = all_frames(effects[1], SIZE)
    for k in (15, 22, 29):
        found = channel_offset(frames[k])
        assert found.is_split and (found.red, found.blue) == ((8, 0), (-8, 0))
    for k in (36, 41):
        found = channel_offset(frames[k])
        assert found.is_split and (found.red, found.blue) == ((0, -6), (0, 6))
    for k in (14, 30, 35, 42, 50):
        assert not channel_offset(frames[k]).is_split


def test_the_glitch_plays_its_plan(effects: tuple[Path, Path]) -> None:
    clean, drawn = (all_frames(video) for video in effects)
    plan = glitch_window(GlitchParams(strength=1.0, seed=3), 60, 15, SIZE)
    assert plan.frames != tuple(range(15))
    for k, shown in enumerate(plan.frames):
        off = difference(drawn[60 + k], clean[60 + shown])
        assert (off > 3 * SAME) if k in plan.glitches else (off < SAME), k
    stutter = next(k for k, shown in enumerate(plan.frames) if shown != k)
    if stutter not in plan.glitches:
        assert difference(drawn[60 + stutter], clean[60 + stutter]) > 3 * SAME


def test_whip_and_glitch_transitions_change_their_windows(
    effects: tuple[Path, Path],
) -> None:
    clean, drawn = (all_frames(video) for video in effects)
    for first, end in WINDOWS[3:]:
        middle = (first + end) // 2
        assert difference(drawn[middle], clean[middle]) > 3 * SAME
        assert difference(drawn[end], clean[end]) == 0


def test_a_crossfade_blends_across_its_cut(
    scenes: tuple[list[Pixels], list[Pixels]],
) -> None:
    clean, drawn = scenes
    assert difference(clean[29], clean[30]) > 50
    before, after = mean_color(clean[29]), mean_color(clean[30])
    progress = [
        float((mean_color(drawn[k]) - before)[0] / (after - before)[0])
        for k in range(24, 37)
    ]
    assert progress[0] == pytest.approx(0, abs=0.02)
    assert progress[-1] == pytest.approx(1, abs=0.02)
    assert all(b > a for a, b in zip(progress[:-1], progress[1:], strict=True))
    assert progress[6] == pytest.approx(0.5, abs=0.1)


def test_a_flash_fades_through_white_at_its_cut(
    scenes: tuple[list[Pixels], list[Pixels]],
) -> None:
    clean, drawn = scenes
    lightest = [float(mean_color(frame).min()) for frame in drawn]
    white = [k for k, level in enumerate(lightest) if level > 250]
    assert white and 54 < min(white) and max(white) < 60
    fading = lightest[max(white) : 67]
    assert all(b < a for a, b in zip(fading[:-1], fading[1:], strict=True))
    assert difference(drawn[53], clean[53]) == 0
    assert difference(drawn[66], clean[66]) == 0


def test_a_zoom_moves_to_the_next_scene_inside_its_window(
    scenes: tuple[list[Pixels], list[Pixels]],
) -> None:
    clean, drawn = scenes
    assert difference(drawn[104], clean[104]) == 0
    assert difference(drawn[105], clean[104]) == 0
    assert 0 < difference(drawn[110], clean[110]) < difference(clean[104], clean[110])
    assert difference(drawn[111], clean[111]) == 0
