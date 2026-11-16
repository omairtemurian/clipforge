"""The timeline endpoints (SPEC-v2 3.5): replace a clip's tracks (PUT
/clips/{id}/tracks) or some of them (PATCH /clips/{id}/tracks).

The tracks are checked first (timeline.track_problems: kinds, times inside
the rendered clip, assets, props) and stored with their props' defaults
filled in. The video track follows the clip's segments (moved with
PATCH /clips/{id} start and end), so these endpoints keep it as it is. The
rendered video is not changed: render the clip again to apply the tracks.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.api.deps import clip_row, get_engine
from clipforge.api.errors import ApiError
from clipforge.db import ClipRow
from clipforge.fonts import available_fonts
from clipforge.models import Clip, Timeline, TimelinePatch
from clipforge.timeline import (
    clip_length,
    tidy_props,
    timeline_assets,
    track_problems,
)

router = APIRouter()

TracksEdit = Callable[[Clip], Timeline]


@router.put("/clips/{clip_id}/tracks")
def put_tracks(
    clip_id: int, body: Timeline, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Replace the clip's tracks with body and return the clip. body's
    video track must be the clip's (as GET /clips/{id} returns it) or
    empty, which keeps it.

    404 if the clip does not exist; 422 if a track is not valid
    (timeline.track_problems) or the video track differs; 409 while the
    clip renders.
    """

    def replace(clip: Clip) -> Timeline:
        """Return body, with the clip's video track if body has none."""
        if body.video:
            return body
        return body.model_copy(update={"video": clip.tracks.video})

    return _save_tracks(engine, clip_id, replace)


@router.patch("/clips/{clip_id}/tracks")
def patch_tracks(
    clip_id: int, body: TimelinePatch, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Replace the tracks that body sets (not null) and return the clip;
    the other tracks are kept. Errors as for PUT."""
    changes = {
        name: getattr(body, name)
        for name in TimelinePatch.model_fields
        if getattr(body, name) is not None
    }
    return _save_tracks(
        engine, clip_id, lambda clip: clip.tracks.model_copy(update=changes)
    )


def _save_tracks(engine: Engine, clip_id: int, edit: TracksEdit) -> Clip:
    """Store edit's tracks for clip clip_id, once checked, and return the
    clip (errors: see the routes)."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        clip = row.to_model()
        tracks = edit(clip)
        if tracks.video != clip.tracks.video:
            raise ApiError(
                422,
                "validation_error",
                "the video track follows the clip's segments: send it as it is "
                "(or empty) and move the clip with PATCH /clips/{id}",
            )
        return store_tracks(session, row, tracks)


def store_tracks(session: Session, row: ClipRow, tracks: Timeline) -> Clip:
    """Give row's clip tracks, once checked (timeline.track_problems; 422 if
    they are not valid), with their props' defaults filled in, and return
    the clip."""
    clip = row.to_model()
    length = clip_length(clip, config.settings.render.fps)
    assets = timeline_assets(session, tracks)
    problems = track_problems(tracks, length, assets, available_fonts())
    if problems:
        raise ApiError(422, "validation_error", "; ".join(problems))
    row.tracks = tidy_props(tracks)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.to_model()
