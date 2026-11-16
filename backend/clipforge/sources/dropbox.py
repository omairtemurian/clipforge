"""Dropbox source (SPEC-v2 3.1, optional): a Dropbox shared link to a video
becomes a project whose video is downloaded with the Dropbox API as the
account connected through clipforge.oauth.

Verified against Dropbox's API spec and SDK on 2026-11-01 (docs/decisions.md
"TASK-67"): OAuth code flow with PKCE S256 (AUTHORIZE_URL, TOKEN_URL;
`token_access_type=offline` gives a refresh token; no app secret is needed
with PKCE), `sharing/get_shared_link_metadata` (RPC on API_URL, JSON body
{"url"}) and `sharing/get_shared_link_file` (download style on CONTENT_URL:
POST, the argument in the Dropbox-API-Arg header, the file as the body),
both with the `sharing.read` scope.
"""

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel

from clipforge import config
from clipforge.config import Settings
from clipforge.oauth import OAuthClient, OAuthError, OAuthSession
from clipforge.pipeline.download import DOWNLOAD_STEM, Download
from clipforge.pipeline.step import StepError
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
METADATA_URL = "https://api.dropboxapi.com/2/sharing/get_shared_link_metadata"
CONTENT_URL = "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
SCOPE = "sharing.read"
# The connected Dropbox account's token in the TokenStore.
TOKEN_REF = "dropbox"
CLIENT_NAME = "Dropbox"
CHUNK_BYTES = 1 << 20
DROPBOX_HOSTS = frozenset({"dropbox.com", "www.dropbox.com"})
FILE_PREFIXES = ("/s/", "/scl/fi/")
FOLDER_PREFIXES = ("/sh/", "/scl/fo/")
VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".mts"}
    | {".m2ts", ".wmv", ".flv", ".3gp", ".ogv"}
)
NEEDS_CREDENTIALS = (
    "Dropbox needs credentials: set DROPBOX_APP_KEY (and register the "
    "redirect URL, README, Dropbox import)."
)


class DropboxError(StepError):
    """A Dropbox step failed; status and code are the API's answer to it."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class DropboxFile(BaseModel):
    """A Dropbox video behind a shared link: the link, file name and size in
    bytes."""

    url: str
    name: str
    size: int


def dropbox_client(settings: Settings | None = None) -> OAuthClient | None:
    """Return the Dropbox app of the settings, or None when DROPBOX_APP_KEY
    is not set. The app secret is not sent: PKCE replaces it."""
    cfg = settings or config.settings
    key = cfg.dropbox_app_key.strip()
    if not key:
        return None
    return OAuthClient(
        name=CLIENT_NAME,
        client_id=key,
        client_secret="",
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        scopes=(SCOPE,),
        authorize_params={"token_access_type": "offline"},
    )


def require_client() -> OAuthClient:
    """Return dropbox_client(); DropboxError 412 needs_credentials without it."""
    client = dropbox_client()
    if client is None:
        raise DropboxError(412, "needs_credentials", NEEDS_CREDENTIALS)
    return client


def is_connected() -> bool:
    """Return True if Dropbox is configured and an account's token stored."""
    return (
        dropbox_client() is not None
        and TokenStore.from_settings().load(TOKEN_REF) is not None
    )


def dropbox_session(transport: httpx.BaseTransport | None = None) -> OAuthSession:
    """Return the session of the connected account (412 needs_credentials
    if Dropbox is not configured)."""
    return OAuthSession(
        require_client(), TokenStore.from_settings(), TOKEN_REF, transport=transport
    )


def parse_link(text: str) -> str:
    """Return the https shared link of a Dropbox file link (/s/..., /scl/fi/...
    with its query: rlkey, st, dl), without a fragment.

    DropboxError 422 invalid_dropbox_link for anything else, folder links
    (/sh/..., /scl/fo/...) included.
    """
    parts = urlsplit(text.strip())
    if parts.scheme in ("http", "https") and parts.hostname in DROPBOX_HOSTS:
        if parts.path.startswith(FOLDER_PREFIXES):
            raise DropboxError(
                422, "invalid_dropbox_link", "That is a Dropbox folder; link one video."
            )
        if parts.path.startswith(FILE_PREFIXES):
            return urlunsplit(("https", "www.dropbox.com", parts.path, parts.query, ""))
    raise DropboxError(
        422, "invalid_dropbox_link", "That is not a Dropbox shared file link."
    )


