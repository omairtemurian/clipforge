"""Clip endpoints (SPEC 7): list a project's clips, get, edit, re-word, delete
one, the transcript, filmstrip and waveform around one.

The files of a clip (render, preview, downloads) are in api/clip_files.py,
its suggested cuts (cleanup, auto cut) in api/clip_cuts.py.
"""

import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import Engine
from sqlmodel import Session, select

from clipforge import usage
from clipforge.api.deps import clip_row, get_engine, get_llm, project_row, work_dir
from clipforge.api.errors import ApiError
from clipforge.clip_edit import ClipEditError, apply_patch
from clipforge.clip_text import ClipTextError, regenerate_text
from clipforge.clip_transcript import CONTEXT_S, clip_transcript, context_window
from clipforge.db import ClipRow
from clipforge.ffmpeg import FFmpegError
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import Clip, ClipPatch, Transcript, Word
from clipforge.pipeline import preview_assets
from clipforge.pipeline.export import metadata_path, srt_path
from clipforge.pipeline.preview_assets import Waveform
from clipforge.pipeline.step import SOURCE, TRANSCRIPT, StepError, load_json
from clipforge.preview import previews_dir

logger = logging.getLogger(__name__)

router = APIRouter()

ClipSort = Literal["score", "duration"]


@router.get("/projects/{project_id}/clips")
def list_clips(
    project_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    sort: ClipSort = "score",
    min_score: Annotated[int | None, Query(ge=0, le=99)] = None,
    q: str | None = None,
    result_set: Annotated[int | None, Query(ge=1)] = None,
) -> list[Clip]:
    """Return the clips of a project's current result set, or of result_set
    (the project's result sets are 1..Project.result_set; a reprompt makes
    the next one and keeps the earlier ones).

    sort=score puts the best overall score first, sort=duration the shortest
    clip (end - start) first; ties go by id. min_score keeps the clips whose
    overall score is at least min_score, and q those whose title, hook text,
    description or a hashtag contains q (ignoring case).
    """
    with Session(engine) as session:
        wanted = project_row(session, project_id).result_set
        if result_set is not None:
            wanted = result_set
        rows = session.exec(
            select(ClipRow).where(
                ClipRow.project_id == project_id, ClipRow.result_set == wanted
            )
        )
        clips = [row.to_model() for row in rows]
    if min_score is not None:
        clips = [clip for clip in clips if clip.scores.overall >= min_score]
    needle = (q or "").strip().casefold()
    if needle:
        clips = [clip for clip in clips if needle in _searchable(clip)]
    if sort == "duration":
        return sorted(clips, key=lambda clip: (clip.end - clip.start, clip.id))
    return sorted(clips, key=lambda clip: (-clip.scores.overall, clip.id))


@router.get("/clips/{clip_id}")
def get_clip(clip_id: int, engine: Annotated[Engine, Depends(get_engine)]) -> Clip:
    """Return one clip."""
    with Session(engine) as session:
        return clip_row(session, clip_id).to_model()


@router.get("/clips/{clip_id}/transcript")
def get_clip_transcript(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    context: Annotated[float, Query(ge=0, le=300)] = CONTEXT_S,
) -> list[Word]:
    """Return the words of the saved clip with context seconds of the source
    before and after it, in seconds of the source (clip_transcript: caption
    words, so a word's text is what captions show).

    Answers 409 if the project's transcript is missing.
    """
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        duration = project_row(session, clip.project_id).duration
        work = work_dir(session, clip.project_id)
    try:
        transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return clip_transcript(transcript, clip, duration, context)


