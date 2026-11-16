"""Endpoints that the Home settings panel uses before a project exists: what
a video link points to (SPEC 8.2), the speech languages and an SRT or VTT upload.
Its saved default and presets are in api/presets."""

import logging

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from clipforge import config
from clipforge.api.errors import ApiError
from clipforge.languages import WHISPER_LANGUAGES
from clipforge.models import HttpUrl
from clipforge.pipeline import download
from clipforge.pipeline.extractors import UnsupportedSource
from clipforge.pipeline.step import StepError
from clipforge.pipeline.subtitle_import import (
    MAX_SUBTITLE_BYTES,
    SubtitlesError,
    parse_subtitles,
    save_subtitles,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class SourceProbe(BaseModel):
    """The body of POST /sources/probe: the video link to read."""

    url: HttpUrl


class SourceInfo(BaseModel):
    """The title, duration (seconds) and thumbnail of a linked video; each is
    None when the page does not say."""

    url: str
    title: str | None
    duration: float | None
    thumbnail_url: str | None


class SpeechLanguage(BaseModel):
    """A language that Whisper transcribes: its code and English name."""

    code: str
    name: str


class SubtitlesUpload(BaseModel):
    """The reply of POST /subtitles: the token that
    ProcessingSettings.subtitles_id takes, and the file's cue count."""

    subtitles_id: str
    cues: int


@router.get("/speech-languages")
def list_speech_languages() -> list[SpeechLanguage]:
    """Return the languages of the speech language select, by name."""
    languages = [SpeechLanguage(code=c, name=n) for c, n in WHISPER_LANGUAGES.items()]
    return sorted(languages, key=lambda language: language.name)


@router.post("/subtitles", status_code=201)
def upload_subtitles(file: UploadFile) -> SubtitlesUpload:
    """Save an SRT or VTT file for a project to use instead of Whisper
    (pipeline/subtitle_import); 422 invalid_subtitles, naming the line of the
    first fault, if it is not UTF-8 SRT or VTT with cues or is larger than
    MAX_SUBTITLE_BYTES."""
    data = file.file.read(MAX_SUBTITLE_BYTES + 1)
    try:
        token = save_subtitles(data, config.settings)
        cues = parse_subtitles(data.decode("utf-8-sig"))
    except SubtitlesError as exc:
        raise ApiError(422, "invalid_subtitles", str(exc)) from exc
    return SubtitlesUpload(subtitles_id=token, cues=len(cues))


@router.post("/sources/probe")
def probe_source(body: SourceProbe) -> SourceInfo:
    """Read the linked video's page with yt-dlp, without downloading it.

    422 unsupported_source if no yt-dlp extractor handles the site; 422
    probe_failed if the link is a playlist or the page cannot be read.
    """
    try:
        info = download.probe(body.url)
    except UnsupportedSource as exc:
        raise ApiError(422, "unsupported_source", str(exc)) from exc
    except StepError as exc:
        logger.info("probe of %s failed: %s", body.url, exc)
        raise ApiError(422, "probe_failed", str(exc)) from exc
    return SourceInfo(
        url=body.url,
        title=info.title,
        duration=info.duration,
        thumbnail_url=info.thumbnail_url,
    )
