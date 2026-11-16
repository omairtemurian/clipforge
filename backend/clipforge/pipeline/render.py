"""Render one clip of a job's source video to an mp4 (SPEC 6.11).

render_clip trims [start, end] from source.mp4 and leaves out the clip's
cut_ranges, in whole frames (frame_cuts.kept_spans), and the gaps between
its segments, which it plays in their order (sections.played_spans). It
frames the clip in its
layout with its crop plan (pipeline/layouts: fill, fit or split, at the
aspect's SPEC size), burns in the clip's captions (the ASS file of
pipeline/captions, drawn by libass with ffmpeg's subtitles filter and the
bundled fonts of clipforge.fonts), all in one filter graph
(pipeline/render_graph), normalizes its loudness in two passes
(pipeline/loudnorm) and encodes H.264 yuv420p (libx264 or VideoToolbox) and
AAC with the render settings, with the index (moov) at the front of the file
(+faststart). Its censored words are beeped or muted after the cuts
(pipeline/censor). The layers of the clip's timeline (B-roll, overlays,
text, music, sound effects, voiceover: pipeline/timeline_graph) are drawn
on its frames and mixed into its sound after the cuts and loudnorm.
ffprobe checks the result before it replaces the output, so a clip's file
either passes the checks or does not exist. There is no brand pass yet.

Rendering works per clip and writes into {data_dir}/output, outside the job's
work directory, so it is not one of the steps in STEP_NAMES.
"""

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge import config
from clipforge.aspect import PRESETS, aspect_size
from clipforge.config import RenderSettings, Settings
from clipforge.encoders import encoder_args
from clipforge.ffmpeg import Arg, MediaInfo, probe_media, run_ffmpeg
from clipforge.models import (
    ClipTransitions,
    CropPlan,
    CutRange,
    Layout,
    SourceSpan,
    ZoomKeyframe,
)
from clipforge.pipeline.hooks import Punch, punch_filter
from clipforge.pipeline.layouts import VIDEO_OUT
from clipforge.pipeline.loudnorm import (
    measure_filter,
    measure_loudness,
    normalize_filter,
)
from clipforge.pipeline.render_graph import (
    AUDIO_IN,
    AUDIO_OUT,
    audio_graph,
    clip_graph,
)
from clipforge.pipeline.scene_graph import ScenePart
from clipforge.pipeline.sections import played_spans
from clipforge.pipeline.timeline_graph import (
    FIRST_INPUT,
    Layer,
    has_sounds,
    layer_inputs,
    numbered,
)
from clipforge.pipeline.transitions import clip_joins

logger = logging.getLogger(__name__)

OUTPUT_DIRNAME = "output"
# The output frame size (width, height) of each aspect (SPEC 6.11).
# The presets' sizes; aspect_size also sizes a custom W:H.
SIZES: dict[str, tuple[int, int]] = {name: aspect_size(name) for name in PRESETS}
# How far a rendered clip's duration may be from end - start (SPEC 6.11).
DURATION_TOLERANCE_S = 0.2
VIDEO_CODEC = "h264"
PIX_FMT = "yuv420p"
AUDIO_CODEC = "aac"


class RenderError(RuntimeError):
    """A clip cannot be rendered: its cuts leave nothing of it, or the
    rendered file failed the ffprobe checks and was removed."""


@dataclass(frozen=True)
class Crop:
    """A width x height window of a frame whose top-left corner is at (x, y)."""

    width: int
    height: int
    x: int
    y: int


def project_output(project_id: int, cfg: Settings | None = None) -> Path:
    """Return the directory of a project's rendered clips and exports (SPEC
    6.11, 6.12): {data_dir}/output/{project_id}."""
    data_dir = (config.settings if cfg is None else cfg).data_dir
    return data_dir / OUTPUT_DIRNAME / str(project_id)


def clip_output(project_id: int, clip_id: int, cfg: Settings | None = None) -> Path:
    """Return the path of a rendered clip (SPEC 6.11):
    {data_dir}/output/{project_id}/{clip_id}.mp4."""
    return project_output(project_id, cfg) / f"{clip_id}.mp4"