def dropbox_link(source: str) -> str | None:
    """Return the normalized shared link if source is a Dropbox file link,
    else None."""
    try:
        return parse_link(source)
    except DropboxError:
        return None


def get_file(session: OAuthSession, link: str) -> DropboxFile:
    """Return the metadata of a shared-link video.

    DropboxError 404 dropbox_file_not_found (unknown link or no access),
    422 not_a_video (a folder or a file that is not a video), 409
    dropbox_not_connected (connect again), 429 dropbox_rate_limited, 502
    dropbox_error otherwise.
    """
    with _dropbox_errors():
        response = session.request("POST", METADATA_URL, json={"url": link})
    _raise_for_status(response)
    body = response.json()
    name = str(body.get("name") or PurePosixPath(urlsplit(link).path).name)
    if body.get(".tag") != "file" or Path(name).suffix.lower() not in VIDEO_SUFFIXES:
        raise DropboxError(422, "not_a_video", f"{name} is not a video file.")
    return DropboxFile(url=link, name=name, size=int(body.get("size", 0)))


def download(
    link: str,
    job_dir: Path,
    on_progress: Callable[[float], None],
    *,
    session: OAuthSession | None = None,
) -> Download:
    """Download the shared-link video into job_dir as download.<ext>.

    on_progress receives the downloaded fraction. Raises DropboxError (a
    StepError) as get_file does, and if the download breaks off or stops
    short of the file's size.
    """
    session = session or dropbox_session()
    info = get_file(session, link)
    dest = job_dir / f"{DOWNLOAD_STEM}{Path(info.name).suffix.lower()}"
    part = dest.with_name(dest.name + ".part")
    job_dir.mkdir(parents=True, exist_ok=True)
    arg = {"Dropbox-API-Arg": json.dumps({"url": link})}
    received = 0
    try:
        with (
            _dropbox_errors(),
            session.stream("POST", CONTENT_URL, headers=arg) as response,
        ):
            if response.status_code != 200:
                response.read()
                _raise_for_status(response)
            with part.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    handle.write(chunk)
                    received += len(chunk)
                    if info.size:
                        on_progress(min(received / info.size, 1.0))
        if received != info.size:
            raise DropboxError(
                502,
                "dropbox_error",
                f"The Dropbox download stopped at {received} of {info.size} bytes.",
            )
    except DropboxError:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    logger.info("downloaded Dropbox file %s (%d bytes)", info.name, received)
    return Download(
        path=dest, title=Path(info.name).stem, channel=None, channel_url=None
    )


@contextmanager
def _dropbox_errors() -> Iterator[None]:
    """Turn OAuth and network errors into DropboxErrors. A refresh token
    that Dropbox rejects is forgotten: the account must connect again."""
    try:
        yield
    except OAuthError as exc:
        if exc.code == "reconnect_required":
            TokenStore.from_settings().delete(TOKEN_REF)
        code = "dropbox_not_connected"
        if exc.code not in {"not_connected", "reconnect_required"}:
            code = exc.code
        raise DropboxError(409, code, exc.message) from exc
    except httpx.HTTPError as exc:
        raise DropboxError(502, "dropbox_error", f"Dropbox failed: {exc}") from exc


def _error_tag(response: httpx.Response) -> str:
    """Return the `.tag` of a Dropbox error body ({"error": {".tag": ...}}),
    or "" if it has none (400 answers are plain text)."""
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return ""
    return str(error.get(".tag", "")) if isinstance(error, dict) else ""


def _raise_for_status(response: httpx.Response) -> None:
    """Raise the DropboxError of a failed shared-link answer."""
    status = response.status_code
    if status == 200:
        return
    tag = _error_tag(response)
    if status == 401:
        raise DropboxError(
            409,
            "dropbox_not_connected",
            "Dropbox refused the sign-in; connect again.",
        )
    if status == 409 and tag in {"shared_link_not_found", "shared_link_access_denied"}:
        raise DropboxError(
            404,
            "dropbox_file_not_found",
            "The Dropbox link was not found, or the connected account cannot open it.",
        )
    if status == 409 and tag == "shared_link_is_directory":
        raise DropboxError(
            422, "invalid_dropbox_link", "That is a Dropbox folder; link one video."
        )
    if status == 429:
        raise DropboxError(
            429, "dropbox_rate_limited", "Dropbox is busy; try again in a moment."
        )
    detail = tag or f"HTTP {status}"
    raise DropboxError(502, "dropbox_error", f"Dropbox answered: {detail}")
