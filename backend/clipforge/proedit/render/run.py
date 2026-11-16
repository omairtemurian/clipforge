"""Running a Pro Edit render (SPEC-v3 3.6): a 540p proxy first (quick, for
the critic and the editor's preview), then the final at the source's
resolution, both from the same graph (graph.proedit_graph).

The proxy's frame is the aspect's standard frame (aspect.aspect_size, 1080
on the short side) at PROXY_SHORT_SIDE on its short side, e.g. 540x960 for
9:16; the final's short side is the source's short side, at least the
standard 1080 (a Pro Edit is never smaller than the normal render) and at
most FINAL_SHORT_SIDE_MAX (4K: 2160x3840 for 9:16). The video is encoded
with the render settings' encoder (h264_videotoolbox when ffmpeg has it,
clipforge.encoders), the proxy with the faster PROXY_PRESET (libx264) at
the same quality, so film grain is still seen in it. The file is written
next to output and checked with ffprobe (render.render_problems: size,
H.264 yuv420p, AAC, duration within 0.2 s) before it replaces output. The
ASS files of kinetic captions (captions.py) and the mask video of a
subject cut-out (cutout_pass.py) are written next to output for the render
and deleted after it.
"""

import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

from clipforge import config
from clipforge.aspect import SHORT_SIDE, aspect_size
from clipforge.config import RenderSettings
from clipforge.encoders import encoder_args
from clipforge.ffmpeg import Arg, probe_media, run_ffmpeg
from clipforge.ffmpeg_progress import run_ffmpeg_progress
from clipforge.models import ProEditPlan
from clipforge.pipeline.loudnorm import (
    measure_filter,
    measure_loudness,
    normalize_filter,
)
from clipforge.pipeline.render import (
    AUDIO_CODEC,
    PIX_FMT,
    RenderError,
    render_problems,
)
from clipforge.proedit.edl import TypedEdlItem, validate_plan
from clipforge.proedit.pacing import JL_FRAMES
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.captions import (
    caption_files,
    loud_starts,
    needs_loud_words,
    remove_files,
)
from clipforge.proedit.render.cutout import CutoutChoice
from clipforge.proedit.render.cutout_pass import prepare_cutout
from clipforge.proedit.render.graph import (
    PRO_AUDIO,
    PRO_VIDEO,
    proedit_audio_graph,
    proedit_graph,
    undrawn,
)

logger = logging.getLogger(__name__)

Quality = Literal["proxy", "final"]
PROXY_SHORT_SIDE = 540
FINAL_SHORT_SIDE_MAX = 2160
PROXY_PRESET = "veryfast"


class UndrawnItemsError(RenderError):
    """The plan holds items that the renderer does not draw; problems names
    each one."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def output_size(
    aspect: str, quality: Quality, source_size: tuple[int, int]
) -> tuple[int, int]:
    """Return the (width, height) of a Pro Edit of aspect at quality from a
    source of source_size (width, height) pixels (module docstring)."""
    width, height = aspect_size(aspect)
    if quality == "proxy":
        short = PROXY_SHORT_SIDE
    else:
        short = min(max(min(source_size), SHORT_SIDE), FINAL_SHORT_SIDE_MAX)
    scale = short / SHORT_SIDE
    return _even(width * scale), _even(height * scale)


def quality_settings(settings: RenderSettings, quality: Quality) -> RenderSettings:
    """Return settings for a render at quality: the proxy's libx264 preset
    is PROXY_PRESET; the final's settings are settings."""
    if quality == "proxy":
        return settings.model_copy(update={"preset": PROXY_PRESET})
    return settings


