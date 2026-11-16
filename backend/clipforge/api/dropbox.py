"""Dropbox import endpoints (SPEC-v2 3.1, optional), see
clipforge.sources.dropbox:

    GET    /sources/dropbox                -> DropboxStatus
    POST   /sources/dropbox/connect        -> DropboxConnect (the sign-in URL)
    GET    /sources/dropbox/callback       <- Dropbox's redirect; an HTML page
    DELETE /sources/dropbox/connection     -> 204 (forgets the token)
    POST   /sources/dropbox/file           {file} -> DropboxFile
    POST   /sources/dropbox/import         DropboxImport -> Project

Every endpoint but the status answers 412 needs_credentials while
DROPBOX_APP_KEY is not set.
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
from clipforge.sources import dropbox
from clipforge.sources.dropbox import DropboxError, DropboxFile
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)

router = APIRouter()

CALLBACK_ROUTE = "dropbox_callback"


class DropboxStatus(BaseModel):
    """Whether the Dropbox app is configured and an account connected."""

    configured: bool
    connected: bool


class DropboxConnect(BaseModel):
    """The Dropbox sign-in page that connects an account."""

    authorize_url: str


class DropboxFileRequest(BaseModel):
    """The body of POST /sources/dropbox/file: a Dropbox shared file link."""

    file: str = Field(min_length=1, max_length=2048)


class DropboxImport(BaseModel):
    """The body of POST /sources/dropbox/import: the shared file link, how to
    process it and its source rights, as in ProjectCreate."""

    file: str = Field(min_length=1, max_length=2048)
    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)


@router.get("/sources/dropbox")
def dropbox_status() -> DropboxStatus:
    """Return whether Dropbox import can be used."""
    return DropboxStatus(
        configured=dropbox.dropbox_client() is not None,
        connected=dropbox.is_connected(),
    )


@router.post("/sources/dropbox/connect")
def connect_dropbox(request: Request) -> DropboxConnect:
    """Start a Dropbox sign-in whose redirect comes back to the callback."""
    client = _client()
    redirect_uri = str(request.url_for(CALLBACK_ROUTE))
    url = pending.start(client, redirect_uri, dropbox.TOKEN_REF)
    return DropboxConnect(authorize_url=url)


@router.get(
    "/sources/dropbox/callback", name=CALLBACK_ROUTE, response_class=HTMLResponse
)
def dropbox_callback(
    state: str = "",
    code: str = "",
    error: str = "",
    error_description: str = "",
) -> HTMLResponse:
    """Finish the sign-in: trade the code for a token and save it. Answers
    a page that tells the user to go back to ClipForge (400 on failure)."""
    try:
        client = _client()
        flow = pending.take(state, client.name)
        if error or not code:
            reason = "access was denied" if error == "access_denied" else error
            raise OAuthError(
                "authorization_denied",
                f"Dropbox was not connected: {reason or 'no code was sent'}"
                f"{': ' + error_description if error_description else ''}.",
            )
        token = exchange_code(client, flow, code)
        TokenStore.from_settings().save(flow.token_ref, token)
    except (OAuthError, ApiError) as exc:
        logger.info("Dropbox sign-in failed: %s", exc)
        return result_page("Dropbox is not connected", str(exc), 400)
    return result_page(
        "Dropbox is connected",
        "You can close this tab and go back to ClipForge.",
        200,
    )


@router.delete("/sources/dropbox/connection", status_code=204)
def disconnect_dropbox() -> Response:
    """Forget the connected account's token on this machine."""
    TokenStore.from_settings().delete(dropbox.TOKEN_REF)
    return Response(status_code=204)


@router.post("/sources/dropbox/file")
def read_dropbox_file(body: DropboxFileRequest) -> DropboxFile:
    """Return the Dropbox video that a shared link names (see
    dropbox.get_file for the errors)."""
    return _dropbox_file(body.file)


@router.post("/sources/dropbox/import", status_code=201)
def import_dropbox_file(
    body: DropboxImport,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Project:
    """Add a project for a Dropbox video and queue its process job, which
    downloads it with the Dropbox API; 409 if a monthly usage cap is used up."""
    _client()
    require_usage_budget(engine)
    found = _dropbox_file(body.file)
    job_id = enqueue_process(
        engine,
        found.url,
        body.settings,
        source_rights=body.source_rights,
        credit_line=body.credit_line,
    )
    wake_worker(request)
    return project_of_job(engine, job_id)


def _client() -> OAuthClient:
    """Return the Dropbox app; 412 needs_credentials without it."""
    try:
        return dropbox.require_client()
    except DropboxError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc


def _dropbox_file(text: str) -> DropboxFile:
    """Read the metadata of the Dropbox video named by text, as ApiErrors."""
    try:
        link = dropbox.parse_link(text)
        return dropbox.get_file(dropbox.dropbox_session(), link)
    except DropboxError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
