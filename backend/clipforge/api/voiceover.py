"""AI voiceover endpoints (SPEC-v2 3.5): the voices of the local TTS engines
(engines/tts) and the voiceover items of a clip (pipeline/voiceover).

GET /voices lists the voices of the installed engines (Kokoro, Piper).
POST /clips/{id}/voiceover speaks a text with a voice and puts it on the
clip's voiceover track from start; PATCH /clips/{id}/voiceover/{item_id}
moves it, changes its volume or ducking, or speaks it again with new text,
voice or speed; DELETE removes it. While a voiceover item with duck plays,
the render lowers the clip's own sound under it. Each answers the clip and
stores a version (undo); the rendered video is not changed: render the clip
again to apply it.

Errors: 404 if the clip or item does not exist; 409 while the clip renders
or if the voice's engine is not installed (engine_not_installed); 422 for an
unknown voice, a voiceover that does not fit the clip or a recording given a
voice or speed without text; 502 if the engine fails (engine_error).
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import assets, config, usage
from clipforge.api.deps import clip_row, get_engine
from clipforge.api.errors import ApiError
from clipforge.db import ClipRow
from clipforge.engines.tts import (
    TtsError,
    TtsNotInstalled,
    UnknownVoice,
    find_voice,
    installed_voices,
)
from clipforge.fonts import available_fonts
from clipforge.models import (
    Clip,
    TrackItem,
    TtsVoice,
    VoiceoverCreate,
    VoiceoverPatch,
    VoiceoverProps,
)
from clipforge.pipeline.voiceover import (
    VOICEOVER_TAG,
    Spoken,
    fit_problem,
    next_item_id,
    speak,
    voiceover_item,
)
from clipforge.timeline import clip_length, tidy_props, timeline_assets, track_problems

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/voices")
def list_voices() -> list[TtsVoice]:
    """Return the voices of the installed TTS engines (none if neither is)."""
    return installed_voices()


@router.post("/clips/{clip_id}/voiceover")
def add_voiceover(
    clip_id: int,
    body: VoiceoverCreate,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Speak body.text with body.voice and put it on clip clip_id's
    voiceover track from body.start; return the clip."""
    project_id = _editable(engine, clip_id).project_id
    spoken = _speak(engine, project_id, body.text, body.voice, body.speed)
    props = VoiceoverProps(
        volume=body.volume,
        text=body.text,
        voice=body.voice,
        speed=body.speed,
        duck=body.duck,
    )
    with Session(engine) as session:
        row = _editable_row(session, clip_id)
        clip = row.to_model()
        _check_fit(clip, body.start, spoken.seconds)
        asset_id = _asset_id(session, spoken, body.voice)
        item = voiceover_item(
            next_item_id(clip.tracks), asset_id, body.start, spoken.seconds, props
        )
        return _save(session, row, [*clip.tracks.voiceover, item])