def render_plan(
    base: ProEditBase,
    plan: ProEditPlan,
    output: Path,
    *,
    quality: Quality = "final",
    settings: RenderSettings | None = None,
    on_progress: Callable[[float], None] | None = None,
    master: bool = True,
    cutout: CutoutChoice | None = None,
) -> Path:
    """Render the Pro Edit of base with plan's items into output at quality
    (module docstring) with settings (by default the app's render settings
    and encoder) and return output; on_progress, if set, is passed the
    share (0..1) of the clip written so far. With master (the default) the
    sound is mastered: the dialogue chain, then the final loudness at the
    settings' target_lufs (mastered_filter). The cuts of the base get J
    and L cuts of up to pacing.JL_FRAMES[plan.intensity] frames. cutout is
    the subject cut-out the owner chose (skipped, with the reason logged,
    when its engine is not installed: cutout_pass.prepare_cutout).

    Raises EdlValidationError if the plan is not valid for the clip,
    UndrawnItemsError if an item cannot be drawn (no file is touched then),
    RenderError if the cuts leave nothing or the file fails the ffprobe
    checks and FFmpegError if ffmpeg fails; a failed render leaves no
    output file behind.
    """
    settings = quality_settings(
        config.settings.render_settings() if settings is None else settings, quality
    )
    fps = settings.fps
    base = replace(base, jl_frames=JL_FRAMES[plan.intensity])
    duration = base.duration(fps)
    if duration <= 0:
        raise RenderError(f"the cuts of {output.name} leave nothing of it")
    items = validate_plan(plan, duration)
    problems = undrawn(items, base.sounds)
    if problems:
        raise UndrawnItemsError(problems)
    source = probe_media(base.source)
    size = output_size(base.plan.aspect, quality, (source.width, source.height))
    inputs: list[Arg] = [
        "-ss", f"{base.start:.3f}", "-t", f"{base.end - base.start:.3f}",
        "-i", base.source,
    ]  # fmt: skip
    loudness = mastered_filter(base, items, fps, inputs) if master else ""
    output.unlink(missing_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    loud = loud_starts(base, inputs, fps) if needs_loud_words(items) else frozenset()
    texts = caption_files(base, items, size, output.parent, output.stem, loud)
    cut = None
    try:
        cut = prepare_cutout(
            cutout, base, items, size, fps, inputs, output.parent, output.stem
        )
        graph = proedit_graph(
            base,
            items,
            size,
            fps,
            dialogue=master,
            master=loudness,
            caption_files=texts,
            cut=cut,
        )
        _encode(graph, inputs, settings, size, duration, output, on_progress)
    finally:
        remove_files(texts)
        if cut is not None:
            cut.mask.unlink(missing_ok=True)
    logger.info(
        "rendered the Pro Edit plan %d v%d of clip %d (%s, %dx%d, %d items) as %s",
        plan.id,
        plan.version,
        plan.clip_id,
        quality,
        *size,
        len(items),
        output,
    )
    return output


def _encode(
    graph: str,
    inputs: Sequence[Arg],
    settings: RenderSettings,
    size: tuple[int, int],
    duration: float,
    output: Path,
    on_progress: Callable[[float], None] | None,
) -> None:
    """Encode the -filter_complex graph of the ffmpeg inputs with settings
    into a partial file, check it (size, duration) and move it to output;
    a failed render leaves no file behind."""
    args: list[Arg] = [
        *inputs,
        "-filter_complex",
        graph,
        "-map", PRO_VIDEO, "-map", PRO_AUDIO,
        *encoder_args(settings.encoder, settings.preset, settings.crf),
        "-pix_fmt", PIX_FMT,
        "-c:a", AUDIO_CODEC, "-b:a", settings.audio_bitrate,
        "-movflags", "+faststart",
    ]  # fmt: skip
    partial = output.with_name(f"{output.stem}.tmp{output.suffix}")
    try:
        if on_progress is None:
            run_ffmpeg([*args, partial])
        else:
            run_ffmpeg_progress([*args, partial], duration, on_progress)
        found = render_problems(probe_media(partial), size, duration)
        if found:
            raise RenderError(f"{output.name} is wrong: {'; '.join(found)}")
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, output)


def mastered_filter(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    fps: int,
    inputs: Sequence[Arg],
) -> str:
    """Return the loudnorm filter that brings the sound of the Pro Edit of
    base with items (through the dialogue chain, read with the ffmpeg
    inputs) to the app's target_lufs: its first pass measures the sound
    (pipeline/loudnorm); "" if the sound is too quiet to measure."""
    target = config.settings.target_lufs
    graph = proedit_audio_graph(
        base, items, fps, dialogue=True, master=measure_filter(target)
    )
    loudness = measure_loudness(inputs, graph, PRO_AUDIO)
    if loudness is None:
        logger.info("the sound is too quiet to measure; loudness not normalized")
        return ""
    return normalize_filter(target, loudness)


def _even(value: float) -> int:
    """Round value to the nearest even number."""
    return round(value / 2) * 2
