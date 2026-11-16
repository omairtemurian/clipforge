"""Google Drive source (SPEC-v2 3.1): a Drive file link or id becomes a
project whose video is downloaded with the Drive API (files.get alt=media)
as the Google account connected through clipforge.oauth.

Verified against Google's docs on 2026-10-31 (docs/decisions.md "TASK-66"):
OAuth for desktop apps (authorization endpoint AUTHORIZE_URL with PKCE S256,
token endpoint TOKEN_URL), files.get (GET FILES_URL/{fileId}; alt=media for
the content, supportsAllDrives, `fields` with a/b for nested fields) and the
drive.readonly scope ("View and download all your Drive files").
"""

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel

from clipforge import config
from clipforge.config import Settings
from clipforge.oauth import OAuthClient, OAuthError, OAuthSession
from clipforge.pipeline.download import DOWNLOAD_STEM, Download
from clipforge.pipeline.step import StepError
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
METADATA_FIELDS = (
    "id,name,mimeType,size,capabilities/canDownload,videoMediaMetadata/durationMillis"
)
# The connected Google account's token in the TokenStore.
TOKEN_REF = "google-drive"
CLIENT_NAME = "Google Drive"
CHUNK_BYTES = 1 << 20
DRIVE_HOSTS = frozenset(
    {"drive.google.com", "docs.google.com", "drive.usercontent.google.com"}
)
FILE_ID = re.compile(r"[A-Za-z0-9_-]{10,}")
PATH_ID = re.compile(r"/(?:file/)?d/([A-Za-z0-9_-]{10,})(?:/|$)")
NEEDS_CREDENTIALS = (
    "Google Drive needs credentials: set GOOGLE_OAUTH_CLIENT_ID and "
    "GOOGLE_OAUTH_CLIENT_SECRET (README, Google Drive import)."
)


