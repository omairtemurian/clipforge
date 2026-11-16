"""Frame captions (SPEC-v2 3.2, clip anything): what the local vision model
(engines/vlm_ollama) sees in frames of a job's timeframe -> frame_captions.json.

A frame is sampled CUT_OFFSET_S after every scene cut that the signals step
found (signals.json), so that it shows the new scene, and every
frame_caption_interval_s seconds from the timeframe's start; an interval
frame closer than MIN_GAP_S to a scene-cut frame is left out, as that frame
already shows the scene. ffmpeg decodes each frame into memory as a JPEG
FRAME_WIDTH pixels wide, and the captioner describes it. The captions are
stored by time, with the name of the model that wrote them.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.engines.vlm_ollama import Captioner, create_captioner
from clipforge.ffmpeg import FFmpegError, run_ffmpeg
from clipforge.llm_http import LLMError
from clipforge.models import (
    FrameCaption,
    FrameCaptionList,
    FrameSampleReason,
    SignalList,
)
from clipforge.pipeline.step import (
    FRAME_CAPTIONS,
    SIGNALS,
    SOURCE,
    StepError,
    StepSettings,
    is_done,
    load_json,
    load_meta,
    write_json,
)

CUT_OFFSET_S = 0.2
MIN_GAP_S = 2.0
FRAME_WIDTH = 512
JPEG_QUALITY = 4
DECIMALS = 3

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameSample:
    """A frame to caption: its source time and why it was picked."""

    time: float
    reason: FrameSampleReason


def sample_times(
    start: float, end: float, cuts: Sequence[float], interval: float
) -> list[FrameSample]:
    """Return the frames to caption in [start, end) source seconds, by time.

    Each scene cut of cuts (seconds) inside the span gives a frame
    CUT_OFFSET_S after it (at the cut if that is past end); then one frame
    every interval seconds from start, unless it is within MIN_GAP_S of a
    scene-cut frame.
    """
    scene = []
    for cut in sorted(set(cuts)):
        if start <= cut < end:
            time = cut + CUT_OFFSET_S if cut + CUT_OFFSET_S < end else cut
            scene.append(FrameSample(round(time, DECIMALS), "scene_cut"))
    regular = []
    step = 0
    while (time := start + step * interval) < end:
        if all(abs(time - frame.time) >= MIN_GAP_S for frame in scene):
            regular.append(FrameSample(round(time, DECIMALS), "interval"))
        step += 1
    return sorted(scene + regular, key=lambda frame: frame.time)


def grab_frame(video: Path, time: float) -> bytes:
    """Return the frame of video at time seconds as JPEG bytes, FRAME_WIDTH
    pixels wide. Raises StepError if ffmpeg fails or finds no frame there."""
    try:
        result = run_ffmpeg(
            [
                "-ss", f"{time:.3f}", "-i", video, "-map", "0:V:0", "-an",
                "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2",
                "-q:v", str(JPEG_QUALITY), "-f", "image2pipe", "-c:v", "mjpeg",
                "pipe:1",
            ]
        )  # fmt: skip
    except FFmpegError as exc:
        raise StepError(
            f"cannot read the frame at {time:g}s of {video}: {exc}"
        ) from exc
    if not result.stdout:
        raise StepError(f"{video} has no frame at {time:g}s")
    return result.stdout


def run(
    job_dir: Path,
    settings: StepSettings,
    *,
    force: bool = False,
    captioner: Captioner | None = None,
) -> Path:
    """Write the captions of the sampled frames of the job's timeframe to
    frame_captions.json and return its path.

    Reads meta.json, source.mp4 and the scene cuts of signals.json. The
    captioner defaults to the configured Ollama vision model
    (create_captioner). Skips the work if frame_captions.json exists, unless
    force. Raises StepError if ingest or signals has not run, a frame cannot
    be decoded, or the vision model cannot be reached or fails.
    """
    output = job_dir / FRAME_CAPTIONS
    if is_done(output, force=force):
        logger.info("%s exists; skipping frame captions", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    video = job_dir / SOURCE
    if not video.is_file():
        raise StepError(f"{video} not found; run the ingest step first")
    signals = load_json(job_dir / SIGNALS, SignalList, "signals")
    cuts = [event.start for event in signals.root if event.kind == "scene_cut"]
    samples = sample_times(
        meta.timeframe_start,
        meta.timeframe_end,
        cuts,
        settings.cfg.frame_caption_interval_s,
    )
    try:
        vlm = create_captioner() if captioner is None else captioner
        captions = []
        for done, sample in enumerate(samples, start=1):
            text = vlm.caption(grab_frame(video, sample.time))
            captions.append(
                FrameCaption(time=sample.time, reason=sample.reason, caption=text)
            )
            settings.report_progress(done / len(samples))
    except LLMError as exc:
        raise StepError(f"cannot caption the frames: {exc}") from exc
    write_json(output, FrameCaptionList(model=vlm.model, captions=captions))
    logger.info("captioned %d frames with %s", len(captions), vlm.model)
    return output
