"""A project's clips: saving scored candidates as clip rows, rendering and
exporting them.

The clips of a project are the candidates that score kept, best overall
score first, with the starts and ends that snap moved between words
(snapped.json) and, if the project removes fillers, the filler cuts of
pipeline/polish. Each is rendered in its layout with its crop plan
(crop_<clip_id>.json, pipeline/reframe) and its captions
(captions_<clip_id>.ass, pipeline/captions) from its process job's work
directory, and its SRT subtitles and metadata JSON (pipeline/export) are
written next to its video (clip_render gathers a clip's render inputs and
runs the render; clip_export renders a clip again at another resolution or
for a platform preset, export_presets); export_project zips the rendered clips, and
export_premiere writes all the clips as Premiere XML (pipeline/premiere).
"""

import logging
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from clipforge import config, notifications, webhook_events
from clipforge.clip_graphics import brand_style_of
from clipforge.clip_render import prepare_render, run_render
from clipforge.db import ClipRow, ProjectRow
from clipforge.engines.deepfilternet import DeepFilterError
from clipforge.ffmpeg import FFmpegError
from clipforge.models import (
    CaptionStyle,
    Clip,
    ClipStatus,
    Layout,
    ProcessingSettings,
    ScoredCandidate,
)
from clipforge.pipeline.auto_cut import new_clip_cuts
from clipforge.pipeline.auto_zoom import new_clip_zooms
from clipforge.pipeline.export import (
    metadata_path,
    srt_path,
    write_metadata,
    write_srt,
    write_zip,
)
from clipforge.pipeline.headline import new_clip_tracks
from clipforge.pipeline.premiere import write_premiere_xml
from clipforge.pipeline.render import (
    RenderError,
    clip_output,
    project_output,
)
from clipforge.pipeline.step import StepError
from clipforge.timeline import timeline_of

logger = logging.getLogger(__name__)

# How a clip is framed until reframe chooses (clip_layouts.set_planned_layouts).
DEFAULT_LAYOUT: Layout = "fill"
# The zip of a project's rendered clips, in its output directory.
ZIP_NAME = "clips.zip"
# The Premiere XML of a project's clips, in its output directory.
PREMIERE_NAME = "premiere.xml"


def save_clips(
    engine: Engine,
    project_id: int,
    candidates: Sequence[ScoredCandidate],
    processing: ProcessingSettings,
    work: Path,
    result_set: int = 1,
) -> list[int]:
    """Save scored candidates, best first, as the clips of a project, in its
    result set result_set (reprompt makes the next one).

    The clips are added in the order of candidates, each with one segment
    from its start to its end (and its video track, timeline_of), scores,
    status candidate, the default layout and the project's caption template.
    Their cut_ranges are their filler cuts with processing.remove_fillers on
    and their auto cuts (silences) with processing.auto_cut on
    (auto_cut.new_clip_cuts), from the transcript and signals in work, the
    job's work directory, which is otherwise not read; auto_cut is copied to
    each clip. With processing.auto_zoom on, each clip gets its punch-ins
    (auto_zoom.new_clip_zooms) and auto_zoom on. The clips keep the LLM's
    hook text only with processing.auto_headline on, also as a headline
    item in the style of processing's brand template if it picks one
    (headline.new_clip_tracks), and get auto_color and
    show_captions (processing.captions) as processing says. Returns their ids in the
    same order; raises StepError if a file that it reads is missing.
    """
    spans = [(c.start, c.end) for c in candidates]
    cuts = new_clip_cuts(work, spans, processing)
    zooms = new_clip_zooms(
        work, [(c.start, c.end, c.emphasis_words) for c in candidates], processing
    )
    style = brand_style_of(engine, processing.brand_template_id)
    fps = config.settings.render.fps
    rows = [
        ClipRow(
            project_id=project_id,
            segments=[(c.start, c.end)],
            tracks=new_clip_tracks(
                timeline_of([(c.start, c.end)]),
                (c.start, c.end),
                cut_ranges,
                c.hook_text if processing.auto_headline else "",
                style,
                fps,
            ),
            title=c.title,
            hook_text=c.hook_text if processing.auto_headline else "",
            description=c.description,
            hashtags=c.hashtags,
            emphasis_words=c.emphasis_words,
            reason=c.reason,
            scores=c.scores,
            layout=DEFAULT_LAYOUT,
            caption_template=processing.caption_template,
            caption_style=CaptionStyle(**processing.caption_colors.model_dump()),
            cut_ranges=cut_ranges,
            auto_cut=processing.auto_cut,
            auto_zoom=processing.auto_zoom,
            zoom_keyframes=zoom_keyframes,
            auto_color=processing.auto_color,
            show_captions=processing.captions,
            result_set=result_set,
        )
        for c, cut_ranges, zoom_keyframes in zip(candidates, cuts, zooms, strict=True)
    ]
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()
        return [row.id for row in rows if row.id is not None]


