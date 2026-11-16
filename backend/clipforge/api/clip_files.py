"""Clip file endpoints (SPEC 7): render a clip, its preview, and downloads of
a clip's video and subtitles and of a project's zip and Premiere XML."""

import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import config
from clipforge.api.deps import (
    clip_row,
    get_engine,
    project_row,
    require_usage_budget,
    wake_worker,
    work_dir,
)
from clipforge.api.errors import ApiError
from clipforge.clips import export_premiere, export_project
from clipforge.db import ClipRow, JobRow
from clipforge.ffmpeg import FFmpegError
from clipforge.jobs import enqueue_render
from clipforge.models import Clip, Job, Transcript
from clipforge.pipeline.export import srt_path, write_srt
from clipforge.pipeline.render import RenderError
from clipforge.pipeline.step import TRANSCRIPT, StepError, load_json
from clipforge.pipeline.transcript_files import (
    MEDIA_TYPES,
    TranscriptFormat,
    clip_cues,
    format_cues,
    source_cues,
)
from clipforge.preview import render_preview
from clipforge.storage import StorageRefused, require_not_archived
from clipforge.timeline import clip_layers

logger = logging.getLogger(__name__)

router = APIRouter()

# Characters of a title that a download's file name keeps.
SLUG_LENGTH = 60
NOT_SLUG = re.compile(r"[^0-9A-Za-z]+")


@router.post("/clips/{clip_id}/render", status_code=202)
def queue_render(
    clip_id: int, request: Request, engine: Annotated[Engine, Depends(get_engine)]
) -> Job:
    """Queue a render job for the clip and return it.

    A render job of the clip that is still queued is returned instead of a
    new one (it renders the clip as it is when it runs). 409 if the clip's
    project has no process job or is archived, or if a monthly usage cap is
    used up.
    """
    with Session(engine) as session:
        project_id = clip_row(session, clip_id).project_id
        try:
            require_not_archived(session, project_id)
        except StorageRefused as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
        work_dir(session, project_id)
        queued = session.exec(
            select(JobRow)
            .where(JobRow.clip_id == clip_id, JobRow.status == "queued")
            .order_by(col(JobRow.id))
        ).first()
        if queued is not None:
            return queued.to_model()
    require_usage_budget(engine)
    job_id = enqueue_render(engine, clip_id)
    wake_worker(request)
    with Session(engine) as session:
        return session.get_one(JobRow, job_id).to_model()


