"""What a render of a saved clip draws, gathered once and rendered to any file
(SPEC 6.11, SPEC-v2 3.9).

render_clip_row (the clip's own video) and clip_export.export_clip (a video
at another size) both frame, caption, censor, layer and enhance the clip the
same way: prepare_render gathers it from the job's work directory and the
clip's row, run_render has render_clip draw it.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session

from clipforge import config
from clipforge.aspect import aspect_size
from clipforge.models import Clip, CropPlan
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.censor_audio import clip_censor_filter
from clipforge.pipeline.enhance import enhanced_voice
from clipforge.pipeline.framing import framed_plan
from clipforge.pipeline.hooks import Punch
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.scene_framing import scene_parts
from clipforge.pipeline.scene_graph import ScenePart
from clipforge.pipeline.step import SOURCE
from clipforge.pipeline.timeline_graph import Layer
from clipforge.timeline import clip_layers, hook_punch


@dataclass(frozen=True)
class RenderJob:
    """A clip with what its render draws: its framed crop plan, its scenes,
    the ASS file of its captions, its censor filter, its timeline layers and
    its hook's punch-in."""

    clip: Clip
    plan: CropPlan
    scenes: list[ScenePart]
    captions: Path
    censor: str
    layers: list[Layer]
    punch: Punch | None


def prepare_render(
    session: Session, clip: Clip, work: Path, captions: Path | None = None
) -> RenderJob:
    """Gather the render of clip from work, the work directory of its
    project's process job, and the session's database.

    The captions are written first (write_captions, to captions, by default
    the job's captions_<clip_id>.ass), for the clip's aspect at the standard
    size: libass scales them to a larger frame. Raises StepError if the
    clip's crop plan, the transcript or a file that the censor reads is
    missing, and ValueError if its caption template does not exist.
    """
    fps = config.settings.render.fps
    plan = framed_plan(work, clip)
    scenes = scene_parts(work, clip, plan)
    return RenderJob(
        clip,
        plan,
        scenes,
        write_captions(work, clip, aspect_size(plan.aspect), fps, captions),
        clip_censor_filter(work, clip, fps),
        clip_layers(session, clip, fps),
        hook_punch(clip, fps),
    )


def run_render(
    job: RenderJob, work: Path, output: Path, size: tuple[int, int] | None = None
) -> Path:
    """Render job's clip from work's source video into output, at size
    (width, height), by default the aspect's standard size (render_clip), and
    return output. Raises RenderError, FFmpegError or DeepFilterError if the
    render fails; no output file is then left behind."""
    clip, settings = job.clip, config.settings
    with enhanced_voice(work / SOURCE, clip.start, clip.end, clip.enhance) as voice:
        return render_clip(
            work / SOURCE,
            output,
            clip.start,
            clip.end,
            job.plan,
            clip.layout,
            settings.render_settings(),
            captions=job.captions,
            cut_ranges=clip.cut_ranges,
            segments=clip.segments,
            target_lufs=settings.target_lufs,
            size=size,
            zoom=clip.zoom_keyframes if clip.auto_zoom else (),
            scenes=job.scenes,
            auto_color=clip.auto_color,
            censor=job.censor,
            layers=job.layers,
            transitions=clip.transitions,
            punch=job.punch,
            voice=voice,
        )
