"""Person segmentation for the Pro Edit subject cut-out (SPEC-v3 3.3
motion, TASK-234): the mask of the fixture's drawn face (engine_segment:
the real MediaPipe model), the install check and the fallback when the
engine is missing or broken, the mask video, the model download and the
cut-out's filters."""

import hashlib
import importlib.util
import json
import logging
from pathlib import Path

import httpx
import numpy as np
import pytest
from clipforge import config
from clipforge.engines.checks import SegmentEngine
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import ProEditOptions
from clipforge.proedit import segment
from clipforge.proedit.render import cutout_pass
from clipforge.proedit.render.cutout import (
    Cutout,
    CutoutChoice,
    cutout_choice,
    end_filters,
    front_needed,
    start_filters,
)
from clipforge.proedit.segment import (
    SEGMENTER,
    SegmentError,
    download_segmenter,
    mask_size,
    person_mask,
    person_masker,
    segmenter_path,
    segmenter_problem,
    write_masks,
)
from edl_fakes import item
from proedit_render import base_of

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MASK = (288, 512)
CROP_WIDTH = 404


@pytest.fixture
def models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty models directory as the app's models_dir."""
    folder = tmp_path / "models"
    cfg = config.settings.model_copy(update={"models_dir": folder})
    monkeypatch.setattr(config, "settings", cfg)
    return folder


def face_frames(at: float, count: int) -> tuple[np.ndarray, np.ndarray]:
    """count frames of the fixture from at seconds, cut to a 9:16 window
    around its drawn face and scaled to MASK, and the face's ellipse (True
    inside) in them (expected.json: a 240x300 head moving left to
    right)."""
    face = json.loads((FIXTURES / "expected.json").read_text())["face"]
    start, end = face["start"], face["end"]
    center_x = start["center_x"] + (end["center_x"] - start["center_x"]) * (
        at / (end["t"] - start["t"])
    )
    left = round(center_x) - CROP_WIDTH // 2
    width, height = MASK
    result = run_ffmpeg(
        ["-ss", f"{at}", "-i", FIXTURES / "sample.mp4", "-vf"]
        + [f"crop={CROP_WIDTH}:720:{left}:0,scale={width}:{height}"]
        + ["-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    frames = np.frombuffer(result.stdout, np.uint8).reshape(-1, height, width, 3)
    scale_x, scale_y = width / CROP_WIDTH, height / 720
    rows, columns = np.mgrid[0:height, 0:width]
    dx = (columns - (center_x - left) * scale_x) / (face["width"] / 2 * scale_x)
    dy = (rows - start["center_y"] * scale_y) / (face["height"] / 2 * scale_y)
    return frames, dx**2 + dy**2 <= 1


@pytest.mark.engine_segment
@pytest.mark.parametrize("at", [4.0, 9.0, 14.0])
def test_the_mask_covers_the_drawn_face(at: float) -> None:
    frames, face = face_frames(at, 10)
    with person_masker(config.settings, 30) as mask:
        masks = [mask(frame) for frame in frames]
    found = masks[-1] > 127
    assert found.shape == face.shape
    assert found[face].mean() >= 0.9
    top = int(np.argmax(face.any(axis=1))) - 10
    assert (masks[-1][:top] / 255).mean() < 0.1


def test_the_install_check_says_what_is_missing(
    models: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problem = segmenter_problem(config.settings)
    assert problem is not None and "download_models.py" in problem
    assert SegmentEngine("segment", "S").install_check().error == problem
    path = segmenter_path(config.settings)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"model")
    assert segmenter_problem(config.settings) is None
    assert SegmentEngine("segment", "S").install_check().installed
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "mediapipe" else real(name, *a),
    )
    assert segmenter_problem(config.settings) == (
        "the Python package mediapipe is not installed"
    )


def test_a_broken_model_raises_a_segment_error(models: Path) -> None:
    with pytest.raises(SegmentError, match="download_models.py"):
        with person_masker(config.settings, 30):
            pass
    path = segmenter_path(config.settings)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a tflite model")
    with pytest.raises(SegmentError, match="cannot load the segmentation model"):
        with person_masker(config.settings, 30):
            pass


@pytest.mark.parametrize("broken", [False, True], ids=["missing", "broken"])
def test_the_cutout_is_skipped_with_the_reason_logged(
    models: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture, broken: bool
) -> None:
    if broken:
        path = segmenter_path(config.settings)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"not a tflite model")
    base = base_of(FIXTURES / "sample.mp4")
    choice = CutoutChoice(background="blur")
    inputs = ["-ss", "1.000", "-t", "0.200", "-i", FIXTURES / "sample.mp4"]
    with caplog.at_level(logging.WARNING, logger=cutout_pass.__name__):
        cut = cutout_pass.prepare_cutout(
            choice, base, [], (270, 480), 30, inputs, tmp_path, "clip"
        )
    assert cut is None
    reason = "cannot load" if broken else "is not downloaded"
    assert "subject cut-out skipped" in caplog.text and reason in caplog.text
    assert not cutout_pass.mask_path(tmp_path, "clip").exists()


