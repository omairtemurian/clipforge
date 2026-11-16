"""Person segmentation for the subject cut-out of a Pro Edit (SPEC-v3 3.3
motion): which pixels of a frame are the subject, so the render can put
the subject in front of overlays and captions and blur or swap the
background (render/cutout.py, render/cutout_pass.py).

The engine is MediaPipe's Image Segmenter task (mediapipe 0.10.33, Tasks
API: `vision.ImageSegmenter` in VIDEO mode, `segment_for_video(image,
timestamp_ms)`, confidence masks; verified on the installed package,
docs/decisions.md) with the SelfieSegmenter (square, 256 x 256, float16)
model, Apache-2.0 per its model card: two categories, background 0 and
person 1; with confidence masks only, the result holds one float32 mask
[row, column, 1] of the person's confidence (0..1) at the input's size.
The model lives in cfg.models_dir/segment and is downloaded by
scripts/download_models.py (download_segmenter), never at render time.

segmenter_problem is the engine's install check (the `segment` engine,
engines/checks.SegmentEngine): it only looks for the package and the model
file; person_masker loads the model and raises SegmentError when it cannot.
Masks are worked out on frames of MASK_SHORT_SIDE pixels on their short
side (the model sees 256 x 256 anyway) and written as a lossless gray FFV1
video (write_masks) that the render scales up to its frames.
"""

import importlib.util
import logging
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import numpy.typing as npt

from clipforge.config import Settings
from clipforge.ffmpeg import FFmpegError, _arg, ffmpeg_bin
from clipforge.model_files import ModelFile, download_model_file

logger = logging.getLogger(__name__)

SEGMENT_DIRNAME = "segment"
SEGMENTER = ModelFile(
    "selfie_segmenter.tflite",
    "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_segmenter/float16/1/selfie_segmenter.tflite",
    "191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b",
)
MASK_SHORT_SIDE = 288
MASK_CODEC = "ffv1"
MASK_SUFFIX = ".mkv"

Frame = npt.NDArray[np.uint8]
# A mask is uint8 [row, column]: 255 where the frame shows the subject.
Mask = npt.NDArray[np.uint8]


class SegmentError(RuntimeError):
    """The segmentation model cannot be loaded or run."""


def segmenter_path(cfg: Settings) -> Path:
    """Return the path of the SEGMENTER model in models_dir/segment."""
    return cfg.models_dir / SEGMENT_DIRNAME / SEGMENTER.name


def segmenter_problem(cfg: Settings) -> str | None:
    """Return why the subject cut-out cannot run on this machine (no
    mediapipe package, no model file), or None when it can. Only looks:
    nothing is imported or loaded."""
    if importlib.util.find_spec("mediapipe") is None:
        return "the Python package mediapipe is not installed"
    path = segmenter_path(cfg)
    if not path.is_file():
        return (
            f"the segmentation model is not downloaded: {path} is missing; "
            "run `uv run python scripts/download_models.py`"
        )
    return None


def download_segmenter(
    cfg: Settings,
    *,
    force: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    """Download the SEGMENTER model into models_dir/segment (unless it is
    there, or force) and return that directory. transport, if given,
    carries the HTTP requests (httpx.MockTransport in tests). Raises like
    model_files.download_model_file (a wrong sha256 leaves no file)."""
    path = segmenter_path(cfg)
    if force or not path.is_file():
        download_model_file(SEGMENTER, path, transport)
    else:
        logger.info("%s is in %s", SEGMENTER.name, path.parent)
    return path.parent


def mask_size(size: tuple[int, int]) -> tuple[int, int]:
    """Return the (width, height) of the masks of size (width, height)
    frames: MASK_SHORT_SIDE on the short side (never larger than the
    frames), even, same aspect."""
    scale = min(1.0, MASK_SHORT_SIDE / min(size))
    return _even(size[0] * scale), _even(size[1] * scale)


@contextmanager
def person_masker(cfg: Settings, fps: int) -> Iterator[Callable[[Frame], Mask]]:
    """Load the SEGMENTER model and yield a function that returns the
    subject mask of the next RGB frame of a video at fps (frames must come
    in order: VIDEO mode). The model is closed when the block ends.

    Raises SegmentError if the engine is missing or the model cannot be
    loaded or run.
    """
    problem = segmenter_problem(cfg)
    if problem is not None:
        raise SegmentError(problem)
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(segmenter_path(cfg))),
        running_mode=vision.RunningMode.VIDEO,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    try:
        segmenter = vision.ImageSegmenter.create_from_options(options)
    except Exception as exc:  # the C library's errors subclass only Exception
        raise SegmentError(
            f"cannot load the segmentation model {segmenter_path(cfg)}: {exc}; "
            "download it again with "
            "`uv run python scripts/download_models.py --force`"
        ) from exc
    count = 0

    def mask(frame: Frame) -> Mask:
        nonlocal count
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame)
        )
        try:
            result = segmenter.segment_for_video(image, round(count * 1000 / fps))
        except Exception as exc:
            raise SegmentError(f"segmentation failed on frame {count}: {exc}") from exc
        count += 1
        return person_mask(result.confidence_masks, frame.shape[:2])

    with segmenter:
        yield mask


def person_mask(masks: list[Any], shape: tuple[int, ...]) -> Mask:
    """Return the person's confidence of MediaPipe's confidence masks (the
    last category, person) as a uint8 mask of shape (rows, columns)."""
    if not masks:
        return np.zeros(shape[:2], dtype=np.uint8)
    found = np.asarray(masks[-1].numpy_view(), dtype=np.float32)
    found = found.reshape(found.shape[0], found.shape[1])
    return np.asarray(np.clip(found * 255 + 0.5, 0, 255), dtype=np.uint8)


def write_masks(
    masks: Iterable[Mask], output: Path, size: tuple[int, int], fps: int
) -> int:
    """Write masks, each size (width, height), as a lossless gray video at
    fps (MASK_CODEC) to output and return how many were written. A failed
    write leaves no file. Raises FFmpegError if ffmpeg fails and
    SegmentError if a mask has another size."""
    width, height = size
    command = [
        ffmpeg_bin(), "-nostdin", "-hide_banner", "-nostats", "-loglevel", "error",
        "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "pipe:0", "-c:v", MASK_CODEC, "-pix_fmt", "gray",
        _arg(output),
    ]  # fmt: skip
    written = 0
    with tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=stderr)
        assert process.stdin is not None
        try:
            try:
                for mask in masks:
                    if mask.shape != (height, width):
                        raise SegmentError(
                            f"mask {written} is {mask.shape[1]}x{mask.shape[0]}, "
                            f"not {width}x{height}"
                        )
                    process.stdin.write(np.ascontiguousarray(mask).tobytes())
                    written += 1
                process.stdin.close()
            except BrokenPipeError:
                pass  # ffmpeg stopped reading: its status and stderr say why
            status = process.wait()
        except BaseException:
            process.kill()
            process.wait()
            output.unlink(missing_ok=True)
            raise
        if status != 0:
            output.unlink(missing_ok=True)
            stderr.seek(0)
            raise FFmpegError(
                f"{command[0]} exited with status {status}",
                command=command,
                stderr=stderr.read().decode("utf-8", errors="replace"),
            )
    return written


def _even(value: float) -> int:
    """Round value to the nearest even number, at least 2."""
    return max(2, round(value / 2) * 2)
