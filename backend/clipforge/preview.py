"""Low-resolution previews of clips (GET /clips/{id}/preview).

A preview is the clip rendered as its render would be (layout, crop plan,
cut ranges, captions with the hook, timeline layers) at half the output
size, 540 pixels on its short side, fast (the video_encoder at crf 28,
x264 preset veryfast) and without a loudness pass. It is cached in
{data_dir}/output/{project_id}/previews/ under a key of everything that
changes the picture, so a second request is served from the file and an
edited clip gets a new preview (its old one is deleted).
"""

import hashlib
import json
import logging
import threading
from collections.abc import Sequence
from pathlib import Path

from clipforge import config
from clipforge.aspect import aspect_size
from clipforge.config import RenderSettings
from clipforge.models import Clip, CropPlan
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.censor_audio import clip_censor_filter
from clipforge.pipeline.framing import framed_plan
from clipforge.pipeline.render import project_output, render_clip
from clipforge.pipeline.scene_framing import scene_parts
from clipforge.pipeline.step import SOURCE
from clipforge.pipeline.timeline_graph import Layer
from clipforge.timeline import hook_punch

logger = logging.getLogger(__name__)

PREVIEWS_DIRNAME = "previews"
# Previews are this fraction of the output size: 1080x1920 -> 540x960.
SCALE = 0.5
PRESET = "veryfast"
CRF = 28
AUDIO_BITRATE = "96k"

# One preview renders at a time, so two requests never write the same file.
_lock = threading.Lock()


def preview_size(plan: CropPlan) -> tuple[int, int]:
    """Return the (width, height) of a preview of a clip with plan."""
    width, height = aspect_size(plan.aspect)
    return int(width * SCALE), int(height * SCALE)


def preview_key(
    clip: Clip, plan: CropPlan, censor: str = "", layers: Sequence[Layer] = ()
) -> str:
    """Return a key of what a preview of clip with plan shows: 16 hex digits
    of a hash of its segments (times and order), layout, captions, text on
    screen, cuts, zoom, colour, scenes, timeline tracks, transitions, viral
    hook, plan (framed as the editor set it: crop offset, framing), censor,
    the audio filter of its censored words (which the custom censor list
    changes too), and the files of its layers."""
    shown = clip.model_dump(
        mode="json",
        include={
            "segments",
            "layout",
            "caption_template",
            "caption_overrides",
            "caption_style",
            "cut_ranges",
            "hook_text",
            "emphasis_words",
            "auto_zoom",
            "zoom_keyframes",
            "auto_color",
            "show_captions",
            "scene_reframes",
            "tracks",
            "transitions",
            "hook",
        },
    )
    shown["plan"] = plan.model_dump(mode="json")
    if censor:
        shown["censor"] = censor
    if layers:
        shown["layers"] = [str(layer.path) for layer in layers]
    data = json.dumps(shown, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def previews_dir(project_id: int) -> Path:
    """Return the directory of a project's previews."""
    return project_output(project_id) / PREVIEWS_DIRNAME


def render_preview(clip: Clip, work: Path, layers: Sequence[Layer] = ()) -> Path:
    """Return the preview of clip with the layers of its timeline
    (timeline.clip_layers), rendering it from work, the work directory of
    its process job, unless the current one is cached.

    Raises StepError if the clip's crop plan or the transcript is missing,
    ValueError if its caption template does not exist, and RenderError or
    FFmpegError if the render fails.
    """
    plan = framed_plan(work, clip)
    scenes = scene_parts(work, clip, plan)
    fps = config.settings.render.fps
    censor = clip_censor_filter(work, clip, fps)
    directory = previews_dir(clip.project_id)
    output = directory / f"{clip.id}-{preview_key(clip, plan, censor, layers)}.mp4"
    with _lock:
        if output.is_file():
            return output
        directory.mkdir(parents=True, exist_ok=True)
        size = preview_size(plan)
        captions = write_captions(
            work, clip, size, fps, output=output.with_suffix(".ass")
        )
        settings = RenderSettings(
            fps=fps,
            crf=CRF,
            preset=PRESET,
            audio_bitrate=AUDIO_BITRATE,
            encoder=config.settings.video_encoder,
        )
        try:
            render_clip(
                work / SOURCE,
                output,
                clip.start,
                clip.end,
                plan,
                clip.layout,
                settings,
                captions=captions,
                cut_ranges=clip.cut_ranges,
                segments=clip.segments,
                size=size,
                zoom=clip.zoom_keyframes if clip.auto_zoom else (),
                scenes=scenes,
                auto_color=clip.auto_color,
                censor=censor,
                layers=layers,
                transitions=clip.transitions,
                punch=hook_punch(clip, fps),
            )
        finally:
            captions.unlink(missing_ok=True)
        for old in directory.glob(f"{clip.id}-*.mp4"):
            if old != output:
                old.unlink(missing_ok=True)
    logger.info("rendered the preview of clip %d to %s", clip.id, output)
    return output