def render_clip_row(engine: Engine, clip_id: int, work: Path) -> Clip:
    """Render clip clip_id from work, the work directory of its project's
    process job, and return the clip.

    The clip is cut from work's source.mp4, from the start to the end of its
    segments (Clip.start, Clip.end) without its cut_ranges and the gaps
    between its segments, which play in their order, framed in
    its layout with its crop plan as the editor set it (framing.framed_plan),
    scene by scene if it has scenes (scene_framing.scene_parts),
    captioned and normalized to the target_lufs of the settings
    (render_clip). Its captions are written first
    (write_captions, from work's transcript.json), so that each render shows
    the clip's current words, template and hook, and its censored words
    are beeped or muted (censor_audio.clip_censor_filter), the layers
    of its timeline and its viral hook are drawn and mixed in
    (timeline.clip_layers, with the hook's punch-in: timeline.hook_punch)
    and its cuts get its transitions (pipeline/transitions) and its speech
    is enhanced as its enhance says (pipeline/enhance.enhanced_voice). Its
    status is rendering
    while ffmpeg runs, then rendered with output_path
    {data_dir}/output/{project_id}/{clip_id}.mp4, or failed with no
    output_path (the reason is logged) if ffmpeg or the checks of the
    rendered file fail. A rendered clip's SRT subtitles and metadata JSON
    (pipeline/export, from work's transcript.json and meta.json) are then
    written next to its video; a failed clip has none. Raises StepError if
    the clip, its crop plan or the transcript does not exist, and ValueError
    if its caption template does not; the clip is then left as it was.
    Raises StepError if work's meta.json is missing after a render.
    """
    settings = config.settings
    with Session(engine) as session:
        clip = get_clip_row(session, clip_id)
        job = prepare_render(session, clip.to_model(), work)
        output = clip_output(clip.project_id, clip_id)
        for stale in (srt_path(output), metadata_path(output)):
            stale.unlink(missing_ok=True)
        clip.status, clip.output_path = "rendering", None
        session.add(clip)
        session.commit()

    status: ClipStatus = "rendered"
    try:
        run_render(job, work, output)
    except (RenderError, FFmpegError, DeepFilterError) as exc:
        logger.warning("clip %d failed to render: %s", clip_id, exc)
        status = "failed"

    with Session(engine) as session:
        clip = get_clip_row(session, clip_id)
        clip.status = status
        clip.output_path = str(output) if status == "rendered" else None
        session.add(clip)
        session.commit()
        session.refresh(clip)
        rendered = clip.to_model()
    if status == "rendered":
        write_srt(work, rendered, settings.render.fps)
        write_metadata(work, rendered, settings.credit_template)
        webhook_events.clip_rendered(engine, clip_id)
    else:
        notifications.render_failed(engine, clip_id)
    return rendered


def export_project(engine: Engine, project_id: int, work: Path) -> Path:
    """Write the zip of project project_id's rendered clips and return its
    path, {data_dir}/output/{project_id}/clips.zip (ZIP_NAME).

    For each rendered clip whose video exists, best overall score first, the
    zip holds its video, SRT subtitles and metadata JSON (pipeline/export),
    each named by the clip's id. The metadata is written again first, so it
    has the clip's current text and the current credit_template; subtitles
    belong to the rendered video, so they are only written (from work, the
    work directory of the clips' process job) if they are missing. Raises
    StepError if the project does not exist or a file that it reads in work
    is missing.
    """
    settings = config.settings
    files: list[Path] = []
    for clip in _best_first(engine, project_id, "rendered"):
        video = Path(clip.output_path) if clip.output_path else None
        if video is None or not video.is_file():
            logger.warning("clip %d has no rendered video; not zipped", clip.id)
            continue
        if not srt_path(video).is_file():
            write_srt(work, clip, settings.render.fps)
        metadata = write_metadata(work, clip, settings.credit_template)
        files += [video, srt_path(video), metadata]
    path = write_zip(project_output(project_id) / ZIP_NAME, files)
    logger.info(
        "zipped %d clips of project %d to %s", len(files) // 3, project_id, path
    )
    return path


def export_premiere(engine: Engine, project_id: int, work: Path) -> Path:
    """Write the Premiere XML of project project_id's clips and return its
    path, {data_dir}/output/{project_id}/premiere.xml (PREMIERE_NAME).

    The XML (pipeline/premiere) has a sequence for each clip of the project,
    whatever its status, best overall score first, that plays the clip's
    part of the source video in work, the work directory of the clips'
    process job. Raises StepError if the project does not exist, meta.json
    or source.mp4 in work is missing, or source.mp4 has no audio
    (premiere.read_source), and FFmpegError if ffprobe cannot read it.
    """
    clips = _best_first(engine, project_id)
    path = project_output(project_id) / PREMIERE_NAME
    write_premiere_xml(path, clips, work)
    logger.info(
        "wrote Premiere XML of %d clips of project %d to %s",
        len(clips),
        project_id,
        path,
    )
    return path


def _best_first(
    engine: Engine, project_id: int, status: ClipStatus | None = None
) -> list[Clip]:
    """Return the clips of the current result set of project project_id, only
    those with status if it is set, best overall score first (then by id).

    Raises StepError if the project does not exist.
    """
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        if project is None:
            raise StepError(f"project {project_id} not found")
        query = select(ClipRow).where(
            ClipRow.project_id == project_id, ClipRow.result_set == project.result_set
        )
        if status is not None:
            query = query.where(ClipRow.status == status)
        clips = [row.to_model() for row in session.exec(query).all()]
    return sorted(clips, key=lambda clip: (-clip.scores.overall, clip.id))


def get_clip_row(session: Session, clip_id: int) -> ClipRow:
    """Return the row of clip clip_id; raises StepError if there is none."""
    clip = session.get(ClipRow, clip_id)
    if clip is None:
        raise StepError(f"clip {clip_id} not found")
    return clip
