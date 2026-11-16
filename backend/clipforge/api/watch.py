"""Watchlist endpoints (T28c): the watch's setup, its alerts (new uploads
and go-lives) and the watched Twitch streamers. The YouTube channels are
the Auto Import endpoints (api/auto_import.py); the push callbacks are in
api/watch_callbacks.py.
"""

from collections.abc import Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Engine

from clipforge import config
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.models import (
    WatchedStreamer,
    WatchedStreamerCreate,
    WatchedStreamerPatch,
    WatchEvent,
    WatchStatus,
)
from clipforge.watch import events, streamers

router = APIRouter(prefix="/watch")

T = TypeVar("T")


@router.get("/status")
def get_status() -> WatchStatus:
    """Return whether pushes are available, the poll interval and which
    keys the watch has."""
    settings = config.settings
    return WatchStatus(
        push_available=bool(settings.public_callback_url),
        poll_interval_s=settings.auto_import_poll_s,
        twitch_configured=bool(
            settings.twitch_client_id and settings.twitch_client_secret
        ),
        handles_supported=bool(settings.youtube_api_key),
    )


@router.get("/events")
def list_events(
    engine: Annotated[Engine, Depends(get_engine)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = events.EVENTS_LIMIT,
) -> list[WatchEvent]:
    """Return the latest alerts, newest first; after: only those with a
    higher id (what the app polls for new alerts)."""
    return events.list_events(engine, after=after, limit=limit)


@router.get("/streamers")
def list_streamers(
    engine: Annotated[Engine, Depends(get_engine)],
) -> list[WatchedStreamer]:
    """Return the watched Twitch streamers, oldest first."""
    return streamers.list_streamers(engine)


@router.post("/streamers", status_code=201)
def add_streamer(
    body: WatchedStreamerCreate, engine: Annotated[Engine, Depends(get_engine)]
) -> WatchedStreamer:
    """Watch a Twitch login or twitch.tv link; 409 if already watched."""
    try:
        return streamers.add_streamer(engine, body)
    except streamers.StreamerExists as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.patch("/streamers/{streamer_id}")
def patch_streamer(
    streamer_id: int,
    body: WatchedStreamerPatch,
    engine: Annotated[Engine, Depends(get_engine)],
) -> WatchedStreamer:
    """Turn a streamer's watch on or off."""
    return _found(
        lambda: streamers.update_streamer(engine, streamer_id, body), streamer_id
    )


@router.delete("/streamers/{streamer_id}", status_code=204)
def delete_streamer(
    streamer_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Stop watching a streamer; its alerts stay."""
    _found(lambda: streamers.remove_streamer(engine, streamer_id), streamer_id)
    return Response(status_code=204)


def _found(action: Callable[[], T], streamer_id: int) -> T:
    try:
        return action()
    except streamers.StreamerNotFound as exc:
        raise not_found("watched streamer", streamer_id) from exc
