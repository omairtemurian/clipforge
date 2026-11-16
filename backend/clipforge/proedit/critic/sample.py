"""The frames of a Pro Edit proxy render the critic looks at (SPEC-v3 3.7).

Times are frames of the rendered clip: frame n shows t = n / fps, and a
clip of duration seconds has round(duration * fps) frames. An EDL item from
t_start to t_end is sampled at its first frame, round(t_start * fps), and its
last one, round(t_end * fps) - 1 (t_end is the first frame after it); both
are kept inside the clip. The 1 fps baseline is frames 0, fps, 2 fps, ...
A frame that is both keeps both reasons.

At most max_frames frames are sent (proedit.critic_max_frames, 24): item
frames come first. When there are more item frames than the cap, max_frames
of them are spread evenly; otherwise the rest of the cap is filled with
baseline frames spread evenly. Spreading k of n ordered frames takes the
ones at index floor(i (n - 1) / (k - 1)) for i = 0..k-1 (the middle one,
index floor((n - 1) / 2), when k is 1), so the first and last are always in.

extract_frames decodes the render once and keeps the sampled frames (by
frame number, so each is exactly that frame), scaled to FRAME_WIDTH pixels
wide, as JPEGs.
"""

import io
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage

from clipforge.ffmpeg import FFmpegError, run_ffmpeg
from clipforge.models import EdlItem
from clipforge.pipeline.step import StepError
from clipforge.proedit.critic.vision import Image

FRAME_WIDTH = 360
# mjpeg -q:v (2 best .. 31 worst): small files with readable captions.
JPEG_QUALITY = 4
BASELINE = "1 fps baseline"


@dataclass(frozen=True)
class FrameSample:
    """A frame the critic sees: its number from 0, its time in the clip
    and why it was picked."""

    frame: int
    t: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SampledFrame:
    """A frame sample and its image."""

    sample: FrameSample
    image: Image
    width: int
    height: int


def frame_count(duration: float, fps: int) -> int:
    """Return the frames of a clip of duration seconds at fps (at least 1)."""
    return max(1, round(duration * fps))


def spread(frames: Sequence[int], k: int) -> list[int]:
    """Return k of the ordered frames, spread evenly (module docstring)."""
    n = len(frames)
    if k >= n:
        return list(frames)
    if k <= 0:
        return []
    if k == 1:
        return [frames[(n - 1) // 2]]
    return [frames[i * (n - 1) // (k - 1)] for i in range(k)]


def sample_frames(
    items: Sequence[EdlItem], duration: float, fps: int, max_frames: int
) -> list[FrameSample]:
    """Return the frames to send for a plan's items in a clip of duration
    seconds at fps, at most max_frames, in time order (module docstring)."""
    last = frame_count(duration, fps) - 1
    reasons: dict[int, list[str]] = {}
    for item in sorted(items, key=lambda i: (i.t_start, i.id)):
        first = min(max(round(item.t_start * fps), 0), last)
        end = min(max(round(item.t_end * fps) - 1, first), last)
        what = f"item {item.id} ({item.kind})"
        reasons.setdefault(first, []).append(f"start of {what}")
        reasons.setdefault(end, []).append(f"end of {what}")
    boundary = sorted(reasons)
    baseline = []
    for frame in range(0, last + 1, fps):
        if frame in reasons:
            reasons[frame].append(BASELINE)
        else:
            baseline.append(frame)
            reasons[frame] = [BASELINE]
    picked = spread(boundary, max_frames)
    picked += spread(baseline, max_frames - len(picked))
    return [FrameSample(n, n / fps, tuple(reasons[n])) for n in sorted(picked)]


def extract_frames(
    video: Path, samples: Sequence[FrameSample], width: int = FRAME_WIDTH
) -> list[SampledFrame]:
    """Return the images of samples' frames of video, width pixels wide.

    Raises StepError if ffmpeg fails or the video lacks one of the frames.
    """
    if not samples:
        return []
    picks = "+".join(f"eq(n,{s.frame})" for s in samples)
    with tempfile.TemporaryDirectory(prefix="critic_frames_") as tmp:
        out = Path(tmp)
        try:
            run_ffmpeg(
                [
                    "-i", video, "-map", "0:v:0",
                    "-vf", f"select='{picks}',scale={width}:-2",
                    "-fps_mode", "passthrough", "-q:v", str(JPEG_QUALITY),
                    out / "%03d.jpg",
                ]
            )  # fmt: skip
        except FFmpegError as exc:
            raise StepError(f"cannot read the frames of {video}: {exc}") from exc
        files = sorted(out.glob("*.jpg"))
        if len(files) != len(samples):
            raise StepError(
                f"{video} has {len(files)} of the {len(samples)} frames the "
                f"critic needs (last asked: frame {samples[-1].frame})"
            )
        return [
            _sampled(sample, path.read_bytes())
            for sample, path in zip(samples, files, strict=True)
        ]


def _sampled(sample: FrameSample, jpeg: bytes) -> SampledFrame:
    with PILImage.open(io.BytesIO(jpeg)) as picture:
        width, height = picture.size
    return SampledFrame(sample, Image(jpeg, "image/jpeg"), width, height)
