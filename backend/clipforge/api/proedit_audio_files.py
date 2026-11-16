"""Pro Edit audio imports (SPEC-v3 5.2-5.4), under /proedit: the Pixabay
"Import file" form (Pixabay's API has no audio) and the owner's own audio
uploads with their rights. Every file is analyzed and tagged (duration is
read by the media library; bpm, key, loudness, energy curve, category, mood
by proedit/audio/tagging) and stored with its license, credit, source URL
and time. The flag proedit.enabled turns them off like the other Pro Edit
endpoints.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError
from clipforge.api.proedit import require_proedit
from clipforge.models import Asset
from clipforge.proedit.audio import pixabay
from clipforge.proedit.audio.library import (
    AudioFileError,
    AudioRights,
    DuplicateAudio,
    store_own_upload,
)

router = APIRouter(prefix="/proedit", dependencies=[Depends(require_proedit)])

Category = Annotated[str | None, Form(min_length=1, max_length=40)]


@router.get("/audio/pixabay")
def get_pixabay_status() -> pixabay.PixabayStatus:
    """Return that Pixabay music and sound effects are imported by hand
    (its API serves no audio) and how."""
    return pixabay.status()


@router.post("/audio/pixabay/import", status_code=201)
def import_pixabay(
    engine: Annotated[Engine, Depends(get_engine)],
    file: UploadFile,
    source_url: Annotated[str, Form(max_length=500)],
    license_confirmed: Annotated[bool, Form()],
    title: Annotated[str, Form(max_length=120)] = "",
    category: Category = None,
) -> Asset:
    """Store a file downloaded from Pixabay (source_url: its /music/ or
    /sound-effects/ page) as music or sfx, analyzed and tagged, with the
    Pixabay Content License and its page as source. 422 if
    license_confirmed is false, the URL is not a Pixabay audio page or the
    file is not usable audio; 409 if the library has the file."""
    with Session(engine) as session:
        try:
            return pixabay.import_pixabay_file(
                session,
                file.file,
                file.filename or "",
                source_url=source_url,
                license_confirmed=license_confirmed,
                title=title,
                category=category,
            )
        except DuplicateAudio as exc:
            raise ApiError(409, "conflict", f"file: {exc}") from exc
        except AudioFileError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc


@router.post("/audio/uploads", status_code=201)
def upload_audio(
    engine: Annotated[Engine, Depends(get_engine)],
    file: UploadFile,
    rights: Annotated[AudioRights, Form()],
    kind: Annotated[Literal["sfx", "music", "audio"], Form()] = "sfx",
    attribution: Annotated[str, Form(max_length=500)] = "",
    category: Category = None,
) -> Asset:
    """Store an audio file of the owner as kind, analyzed and tagged. rights
    (own, permission, cc_by or public_domain) is required: it is the
    license the asset keeps, and cc_by also needs attribution. 422 without
    rights, for a missing credit or an unusable file; 409 if the library
    has the file."""
    with Session(engine) as session:
        try:
            return store_own_upload(
                session,
                file.file,
                file.filename or "",
                rights=rights,
                kind=kind,
                attribution=attribution,
                category=category,
            )
        except DuplicateAudio as exc:
            raise ApiError(409, "conflict", f"file: {exc}") from exc
        except AudioFileError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