def test_a_cutout_that_changes_nothing_needs_no_engine(
    models: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = base_of(FIXTURES / "sample.mp4")
    args = (base, [], (270, 480), 30, [], tmp_path, "clip")
    assert cutout_pass.prepare_cutout(None, *args) is None
    assert cutout_pass.prepare_cutout(CutoutChoice(), *args) is None
    with caplog.at_level(logging.INFO, logger=cutout_pass.__name__):
        front = CutoutChoice(subject_front=True)
        assert cutout_pass.prepare_cutout(front, *args) is None
    assert "no overlay or caption" in caplog.text


def test_masks_are_written_losslessly_and_a_wrong_size_leaves_no_file(
    tmp_path: Path,
) -> None:
    width, height = 64, 36
    masks = [np.full((height, width), n * 50, np.uint8) for n in range(4)]
    masks[1][:10, :10] = 255
    video = tmp_path / "mask.mkv"
    assert write_masks(masks, video, (width, height), 30) == 4
    info = probe_media(video)
    assert (info.width, info.height) == (width, height)
    result = run_ffmpeg(["-i", video, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"])
    decoded = np.frombuffer(result.stdout, np.uint8).reshape(-1, height, width)
    assert np.array_equal(decoded, np.stack(masks))
    wrong = tmp_path / "wrong.mkv"
    with pytest.raises(SegmentError, match="not 64x36"):
        write_masks([masks[0], np.zeros((10, 10), np.uint8)], wrong, (64, 36), 30)
    assert not wrong.exists()


class FakeMask:
    """A MediaPipe confidence mask (numpy_view: [row, column, 1])."""

    def __init__(self, values: np.ndarray) -> None:
        self.values = values

    def numpy_view(self) -> np.ndarray:
        return self.values


def test_the_person_mask_is_the_last_confidence_mask_in_bytes() -> None:
    person = np.array([[[0.0], [0.5]], [[1.0], [0.25]]], dtype=np.float32)
    background = FakeMask(1 - person)
    found = person_mask([background, FakeMask(person)], (2, 2, 3))
    assert found.tolist() == [[0, 128], [255, 64]]
    assert person_mask([], (2, 3, 3)).tolist() == [[0, 0, 0], [0, 0, 0]]


def test_mask_size_keeps_the_aspect_on_a_short_side_of_288() -> None:
    assert mask_size((540, 960)) == MASK
    assert mask_size((1080, 1920)) == MASK
    assert mask_size((1920, 1080)) == (512, 288)
    assert mask_size((100, 200)) == (100, 200)


def test_the_model_download_checks_its_sha256(
    models: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"selfie segmenter"
    wrong = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    with pytest.raises(RuntimeError, match="sha256"):
        download_segmenter(config.settings, transport=wrong)
    assert not segmenter_path(config.settings).exists()
    pinned = SEGMENTER._replace(sha256=hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(segment, "SEGMENTER", pinned)
    folder = download_segmenter(config.settings, transport=wrong)
    assert (folder / SEGMENTER.name).read_bytes() == body


def test_options_map_to_the_cutout_choice() -> None:
    assert not cutout_choice(ProEditOptions()).active
    options = ProEditOptions(
        subject_front=True, background="swap", background_color="#00ff00"
    )
    assert cutout_choice(options) == CutoutChoice(True, "swap", "#00ff00")
    caption = item(1, "caption_style", 0, 1, params={"style": "neon_pop"})
    overlay = item(2, "overlay", 0, 1)
    choice = CutoutChoice(subject_front=True)
    assert not front_needed(choice, [item(3, "flash", 0, 0.1, params={})])
    assert front_needed(choice, [caption]) and front_needed(choice, [overlay])
    assert not front_needed(CutoutChoice(background="blur"), [overlay])


def test_the_filters_blur_or_swap_the_background_and_redraw_the_subject(
    tmp_path: Path,
) -> None:
    mask = tmp_path / "m.mkv"
    assert start_filters(None, (540, 960), 30) == [] and end_filters(None) == []
    blur = start_filters(Cutout(mask, False, "blur", "#000000"), (540, 960), 30)
    assert "gblur=sigma=19.2" in blur[0] and "[co_front]" not in blur[0]
    assert "setpts=N,scale=540:960" in blur[0]
    swap = start_filters(Cutout(mask, True, "swap", "#00FF7F"), (540, 960), 30)
    assert "color=0x00FF7F@1:t=fill" in swap[0]
    assert "split=2[co_subject][co_front]" in swap[0]
    front = Cutout(mask, True, "keep", "#000000")
    kept = start_filters(front, (540, 960), 30)[0]
    assert "alphamerge[co_front]" in kept and kept.endswith("[co_back]null")
    assert "[co_front]overlay" in end_filters(front)[0]
    assert start_filters(Cutout(mask, False, "keep", "#000000"), (540, 960), 30) == []