class DriveError(StepError):
    """A Drive step failed; status and code are the API's answer to it."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class DriveFile(BaseModel):
    """A Drive video: its id, file name, MIME type, size in bytes and
    duration in seconds (None when Drive does not say)."""

    id: str
    name: str
    mime_type: str
    size: int | None
    duration: float | None


def google_client(settings: Settings | None = None) -> OAuthClient | None:
    """Return the Google OAuth app of the settings, or None when
    GOOGLE_OAUTH_CLIENT_ID is not set (the client secret is optional for
    desktop apps)."""
    cfg = settings or config.settings
    client_id = cfg.google_oauth_client_id.strip()
    if not client_id:
        return None
    return OAuthClient(
        name=CLIENT_NAME,
        client_id=client_id,
        client_secret=cfg.google_oauth_client_secret.strip(),
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        scopes=(DRIVE_SCOPE,),
    )


def require_client() -> OAuthClient:
    """Return google_client(); DriveError 412 needs_credentials without it."""
    client = google_client()
    if client is None:
        raise DriveError(412, "needs_credentials", NEEDS_CREDENTIALS)
    return client


def is_connected() -> bool:
    """Return True if Google is configured and a Drive token is stored."""
    return (
        google_client() is not None
        and TokenStore.from_settings().load(TOKEN_REF) is not None
    )


def drive_session(transport: httpx.BaseTransport | None = None) -> OAuthSession:
    """Return the session of the connected account (412 needs_credentials
    if Google is not configured)."""
    return OAuthSession(
        require_client(), TokenStore.from_settings(), TOKEN_REF, transport=transport
    )


def parse_file_id(text: str) -> str:
    """Return the file id of a Drive link (.../file/d/<id>/..., open?id=<id>,
    uc?id=<id>, docs.google.com/.../d/<id>) or of a bare file id.

    DriveError 422 invalid_drive_link for anything else, folders included.
    """
    text = text.strip()
    if FILE_ID.fullmatch(text):
        return text
    parts = urlsplit(text)
    if parts.scheme in ("http", "https") and parts.hostname in DRIVE_HOSTS:
        if "/folders/" in parts.path:
            raise DriveError(
                422, "invalid_drive_link", "That is a Drive folder; link one video."
            )
        match = PATH_ID.search(parts.path)
        if match:
            return match.group(1)
        ids = parse_qs(parts.query).get("id", [])
        if ids and FILE_ID.fullmatch(ids[0]):
            return ids[0]
    raise DriveError(
        422, "invalid_drive_link", "That is not a Google Drive file link or file id."
    )


def drive_file_id(source: str) -> str | None:
    """Return the file id if source is a Drive file link, else None."""
    if urlsplit(source).hostname not in DRIVE_HOSTS:
        return None
    try:
        return parse_file_id(source)
    except DriveError:
        return None


def file_url(file_id: str) -> str:
    """Return the Drive link of a file (a project's source_url)."""
    return f"https://drive.google.com/file/d/{file_id}/view"


def get_file(session: OAuthSession, file_id: str) -> DriveFile:
    """Return the metadata of a downloadable Drive video.

    DriveError 404 drive_file_not_found (missing or not shared with the
    account), 422 not_a_video, 422 drive_file_not_downloadable, 409
    drive_not_connected (connect again), 502 drive_error otherwise.
    """
    params = {"fields": METADATA_FIELDS, "supportsAllDrives": "true"}
    with _drive_errors():
        response = session.request("GET", _url(file_id), params=params)
    _raise_for_status(response, file_id)
    body = response.json()
    name = str(body.get("name") or file_id)
    mime_type = str(body.get("mimeType", ""))
    if not mime_type.startswith("video/"):
        raise DriveError(422, "not_a_video", f"{name} is not a video ({mime_type}).")
    if body.get("capabilities", {}).get("canDownload") is False:
        raise DriveError(
            422,
            "drive_file_not_downloadable",
            f"The owner of {name} does not allow downloads.",
        )
    size = body.get("size")
    millis = body.get("videoMediaMetadata", {}).get("durationMillis")
    return DriveFile(
        id=str(body.get("id", file_id)),
        name=name,
        mime_type=mime_type,
        size=int(size) if size is not None else None,
        duration=int(millis) / 1000 if millis is not None else None,
    )


def download(
    file_id: str,
    job_dir: Path,
    on_progress: Callable[[float], None],
    *,
    session: OAuthSession | None = None,
) -> Download:
    """Download the Drive video file_id into job_dir as download.<ext>.

    on_progress receives the downloaded fraction when Drive gave a size.
    Raises DriveError (a StepError) as get_file does, and if the download
    breaks off or stops short of the file's size.
    """
    session = session or drive_session()
    info = get_file(session, file_id)
    suffix = Path(info.name).suffix.lower() or ".mp4"
    dest = job_dir / f"{DOWNLOAD_STEM}{suffix}"
    part = dest.with_name(dest.name + ".part")
    job_dir.mkdir(parents=True, exist_ok=True)
    params = {"alt": "media", "supportsAllDrives": "true"}
    received = 0
    try:
        with (
            _drive_errors(),
            session.stream("GET", _url(file_id), params=params) as response,
        ):
            if response.status_code != 200:
                response.read()
                _raise_for_status(response, file_id)
            with part.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    handle.write(chunk)
                    received += len(chunk)
                    if info.size:
                        on_progress(min(received / info.size, 1.0))
        if info.size is not None and received != info.size:
            raise DriveError(
                502,
                "drive_error",
                f"The Drive download stopped at {received} of {info.size} bytes.",
            )
    except DriveError:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    logger.info("downloaded Drive file %s (%d bytes)", info.name, received)
    return Download(
        path=dest, title=Path(info.name).stem, channel=None, channel_url=None
    )


def _url(file_id: str) -> str:
    return f"{FILES_URL}/{file_id}"


@contextmanager
def _drive_errors() -> Iterator[None]:
    """Turn OAuth and network errors into DriveErrors. A refresh token that
    Google rejects is forgotten: the account must connect again."""
    try:
        yield
    except OAuthError as exc:
        if exc.code == "reconnect_required":
            TokenStore.from_settings().delete(TOKEN_REF)
        code = "drive_not_connected"
        if exc.code not in {"not_connected", "reconnect_required"}:
            code = exc.code
        raise DriveError(409, code, exc.message) from exc
    except httpx.HTTPError as exc:
        raise DriveError(502, "drive_error", f"Google Drive failed: {exc}") from exc


def _raise_for_status(response: httpx.Response, file_id: str) -> None:
    """Raise the DriveError of a failed files.get answer."""
    if response.status_code == 200:
        return
    if response.status_code == 404:
        raise DriveError(
            404,
            "drive_file_not_found",
            f"Drive file {file_id} was not found, or the connected account "
            "cannot open it.",
        )
    if response.status_code == 401:
        raise DriveError(
            409,
            "drive_not_connected",
            "Google Drive refused the sign-in; connect again.",
        )
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = f"HTTP {response.status_code}"
    raise DriveError(502, "drive_error", f"Google Drive answered: {message}")