@router.get("/clips/{clip_id}/preview")
def preview_clip(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the clip's 540p preview (preview.render_preview), rendered on
    the first request after each edit and cached.

    409 if the clip's crop plan, transcript or caption template is missing;
    500 render_failed if ffmpeg fails.
    """
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
        layers = clip_layers(session, clip, config.settings.render.fps)
    try:
        path = render_preview(clip, work, layers)
    except (StepError, ValueError) as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (RenderError, FFmpegError) as exc:
        logger.warning("the preview of clip %d failed: %s", clip_id, exc)
        raise ApiError(
            500, "render_failed", f"the preview of clip {clip_id} failed to render"
        ) from exc
    return FileResponse(path, media_type="video/mp4")


@router.get("/clips/{clip_id}/download")
def download_clip(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the clip's rendered video as a download; 404 if not rendered."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
    return FileResponse(
        _rendered_video(clip),
        media_type="video/mp4",
        filename=download_name(clip, ".mp4"),
    )


@router.get("/clips/{clip_id}/srt")
def clip_srt(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the SRT subtitles of the clip's rendered video (written at render
    time, or now from its process job's transcript if missing); 404 if the
    clip is not rendered."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        path = srt_path(_rendered_video(clip))
        work = work_dir(session, clip.project_id)
    if not path.is_file():
        try:
            write_srt(work, clip, config.settings.render.fps)
        except (StepError, ValueError) as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
    return FileResponse(
        path, media_type="application/x-subrip", filename=download_name(clip, ".srt")
    )


@router.get("/clips/{clip_id}/transcript.{fmt}")
def clip_transcript_file(
    clip_id: int, fmt: TranscriptFormat, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Serve the captions of the clip as text (txt) or subtitles (srt, vtt),
    as its render shows them (transcript_files.clip_cues), whether it is
    rendered or not; 409 if the project's transcript is missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    try:
        transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
        cues = clip_cues(transcript, clip, config.settings.render.fps)
    except (StepError, ValueError) as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return _text_download(format_cues(cues, fmt), fmt, download_name(clip, f".{fmt}"))


@router.get("/projects/{project_id}/transcript")
def source_transcript(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Transcript:
    """Return the transcript of the project's source video (the editor's
    add-section picker lists its segments); 409 if it is missing and 404 if
    there is no such project."""
    with Session(engine) as session:
        project_row(session, project_id)
        work = work_dir(session, project_id)
    try:
        return load_json(work / TRANSCRIPT, Transcript, "transcribe")
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.get("/projects/{project_id}/transcript.{fmt}")
def source_transcript_file(
    project_id: int,
    fmt: TranscriptFormat,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Response:
    """Serve the transcript of the project's source video as text (txt) or
    subtitles (srt, vtt), a cue for each segment; 409 if the project's
    transcript is missing and 404 if there is no such project."""
    with Session(engine) as session:
        project_row(session, project_id)
        work = work_dir(session, project_id)
    try:
        transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    text = format_cues(source_cues(transcript), fmt)
    return _text_download(text, fmt, f"clipforge-{project_id}-transcript.{fmt}")


@router.get("/projects/{project_id}/download.zip")
def download_zip(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the zip of the project's rendered clips (clips.export_project);
    409 if none is rendered."""
    with Session(engine) as session:
        current = project_row(session, project_id).result_set
        work = work_dir(session, project_id)
        rendered = session.exec(
            select(ClipRow.id).where(
                ClipRow.project_id == project_id,
                ClipRow.result_set == current,
                ClipRow.status == "rendered",
            )
        ).first()
    if rendered is None:
        raise ApiError(409, "conflict", f"project {project_id} has no rendered clips")
    try:
        path = export_project(engine, project_id, work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return FileResponse(
        path, media_type="application/zip", filename=f"clipforge-{project_id}.zip"
    )


@router.get("/projects/{project_id}/premiere.xml")
def premiere_xml(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the Premiere Pro XML of the project's clips
    (clips.export_premiere); 409 if it has no clips or its source is not
    ready."""
    with Session(engine) as session:
        current = project_row(session, project_id).result_set
        work = work_dir(session, project_id)
        if (
            session.exec(
                select(ClipRow.id).where(
                    ClipRow.project_id == project_id, ClipRow.result_set == current
                )
            ).first()
            is None
        ):
            raise ApiError(409, "conflict", f"project {project_id} has no clips")
    try:
        path = export_premiere(engine, project_id, work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except FFmpegError as exc:
        logger.warning("Premiere XML of project %d failed: %s", project_id, exc)
        raise ApiError(
            500, "ffmpeg_error", f"ffprobe cannot read project {project_id}'s source"
        ) from exc
    return FileResponse(
        path, media_type="application/xml", filename=f"clipforge-{project_id}.xml"
    )


def download_name(clip: Clip, suffix: str) -> str:
    """Return the file name of a download of clip: "<id>-<title slug><suffix>",
    e.g. "7-pizza-night.mp4" ("7.mp4" for a title without letters)."""
    slug = NOT_SLUG.sub("-", clip.title.lower()).strip("-")[:SLUG_LENGTH].strip("-")
    return f"{clip.id}-{slug}{suffix}" if slug else f"{clip.id}{suffix}"


def _rendered_video(clip: Clip) -> Path:
    """Return the path of clip's rendered video; raises the 404 ApiError if
    the clip is not rendered or its file is gone."""
    video = Path(clip.output_path) if clip.output_path else None
    if clip.status != "rendered" or video is None or not video.is_file():
        raise ApiError(404, "not_found", f"clip {clip.id} has no rendered video")
    return video


def _text_download(text: str, fmt: TranscriptFormat, filename: str) -> Response:
    """Return text as an attachment of the media type of fmt."""
    return Response(
        text.encode(),
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
