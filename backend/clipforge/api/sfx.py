"""Sound effect endpoints (SPEC-v2 3.5): the bundled CC0 pack (assets/sfx,
pipeline/sfx), and an AI pass that places its sounds on a clip.

GET /sfx lists the pack, only the sounds with the tag if given, and
GET /sfx/{id}/file serves a sound to listen to. POST /clips/{id}/auto-sfx
asks the LLM for the moments of the saved clip that a sound fits (cuts and
punchlines or key words), searches the pack for each by tag and puts the
sounds on the clip's sfx track, replacing those that an earlier run put
there (the owner's own items stay). The rendered video is not changed:
render the clip again.

Errors of auto-sfx: 404 if the clip does not exist; 409 if the project's
transcript is missing or while the clip renders; 422 for a body that is not
valid or sounds that do not fit the clip; 502 if the LLM cannot be reached
or sends no valid sounds.
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import assets, config, usage
from clipforge.api.deps import clip_row, get_engine, get_llm, work_dir
from clipforge.api.errors import ApiError
from clipforge.fonts import available_fonts
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import Asset, AutoSfxOptions, Clip, SfxSound, Transcript
from clipforge.pipeline.polish import spoken_words
from clipforge.pipeline.sfx import (
    Placement,
    SfxError,
    bundled_sfx,
    clip_joins,
    clip_moments,
    find_sfx,
    merge_sfx,
    place_sfx,
    sfx_items,
)
from clipforge.pipeline.step import TRANSCRIPT, StepError, load_json
from clipforge.timeline import (
    clip_length,
    tidy_props,
    timeline_assets,
    track_problems,
)

logger = logging.getLogger(__name__)

router = APIRouter()
BUNDLED_MIME = {".flac": "audio/flac"}


@router.get("/sfx")
def list_sfx(
    engine: Annotated[Engine, Depends(get_engine)], tag: str | None = None
) -> list[SfxSound]:
    """Return the sound effects of the bundled pack in id order, only those
    with tag (not case sensitive) if given; a sound whose file is gone is
    left out."""
    with Session(engine) as session:
        found = assets.list_assets(session, kind="sfx")
    sounds = [sound for asset in found if (sound := sfx_sound(asset)) is not None]
    if tag is None:
        return sounds
    return [sound for sound in sounds if tag.strip().lower() in sound.tags]


@router.get("/sfx/{asset_id}/file")
def get_sfx_file(
    asset_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve a sound effect's file (with HTTP Range, so it can be played).
    404 if there is no such sound or its file is gone."""
    with Session(engine) as session:
        asset = assets.get_asset(session, asset_id)
    if asset is None or asset.kind != "sfx" or sfx_sound(asset) is None:
        raise ApiError(404, "not_found", f"sound effect {asset_id} not found")
    mime = BUNDLED_MIME.get(Path(asset.path).suffix, "application/octet-stream")
    return FileResponse(asset.path, media_type=mime)


@router.post("/clips/{clip_id}/auto-sfx")
def auto_sfx(
    clip_id: int,
    body: AutoSfxOptions,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> Clip:
    """Place sound effects on the saved clip's sfx track
    (pipeline/sfx.find_sfx, place_sfx) and return the clip."""
    fps = config.settings.render.fps
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        clip = row.to_model()
        work = work_dir(session, clip.project_id)
    try:
        transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    moments = clip_moments(spoken_words(transcript, clip, fps), clip_joins(clip, fps))
    try:
        with usage.recording(engine, clip.project_id):
            picks = find_sfx(llm, moments, body.max_items, clip.id)
    except (LLMError, SfxError) as exc:
        logger.warning("clip %d: no sound effects from the LLM: %s", clip.id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc
    placements = place_sfx(picks, moments, clip_length(clip, fps))
    return _save_sfx(engine, clip_id, placements)


def _save_sfx(engine: Engine, clip_id: int, placements: list[Placement]) -> Clip:
    """Put placements on clip clip_id's sfx track and return the clip."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        clip = row.to_model()
        items = sfx_items(placements, assets.bundled_sfx_ids(session))
        tracks = clip.tracks.model_copy(
            update={"sfx": merge_sfx(clip.tracks.sfx, items)}
        )
        length = clip_length(clip, config.settings.render.fps)
        problems = track_problems(
            tracks, length, timeline_assets(session, tracks), available_fonts()
        )
        if problems:
            raise ApiError(422, "validation_error", "; ".join(problems))
        row.tracks = tidy_props(tracks)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def sfx_sound(asset: Asset) -> SfxSound | None:
    """Return the library entry of the sound effect asset, or None if its
    file is gone: a bundled sound has its catalogue title, tags and length."""
    path = Path(asset.path)
    if not path.is_file():
        return None
    bundled = bundled_sfx(path) if assets.BUNDLED_TAG in asset.tags else None
    if bundled is not None:
        return SfxSound(
            asset=asset,
            title=bundled.title,
            duration=bundled.seconds,
            tags=list(bundled.tags),
        )
    return SfxSound(asset=asset, title=path.name, duration=None, tags=list(asset.tags))
