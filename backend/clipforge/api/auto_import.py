"""Auto Import endpoints (SPEC-v2 3.1): the watched YouTube channels, with the
defaults of the projects that their new videos become, and the videos seen
in their feeds. The AutoImporter (clipforge.watch.youtube_watcher) does the
importing.
"""

from collections.abc import Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Response
from sqlalchemy import Engine

from clipforge import auto_import, config
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.models import (
    WatchedChannel,
    WatchedChannelCreate,
    WatchedChannelPatch,
    WatchedVideo,
)
from clipforge.watch import youtube_handles

router = APIRouter(prefix="/auto-import")

T = TypeVar("T")


@router.get("/channels")
def list_channels(
    engine: Annotated[Engine, Depends(get_engine)],
) -> list[WatchedChannel]:
    """Return the watched channels, oldest first."""
    return auto_import.list_channels(engine)


@router.post("/channels", status_code=201)
def add_channel(
    body: WatchedChannelCreate, engine: Annotated[Engine, Depends(get_engine)]
) -> WatchedChannel:
    """Watch a channel (an id, an @handle or a youtube.com link) with the
    given defaults; 409 conflict if it is already watched. A handle is
    looked up with the YouTube Data API: 412 needs_credentials without
    YOUTUBE_API_KEY, 422 if no channel has it, 502 if the lookup failed.
    Its feed is first read by the next poll, and the videos already in it
    are not imported."""
    if body.channel.startswith("@"):
        body = body.model_copy(update={"channel": _resolve(body.channel)})
    try:
        return auto_import.add_channel(engine, body)
    except auto_import.ChannelExists as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.get("/channels/{channel_id}")
def get_channel(
    channel_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> WatchedChannel:
    """Return one watched channel."""
    return _found(lambda: auto_import.get_channel(engine, channel_id), channel_id)


@router.patch("/channels/{channel_id}")
def patch_channel(
    channel_id: int,
    body: WatchedChannelPatch,
    engine: Annotated[Engine, Depends(get_engine)],
) -> WatchedChannel:
    """Change the defaults, source rights, credit line or enabled flag of a
    channel (the fields sent); they apply to the videos imported from now on."""
    return _found(
        lambda: auto_import.update_channel(engine, channel_id, body), channel_id
    )


@router.delete("/channels/{channel_id}", status_code=204)
def delete_channel(
    channel_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Stop watching a channel; the projects made from its videos stay."""
    _found(lambda: auto_import.remove_channel(engine, channel_id), channel_id)
    return Response(status_code=204)


@router.get("/channels/{channel_id}/videos")
def list_channel_videos(
    channel_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> list[WatchedVideo]:
    """Return the videos seen in a channel's feed, newest first, each with the
    project made for it (none for the videos that were there when the channel
    was added)."""
    _found(lambda: auto_import.get_channel(engine, channel_id), channel_id)
    return auto_import.channel_videos(engine, channel_id)


def _resolve(handle: str) -> str:
    """Return the channel id of a handle; the lookup errors as ApiErrors."""
    try:
        return youtube_handles.resolve_handle(handle, config.settings.youtube_api_key)
    except youtube_handles.NeedsApiKey as exc:
        raise ApiError(412, "needs_credentials", str(exc)) from exc
    except youtube_handles.HandleNotFound as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    except youtube_handles.HandleError as exc:
        raise ApiError(502, "youtube_error", str(exc)) from exc


def _found(action: Callable[[], T], channel_id: int) -> T:
    """Run action; turn ChannelNotFound into the 404 ApiError."""
    try:
        return action()
    except auto_import.ChannelNotFound as exc:
        raise not_found("watched channel", channel_id) from exc
