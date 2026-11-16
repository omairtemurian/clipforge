"""Google Drive import endpoints (SPEC-v2 3.1), see clipforge.sources.gdrive:

    GET    /sources/gdrive                -> DriveStatus
    POST   /sources/gdrive/connect        -> DriveConnect (the sign-in URL)
    GET    /sources/gdrive/callback       <- Google's redirect; an HTML page
    DELETE /sources/gdrive/connection     -> 204 (forgets the token)
    POST   /sources/gdrive/file           {file} -> DriveFile
    POST   /sources/gdrive/import         DriveImport -> Project

Every endpoint but the status answers 412 needs_credentials while
GOOGLE_OAUTH_CLIENT_ID is not set.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from clipforge.api.deps import get_engine, require_usage_budget, wake_worker
from clipforge.api.errors import ApiError
from clipforge.api.oauth_pages import result_page
from clipforge.api.projects import project_of_job
from clipforge.jobs import enqueue_process
from clipforge.models import (
    CREDIT_LINE_MAX,
    ProcessingSettings,
    Project,
    SourceRights,
)
from clipforge.oauth import OAuthClient, OAuthError, exchange_code
from clipforge.oauth_flows import pending
from clipforge.sources import gdrive
from clipforge.sources.gdrive import DriveError, DriveFile
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)

router = APIRouter()

CALLBACK_ROUTE = "gdrive_callback"


class DriveStatus(BaseModel):
    """Whether the Google OAuth app is configured and an account connected."""

    configured: bool
    connected: bool


class DriveConnect(BaseModel):
    """The Google sign-in page that connects an account."""

    authorize_url: str


class DriveFileRequest(BaseModel):
    """The body of POST /sources/gdrive/file: a Drive file link or id."""

    file: str = Field(min_length=1, max_length=2048)


class DriveImport(BaseModel):
    """The body of POST /sources/gdrive/import: the Drive file link or id,
    how to process it and its source rights, as in ProjectCreate."""

    file: str = Field(min_length=1, max_length=2048)
    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)


@router.get("/sources/gdrive")
def drive_status() -> DriveStatus:
    """Return whether Drive import can be used."""
    return DriveStatus(
        configured=gdrive.google_client() is not None,
        connected=gdrive.is_connected(),
    )


@router.post("/sources/gdrive/connect")
def connect_drive(request: Request) -> DriveConnect:
    """Start a Google sign-in whose redirect comes back to the callback."""
    client = _client()
    redirect_uri = str(request.url_for(CALLBACK_ROUTE))
    url = pending.start(client, redirect_uri, gdrive.TOKEN_REF)
    return DriveConnect(authorize_url=url)


@router.get(
    "/sources/gdrive/callback", name=CALLBACK_ROUTE, response_class=HTMLResponse
)
def drive_callback(state: str = "", code: str = "", error: str = "") -> HTMLResponse:
    """Finish the sign-in: trade the code for a token and save it. Answers
    a page that tells the user to go back to ClipForge (400 on failure)."""
    try:
        client = _client()
        flow = pending.take(state, client.name)
        if error or not code:
            reason = "access was denied" if error == "access_denied" else error
            raise OAuthError(
                "authorization_denied",
                f"Google Drive was not connected: {reason or 'no code was sent'}.",
            )
        token = exchange_code(client, flow, code)
        TokenStore.from_settings().save(flow.token_ref, token)
    except (OAuthError, ApiError) as exc:
        logger.info("Google Drive sign-in failed: %s", exc)
        return result_page("Google Drive is not connected", str(exc), 400)
    return result_page(
        "Google Drive is connected",
        "You can close this tab and go back to ClipForge.",
        200,
    )


@router.delete("/sources/gdrive/connection", status_code=204)
def disconnect_drive() -> Response:
    """Forget the connected account's token on this machine."""
    TokenStore.from_settings().delete(gdrive.TOKEN_REF)
    return Response(status_code=204)


@router.post("/sources/gdrive/file")
def read_drive_file(body: DriveFileRequest) -> DriveFile:
    """Return the Drive video that a link or id names (see gdrive.get_file
    for the errors)."""
    return _drive_file(body.file)


@router.post("/sources/gdrive/import", status_code=201)
def import_drive_file(
    body: DriveImport,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Project:
    """Add a project for a Drive video and queue its process job, which
    downloads it with the Drive API; 409 if a monthly usage cap is used up."""
    _client()
    require_usage_budget(engine)
    found = _drive_file(body.file)
    job_id = enqueue_process(
        engine,
        gdrive.file_url(found.id),
        body.settings,
        source_rights=body.source_rights,
        credit_line=body.credit_line,
    )
    wake_worker(request)
    return project_of_job(engine, job_id)


def _client() -> OAuthClient:
    """Return the Google OAuth app; 412 needs_credentials without it."""
    try:
        return gdrive.require_client()
    except DriveError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc


def _drive_file(text: str) -> DriveFile:
    """Read the metadata of the Drive video named by text, as ApiErrors."""
    try:
        file_id = gdrive.parse_file_id(text)
        return gdrive.get_file(gdrive.drive_session(), file_id)
    except DriveError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