@router.patch("/clips/{clip_id}/voiceover/{item_id}")
def edit_voiceover(
    clip_id: int,
    item_id: str,
    body: VoiceoverPatch,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Change voiceover item item_id of clip clip_id (unset fields are
    kept), speaking it again if its text, voice or speed changes; return the
    clip."""
    clip = _editable(engine, clip_id)
    old = _item(clip, item_id)
    before = VoiceoverProps.model_validate(old.props)
    changes = body.model_dump(exclude_none=True, exclude={"start"})
    props = before.model_copy(update=changes)
    spoken = None
    if any(getattr(props, k) != getattr(before, k) for k in ("text", "voice", "speed")):
        if props.text is None or props.voice is None:
            raise ApiError(
                422,
                "validation_error",
                f"{item_id} is a recording; give text and voice to speak it",
            )
        spoken = _speak(engine, clip.project_id, props.text, props.voice, props.speed)
    start = old.start if body.start is None else body.start
    with Session(engine) as session:
        row = _editable_row(session, clip_id)
        clip = row.to_model()
        old = _item(clip, item_id)
        seconds = old.end - old.start if spoken is None else spoken.seconds
        _check_fit(clip, start, seconds)
        asset_id = old.asset_id
        if spoken is not None and props.voice is not None:
            asset_id = _asset_id(session, spoken, props.voice)
        if asset_id is None:
            raise ApiError(422, "validation_error", f"{item_id} plays no asset")
        item = voiceover_item(item_id, asset_id, start, seconds, props)
        items = [item if i.id == item_id else i for i in clip.tracks.voiceover]
        return _save(session, row, items)


@router.delete("/clips/{clip_id}/voiceover/{item_id}")
def remove_voiceover(
    clip_id: int, item_id: str, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Remove voiceover item item_id from clip clip_id; return the clip."""
    with Session(engine) as session:
        row = _editable_row(session, clip_id)
        clip = row.to_model()
        _item(clip, item_id)
        items = [i for i in clip.tracks.voiceover if i.id != item_id]
        return _save(session, row, items)


def _editable(engine: Engine, clip_id: int) -> Clip:
    """Return clip clip_id: 404 if it does not exist, 409 while it renders."""
    with Session(engine) as session:
        return _editable_row(session, clip_id).to_model()


def _editable_row(session: Session, clip_id: int) -> ClipRow:
    """Return clip clip_id's row: 404 if there is none, 409 while it renders."""
    row = clip_row(session, clip_id)
    if row.status == "rendering":
        raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
    return row


def _item(clip: Clip, item_id: str) -> TrackItem:
    """Return the clip's voiceover item item_id (404 if it has none)."""
    found = next((i for i in clip.tracks.voiceover if i.id == item_id), None)
    if found is None:
        raise ApiError(404, "not_found", f"clip {clip.id} has no voiceover {item_id}")
    return found


def _speak(
    engine: Engine, project_id: int, text: str, voice: str, speed: float
) -> Spoken:
    """Speak text with voice at speed (pipeline/voiceover.speak), recording
    the seconds it took as compute for the project; the engine's errors
    become API errors."""
    began = time.monotonic()
    try:
        spoken = speak(text, voice, speed)
    except TtsNotInstalled as exc:
        raise ApiError(409, "engine_not_installed", str(exc)) from exc
    except UnknownVoice as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    except TtsError as exc:
        logger.warning("voiceover with %s failed: %s", voice, exc)
        raise ApiError(502, "engine_error", str(exc)) from exc
    usage.record(engine, usage.COMPUTE, time.monotonic() - began, project_id=project_id)
    return spoken


def _check_fit(clip: Clip, start: float, seconds: float) -> None:
    """422 if a voiceover of seconds from start does not fit the clip."""
    problem = fit_problem(start, seconds, clip_length(clip, config.settings.render.fps))
    if problem is not None:
        raise ApiError(422, "validation_error", problem)


def _asset_id(session: Session, spoken: Spoken, voice_id: str) -> int:
    """Return the id of the voiceover asset of spoken's file, adding it
    (with the voice's license) if there is none yet."""
    path = str(spoken.path)
    found = assets.list_assets(session, kind="audio", tag=VOICEOVER_TAG)
    existing = next((asset for asset in found if asset.path == path), None)
    if existing is not None:
        return existing.id
    voice = find_voice(voice_id)
    return assets.add_asset(
        session,
        "audio",
        path,
        license=voice.license,
        attribution=f"AI voiceover: {voice.name}, {voice.engine.title()} ({voice.id})",
        tags=[VOICEOVER_TAG],
    ).id


def _save(session: Session, row: ClipRow, items: list[TrackItem]) -> Clip:
    """Give row's clip the voiceover track items and return the clip; 422
    if its tracks are then not valid."""
    clip = row.to_model()
    tracks = clip.tracks.model_copy(update={"voiceover": items})
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
