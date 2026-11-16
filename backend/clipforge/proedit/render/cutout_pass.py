"""The pre-pass of a subject cut-out (cutout.py; SPEC-v3 3.3 motion): the
frames as the stages before the overlays leave them
(graph.PRE_CUTOUT_STAGES: the same filters as the render, so frame n is
the render's frame n there) are scaled to the masks' size
(segment.mask_size), streamed out of ffmpeg as rgb24, segmented
(segment.person_masker) and written as the mask video the render reads.

The cut-out is optional: when it would change nothing (no background
change, and no overlay or caption to put the subject in front of) or its
engine is not installed or fails to load, the render goes on without it
and the log says why.
"""

import logging
from collections.abc import Sequence
from pathlib import Path

from clipforge import config
from clipforge.ffmpeg import Arg, _arg, ffmpeg_bin
from clipforge.ffmpeg_args import spilled_args
from clipforge.pipeline.frame_stream import stream_raw
from clipforge.pipeline.layouts import VIDEO_OUT
from clipforge.pipeline.render_graph import AUDIO_OUT
from clipforge.proedit.edl import TypedEdlItem
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.cutout import Cutout, CutoutChoice, front_needed
from clipforge.proedit.render.graph import (
    PRE_CUTOUT_STAGES,
    canvas_of,
    framed_graph,
    video_chain,
)
from clipforge.proedit.segment import (
    MASK_SUFFIX,
    SegmentError,
    mask_size,
    person_masker,
    segmenter_problem,
    write_masks,
)

logger = logging.getLogger(__name__)

MASK_FRAMES = "[cut_frames]"
SKIPPED = "subject cut-out skipped: %s"


def mask_path(folder: Path, stem: str) -> Path:
    """Return the mask video of the render stem in folder."""
    return folder / f"{stem}.mask{MASK_SUFFIX}"


def prepare_cutout(
    choice: CutoutChoice | None,
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    size: tuple[int, int],
    fps: int,
    inputs: Sequence[Arg],
    folder: Path,
    stem: str,
) -> Cutout | None:
    """Return the cut-out of choice for the Pro Edit of base with items as
    size frames at fps (read with the ffmpeg inputs), its masks written to
    mask_path(folder, stem); None, with the reason logged, when it is
    skipped (module docstring). Raises FFmpegError if ffmpeg fails."""
    if choice is None or not choice.active:
        return None
    front = front_needed(choice, items)
    if not front and choice.background == "keep":
        logger.info(SKIPPED, "no overlay or caption to put the subject in front of")
        return None
    problem = segmenter_problem(config.settings)
    if problem is not None:
        logger.warning(SKIPPED, problem)
        return None
    output = mask_path(folder, stem)
    try:
        count = segment_frames(base, items, size, fps, inputs, output)
    except SegmentError as error:
        output.unlink(missing_ok=True)
        logger.warning(SKIPPED, error)
        return None
    logger.info("segmented %d frames of %s for the subject cut-out", count, stem)
    return Cutout(output, front, choice.background, choice.color)


def pre_cutout_graph(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    size: tuple[int, int],
    fps: int,
) -> str:
    """Return the -filter_complex graph of the frames of the Pro Edit of
    base with items before the overlays (PRE_CUTOUT_STAGES), scaled to the
    masks' size as rgb24, in MASK_FRAMES; the sound is dropped."""
    width, height = mask_size(size)
    chain = video_chain(items, canvas_of(base, items, size, fps), PRE_CUTOUT_STAGES)
    return (
        f"{framed_graph(base, size, fps)};{VIDEO_OUT}{chain},"
        f"scale={width}:{height}:flags=area,format=rgb24{MASK_FRAMES};"
        f"{AUDIO_OUT}anullsink"
    )


def segment_frames(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    size: tuple[int, int],
    fps: int,
    inputs: Sequence[Arg],
    output: Path,
) -> int:
    """Write the subject masks of the frames of pre_cutout_graph to output
    (segment.write_masks) and return how many there are. Raises
    SegmentError if the model cannot run and FFmpegError if ffmpeg
    fails."""
    small = mask_size(size)
    command = [
        ffmpeg_bin(), "-nostdin", "-hide_banner", "-nostats", "-loglevel", "error",
        *(_arg(arg) for arg in inputs),
        "-filter_complex", pre_cutout_graph(base, items, size, fps),
        "-map", MASK_FRAMES, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]  # fmt: skip
    with (
        spilled_args(command) as args,
        person_masker(config.settings, fps) as mask,
    ):
        frames = stream_raw(args, small)
        return write_masks((mask(frame) for frame in frames), output, small, fps)
