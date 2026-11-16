"""Tests of the Pro Edit subject cut-out with ffmpeg (SPEC-v3 3.3 motion,
TASK-234).

Source: 4-10 s of the fixture, padded and panned so its drawn face stays
in the middle of the frame; the clip (1-5 s of it, centered 9:16) shows
the face on red, green and yellow columns. Renders are lossless proxies
compared with the render without a cut-out: with the engine (MediaPipe,
engine_segment), a swapped background turns the top corners magenta and
leaves the face's middle alone, a blurred one changes the corners a
little, and a skull larger than the face, with the subject in front, is
hidden over the face's middle but still drawn beyond it. Without the
engine the cut-out is skipped and the render is the one without it.
"""

from pathlib import Path

import numpy as np
import pytest
from clipforge import config
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.proedit.render.cutout import CutoutChoice
from clipforge.proedit.render.run import render_plan
from edl_fakes import item, plan
from proedit_render import LOSSLESS, all_frames, base_of

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample.mp4"
SIZE = (270, 480)
FACE_MIDDLE = (slice(230, 250), slice(125, 145))
CORNER = (slice(0, 40), slice(0, 40))
MAGENTA = (255, 0, 255)
SKULL = item(
    1,
    "overlay",
    0.0,
    4.0,
    params={"asset": "skull", "x": 0.5, "y": 0.5, "scale": 0.9, "animation": "none"},
)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """4-10 s of the fixture with its face kept at x = 640 (1280x720)."""
    video = tmp_path_factory.mktemp("cutout") / "source.mp4"
    pan = "pad=2560:720:640:0,crop=1280:720:x='200+880*(t+4)/60'"
    run_ffmpeg(
        ["-ss", "4", "-t", "6", "-i", FIXTURE, "-vf", pan]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video]
    )
    return video


def render(
    source: Path,
    folder: Path,
    name: str,
    items: list[EdlItem],
    cutout: CutoutChoice | None = None,
) -> np.ndarray:
    """Every frame (int RGB) of the lossless proxy of the clip of source
    with items and cutout."""
    output = render_plan(
        base_of(source),
        plan(items, "pro"),
        folder / f"{name}.mp4",
        quality="proxy",
        settings=LOSSLESS,
        cutout=cutout,
    )
    return np.stack(all_frames(output, SIZE)).astype(int)


def difference(a: np.ndarray, b: np.ndarray, region: tuple[slice, slice]) -> float:
    """The mean absolute difference of a and b in region of every frame."""
    return float(np.abs(a[:, *region] - b[:, *region]).mean())


@pytest.mark.engine_segment
def test_the_background_is_swapped_or_blurred_around_the_subject(
    source: Path, tmp_path: Path
) -> None:
    plain = render(source, tmp_path, "plain", [])
    swap = render(source, tmp_path, "swap", [], CutoutChoice(False, "swap", "#ff00ff"))
    blur = render(source, tmp_path, "blur", [], CutoutChoice(background="blur"))
    assert swap.shape == plain.shape == blur.shape
    corner = swap[:, *CORNER].mean(axis=(0, 1, 2))
    assert np.abs(corner - MAGENTA).max() < 8
    assert difference(swap, plain, FACE_MIDDLE) < 2
    assert difference(blur, plain, FACE_MIDDLE) < 2
    assert 2 < difference(blur, plain, CORNER) < 60


@pytest.mark.engine_segment
def test_the_subject_is_drawn_in_front_of_an_overlay(
    source: Path, tmp_path: Path
) -> None:
    plain = render(source, tmp_path, "plain", [])
    behind = render(source, tmp_path, "behind", [SKULL])
    front = render(source, tmp_path, "front", [SKULL], CutoutChoice(True))
    assert difference(behind, plain, FACE_MIDDLE) > 30
    assert difference(front, plain, FACE_MIDDLE) < 2
    assert difference(front, plain, CORNER) == 0
    covered = np.abs(behind - plain).max(axis=3) > 40
    shown = np.abs(front - plain).max(axis=3) > 40
    assert shown.sum() > 0.05 * covered.sum()
    assert shown.sum() < 0.6 * covered.sum()
    assert not list(tmp_path.glob("*.mask.mkv"))


def test_without_the_engine_the_cutout_is_skipped(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = config.settings.model_copy(update={"models_dir": tmp_path / "none"})
    monkeypatch.setattr(config, "settings", missing)
    plain = render(source, tmp_path, "plain", [SKULL])
    skipped = render(
        source, tmp_path, "skipped", [SKULL], CutoutChoice(True, "blur", "#000000")
    )
    assert np.array_equal(plain, skipped)
    assert not list(tmp_path.glob("*.mask.mkv"))