@router.get("/clips/{clip_id}/filmstrip")
def get_clip_filmstrip(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve a JPEG row of source frames over the saved clip with 30 s
    around it (clip_transcript.context_window; preview_assets.filmstrip),
    made on the first request for each span and cached.

    Headers X-Filmstrip-Start and X-Filmstrip-Interval give the source
    time of the first tile and the seconds between tiles, X-Filmstrip-Count
    the number of tiles. 409 if the project has no processed source; 500 if
    ffmpeg fails.
    """
    clip, source, start, end = _clip_source(engine, clip_id)
    try:
        strip = preview_assets.filmstrip(
            source, previews_dir(clip.project_id), str(clip_id), start, end
        )
    except FFmpegError as exc:
        logger.warning("the filmstrip of clip %d failed: %s", clip_id, exc)
        raise ApiError(
            500, "render_failed", f"the filmstrip of clip {clip_id} failed"
        ) from exc
    headers = {
        "X-Filmstrip-Start": f"{strip.start:.3f}",
        "X-Filmstrip-Interval": f"{strip.interval:.6f}",
        "X-Filmstrip-Count": str(strip.count),
    }
    return FileResponse(strip.path, media_type="image/jpeg", headers=headers)


@router.get("/clips/{clip_id}/waveform")
def get_clip_waveform(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Waveform:
    """Return the audio peaks of the source over the saved clip with 30 s
    around it (preview_assets.waveform), made on the first request for each
    span and cached. 409 if the project has no processed source; 500 if
    ffmpeg fails."""
    clip, source, start, end = _clip_source(engine, clip_id)
    try:
        return preview_assets.waveform(
            source, previews_dir(clip.project_id), str(clip_id), start, end
        )
    except FFmpegError as exc:
        logger.warning("the waveform of clip %d failed: %s", clip_id, exc)
        raise ApiError(
            500, "render_failed", f"the waveform of clip {clip_id} failed"
        ) from exc


@router.patch("/clips/{clip_id}")
def patch_clip(
    clip_id: int, body: ClipPatch, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Change the fields of a clip that body sets and return the clip.

    The edited clip must be valid (clip_edit.edit_problems: start < end
    within the video, cut ranges inside the clip, a known caption
    template), else nothing changes and the answer is 422. Refused with 409
    while the clip renders. The rendered video is not changed: render the
    clip again (POST /clips/{id}/render) to apply the edit.
    """
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        duration = project_row(session, row.project_id).duration
        try:
            apply_patch(session, row, body, duration)
        except ClipEditError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return row.to_model()


@router.delete("/clips/{clip_id}", status_code=204)
def delete_clip(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Delete a clip with its jobs and its rendered video, SRT, metadata and
    previews. Refused with 409 while the clip renders."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        project_id = row.project_id
        video = Path(row.output_path) if row.output_path else None
        session.delete(row)
        session.commit()
    if video is not None:
        for path in (video, srt_path(video), metadata_path(video)):
            path.unlink(missing_ok=True)
    for preview in previews_dir(project_id).glob(f"{clip_id}-*"):
        preview.unlink(missing_ok=True)
    return Response(status_code=204)


@router.post("/clips/{clip_id}/regenerate-text")
def regenerate_clip_text(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> Clip:
    """Let the LLM rewrite the clip's title, description and hashtags from
    its words (clip_text.regenerate_text), save them and return the clip.

    Answers 502 if the LLM cannot be reached or sends no valid text, and
    409 if the clip's transcript is missing.
    """
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    try:
        with usage.recording(engine, clip.project_id):
            text = regenerate_text(llm, work, clip)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (LLMError, ClipTextError) as exc:
        logger.warning("clip %d: no new text: %s", clip_id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        row.title, row.description = text.title, text.description
        row.hashtags = list(text.hashtags)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def _clip_source(engine: Engine, clip_id: int) -> tuple[Clip, Path, float, float]:
    """Return the clip, the source video of its project's process job and the
    span the editor's timeline shows (the clip with 30 s around it); 404 if
    the clip does not exist, 409 if the source is missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        duration = project_row(session, clip.project_id).duration
        source = work_dir(session, clip.project_id) / SOURCE
    if not source.is_file():
        raise ApiError(409, "conflict", f"{source} is missing; process the project")
    start, end = context_window(clip, duration)
    return clip, source, start, end


def _searchable(clip: Clip) -> str:
    """Return the text of clip that q searches, folded for caseless matching."""
    parts = [clip.title, clip.hook_text, clip.description, *clip.hashtags]
    return "\n".join(parts).casefold()