def center_crop(src_width: int, src_height: int, width: int, height: int) -> Crop:
    """Return the largest centered window of a source frame with the shape
    width:height.

    The window keeps the full height of a source that is wider than that
    shape, and the full width otherwise. Its size and position are rounded
    down to even numbers, because yuv420p frames are cut at even pixels; the
    small change of shape this causes is undone by scaling to the output size.
    """
    if src_width * height > src_height * width:
        crop_width, crop_height = src_height * width // height, src_height
    else:
        crop_width, crop_height = src_width, src_width * height // width
    crop_width, crop_height = max(_even(crop_width), 2), max(_even(crop_height), 2)
    return Crop(
        crop_width,
        crop_height,
        _even((src_width - crop_width) // 2),
        _even((src_height - crop_height) // 2),
    )


def render_problems(
    info: MediaInfo, size: tuple[int, int], duration: float
) -> list[str]:
    """Return what is wrong with a rendered clip that ffprobe described as info.

    A clip must be size (width, height), last duration seconds within
    DURATION_TOLERANCE_S (compared to the millisecond, so float noise cannot
    push a difference of exactly 0.2 s over it), and hold H.264 yuv420p video
    and AAC audio. Returns an empty list for a good clip.
    """
    problems = []
    if (info.width, info.height) != size:
        problems.append(f"size {info.width}x{info.height} is not {size[0]}x{size[1]}")
    if round(abs(info.duration - duration), 3) > DURATION_TOLERANCE_S:
        problems.append(
            f"duration {info.duration:.3f}s is not {duration:.3f}s "
            f"(±{DURATION_TOLERANCE_S}s)"
        )
    if (info.video_codec, info.pix_fmt) != (VIDEO_CODEC, PIX_FMT):
        problems.append(f"video {info.video_codec} {info.pix_fmt} is not h264 yuv420p")
    if info.audio_codec != AUDIO_CODEC:
        problems.append(f"audio {info.audio_codec} is not {AUDIO_CODEC}")
    return problems


def render_clip(
    source: Path,
    output: Path,
    start: float,
    end: float,
    plan: CropPlan,
    layout: Layout,
    settings: RenderSettings,
    *,
    captions: Path | None = None,
    cut_ranges: Sequence[CutRange] = (),
    segments: Sequence[SourceSpan] = (),
    target_lufs: float | None = None,
    size: tuple[int, int] | None = None,
    zoom: Sequence[ZoomKeyframe] = (),
    scenes: Sequence[ScenePart] = (),
    auto_color: bool = False,
    censor: str = "",
    layers: Sequence[Layer] = (),
    transitions: ClipTransitions | None = None,
    punch: Punch | None = None,
    voice: Path | None = None,
) -> Path:
    """Render source from start to end seconds into output, without its
    cut_ranges (whole frames: frame_cuts.kept_spans), playing segments (the
    clip's, from start to end; none: one from start to end) in their order
    without the gaps between them (sections.played_spans), framed in layout
    with the
    crop plan of the clip (pipeline/layouts), or scene by scene as scenes
    say (pipeline/scene_graph), with the clip's captions burnt
    in if captions is the path of their ASS file (pipeline/captions, written
    for this frame size and fps), zoomed as the zoom keyframes zoom say
    (pipeline/zoom_graph), its colours levelled if auto_color
    (render_graph.COLOR_FILTER), its sound after the cuts passed through
    the audio filter censor if set (pipeline/censor: the words it beeps or
    mutes), and with its loudness normalized to target_lufs if set
    (pipeline/loudnorm), as censored. The timeline's layers, with times
    in seconds of the rendered clip, are drawn on its frames and mixed into
    its sound after that (pipeline/timeline_graph). The video's cuts get
    the transitions, if set (pipeline/transitions), which keep its length,
    and its frames punch in as punch says, if set (a viral hook's punch-in,
    pipeline/hooks), under the layers. If voice is a WAV of the clip's
    sound from start (pipeline/enhance.enhance_span), it replaces the
    source's sound.

    The video is size (width, height), by default aspect_size(plan.aspect), at
    settings.fps, encoded with settings.encoder (clipforge.encoders: libx264
    with settings.preset and settings.crf, or h264_videotoolbox at the
    matching quality), and the audio AAC at
    settings.audio_bitrate. The file is written next to output and checked
    with ffprobe (render_problems, against the length of the kept parts)
    before it replaces output. Returns output. Raises RenderError if the cuts
    leave nothing or the check fails, and FFmpegError if ffmpeg fails (as it
    does if captions does not exist); either way, no output file is left
    behind.
    """
    size = aspect_size(plan.aspect) if size is None else size
    sections = segments or [(start, end)]
    spans = played_spans(start, end, sections, cut_ranges, settings.fps)
    output.unlink(missing_ok=True)
    if not spans:
        raise RenderError(f"the cuts of {output.name} leave nothing of it")
    cuts = spans if cut_ranges or len(sections) > 1 else []
    joins = (
        clip_joins(start, end, sections, cut_ranges, transitions, settings.fps)
        if cuts and transitions is not None
        else []
    )
    inputs: list[Arg] = [
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{end - start:.3f}",
        "-i",
        source,
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.stem}.tmp{output.suffix}")
    try:
        loudness = _loudnorm_filters(inputs, cuts, target_lufs, censor, voice)
        audio = ",".join(f for f in (censor, loudness) if f)
        if voice is not None and not audio:
            audio = "anull"
        voice_in = AUDIO_IN
        if voice is not None:
            number = FIRST_INPUT + sum(n is not None for _, n in numbered(layers))
            voice_in = f"[{number}:a:0]"
        graph = clip_graph(
            plan,
            layout,
            start,
            size,
            settings.fps,
            captions,
            spans=cuts,
            audio=audio,
            zoom=zoom,
            scenes=scenes,
            auto_color=auto_color,
            layers=layers,
            joins=joins,
            punch=punch_filter(punch, size),
            voice=voice_in,
        )
        mapped = cuts or audio or has_sounds(layers)
        run_ffmpeg(
            [
                *inputs, *layer_inputs(layers, settings.fps),
                *(["-i", str(voice)] if voice is not None else []),
                "-filter_complex", graph, "-map", VIDEO_OUT,
                "-map", AUDIO_OUT if mapped else "0:a:0",
                *encoder_args(settings.encoder, settings.preset, settings.crf),
                "-pix_fmt", PIX_FMT,
                "-c:a", AUDIO_CODEC, "-b:a", settings.audio_bitrate,
                "-movflags", "+faststart", partial,
            ]
        )  # fmt: skip
        duration = sum(span_end - span_start for span_start, span_end in spans)
        problems = render_problems(probe_media(partial), size, duration)
        if problems:
            raise RenderError(f"{output.name} is wrong: {'; '.join(problems)}")
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, output)
    logger.info(
        "rendered %.1f-%.1fs as %s (%s, %s)",
        start,
        end,
        output,
        plan.aspect,
        layout,
    )
    return output


def _loudnorm_filters(
    inputs: Sequence[Arg],
    spans: Sequence[tuple[float, float]],
    target_lufs: float | None,
    censor: str = "",
    voice: Path | None = None,
) -> str:
    """Return the audio filters that bring the clip's audio (read with the
    ffmpeg inputs, or from the WAV voice, cut to spans and through the
    censor filter) to
    target_lufs, once its first pass has measured it (pipeline/loudnorm);
    "" if target_lufs is None or the audio is too quiet to measure."""
    if target_lufs is None:
        return ""
    measure = ",".join(f for f in (censor, measure_filter(target_lufs)) if f)
    if voice is None:
        graph = audio_graph(spans, measure)
    else:
        inputs = [*inputs, "-i", voice]
        graph = audio_graph(spans, measure, f"[{FIRST_INPUT}:a:0]")
    loudness = measure_loudness(inputs, graph, AUDIO_OUT)
    if loudness is None:
        logger.info("audio too quiet to measure; loudness not normalized")
        return ""
    return normalize_filter(target_lufs, loudness)


def _even(value: int) -> int:
    """Round a non-negative value down to an even number."""
    return value - value % 2
