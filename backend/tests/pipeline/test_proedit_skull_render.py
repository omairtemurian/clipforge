"""Acceptance of TASK-237 with ffmpeg: the Skull Moment the LLM Director
plans from the owner's recorded reply (tests/fixtures/proedit_director/
recorded_skull_standard.json) at standard and pro keeps every part, and
rendered on a colorful clip its frame is monochrome and visibly differs
from the same frame without the edit.

The fixture's signals are an 18 s clip; the render clip (proedit_render.CLIP)
lasts 4 s, so the Skull Moment's items are moved to start at AT there."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.models import EdlItem, ProEditIntensity
from clipforge.proedit.audio.drop import IMPACT
from clipforge.proedit.composites import find_composites
from clipforge.proedit.director_llm import director_plan
from clipforge.proedit.render.timing import frame_range
from fakes import FakeLLMClient
from frames import Pixels
from proedit_render import all_frames, rendered, source_video
from skull_fakes import CAUGHT, RECORDED_SKULL, skull_request

AT = 1.5
FPS = 30
# Mean HSV saturation (0..1) of a frame: testsrc2 is ~0.8, black and white 0.
MONOCHROME_MAX = 0.05
VISIBLE_MIN = 20.0


def saturation(frame: Pixels) -> float:
    """The mean HSV saturation of frame (RGB pixels)."""
    rgb = frame.astype(np.float64)
    high, low = rgb.max(axis=2), rgb.min(axis=2)
    return float(np.mean(np.where(high > 0, (high - low) / np.maximum(high, 1), 0)))


def skull_items(intensity: ProEditIntensity) -> list[EdlItem]:
    """The items of the planned Skull Moment, moved from CAUGHT to AT."""
    llm = FakeLLMClient(RECORDED_SKULL, repeat_last=True)
    result = director_plan(skull_request(intensity), llm)
    assert result.fallback is None
    group = next(
        g for g in find_composites(result.plan.items) if g.move == "skull_moment"
    )
    assert abs(group.t - CAUGHT) < 1e-3
    shift = AT - group.t
    return [
        i.model_copy(update={"t_start": i.t_start + shift, "t_end": i.t_end + shift})
        for i in result.plan.items
        if i.id in group.ids
    ]


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path) -> Path:
    """A moving, colorful 6 s source (testsrc2)."""
    directory = tmp_path_factory.mktemp("proedit_skull_source")
    return source_video(directory, "testsrc2=size=1280x720:rate=30", still=False)


@pytest.fixture(scope="module")
def clean(source: Path, tmp_path_factory: pytest.TempPathFactory) -> list[Pixels]:
    """Every frame of the clip without items."""
    directory = tmp_path_factory.mktemp("proedit_skull_clean")
    return all_frames(rendered(directory, source, [], "clean"))


@pytest.mark.parametrize("intensity", ["standard", "pro"])
def test_the_skull_moment_renders_monochrome_and_visible(
    intensity: ProEditIntensity,
    source: Path,
    clean: list[Pixels],
    tmp_path: Path,
) -> None:
    items = skull_items(intensity)
    kinds = {i.kind for i in items if abs(i.t_start - AT) < 1e-3}
    assert {"freeze_frame", "grade_change", "shake", "overlay", "sfx"} <= kinds
    assert any(i.kind == "overlay" and i.params["asset"] == "skull" for i in items)
    assert any(i.kind == "sfx" and i.params["asset"] == IMPACT for i in items)
    freeze = next(i for i in items if i.kind == "freeze_frame")

    drawn = all_frames(rendered(tmp_path, source, items, intensity))

    first, end = frame_range(freeze.t_start, freeze.t_end, FPS)
    middle = (first + end) // 2
    assert saturation(clean[middle]) > 0.3
    assert saturation(drawn[middle]) < MONOCHROME_MAX
    difference = np.abs(drawn[middle].astype(np.int16) - clean[middle]).mean()
    assert difference > VISIBLE_MIN
    after = end + 2
    assert saturation(drawn[after]) > 0.3
