"""YouTube's resumable upload protocol and API errors (SPEC-v2 3.10).

Verified 2026-11-01 (docs/decisions.md "TASK-139") against
https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol
and https://developers.google.com/youtube/data/reference/rest/v3/errors:

1. POST UPLOAD_URL?uploadType=resumable&part=... with the video resource
   (JSON) and X-Upload-Content-Length/-Type -> 200 with the session URI in
   Location.
2. PUT the file to the session URI in chunks (a multiple of 256 KiB, same
   size but the last) with Content-Range "bytes first-last/total": 308
   (Range "bytes=0-n": received so far) until 200/201 with the video.
3. Interrupted (no answer) or 500/502/503/504: PUT an empty body with
   Content-Range "bytes */total" to ask how much arrived (308 + Range, or
   the final answer if the upload completed), back off, resume from the
   next byte. 404: the session expired (start again).
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from clipforge.oauth import OAuthSession
from clipforge.publishers.base import PublishError

logger = logging.getLogger(__name__)

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_UNIT = 256 * 1024
CHUNK_BYTES = 32 * CHUNK_UNIT
# Interruptions of one upload (in a row, without progress) before giving up.
MAX_RESUMES = 5
RESUMABLE_STATUSES = frozenset({500, 502, 503, 504})
# Error reasons that pass with time (rate limits, daily quotas and limits).
RETRYABLE_REASONS = frozenset(
    {
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
        "uploadLimitExceeded",
        "uploadRateLimitExceeded",
    }
)
RANGE = re.compile(r"bytes=0-(\d+)")

Sleep = Callable[[float], None]


def api_error(response: httpx.Response, action: str) -> PublishError:
    """Return the PublishError of a failed YouTube answer: retryable for 429,
    5xx and the RETRYABLE_REASONS; a 401 (after the token refresh) asks to
    reconnect."""
    error = _json(response).get("error")
    reason, message = "", ""
    if isinstance(error, dict):
        message = str(error.get("message", ""))
        errors = error.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            reason = str(errors[0].get("reason", ""))
    status = response.status_code
    if status == 401:
        return PublishError(
            "YouTube rejected the sign-in; connect the account again.",
        )
    detail = f"{reason}: {message}" if reason and message else reason or message
    retryable = status == 429 or status >= 500 or reason in RETRYABLE_REASONS
    return PublishError(
        f"YouTube refused to {action} (HTTP {status}"
        + (f", {detail})" if detail else ")"),
        retryable=retryable,
    )


def start_session(
    session: OAuthSession,
    video: dict[str, Any],
    params: dict[str, str],
    size: int,
    mime: str,
) -> str:
    """Start a resumable upload of video (the resource sent as metadata)
    and return its session URI."""
    response = _send(
        session,
        "POST",
        UPLOAD_URL,
        params={"uploadType": "resumable", **params},
        json=video,
        headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": mime},
    )
    location = response.headers.get("Location")
    if response.status_code != 200 or not location:
        raise api_error(response, "start the upload")
    return str(location)


def send_file(
    session: OAuthSession,
    upload_url: str,
    path: Path,
    mime: str,
    *,
    chunk_bytes: int = CHUNK_BYTES,
    sleep: Sleep,
) -> dict[str, Any]:
    """PUT the file to upload_url chunk by chunk, resuming after
    interruptions, and return the video resource YouTube created."""
    size = path.stat().st_size
    offset = 0
    failures = 0
    with path.open("rb") as file:
        while True:
            file.seek(offset)
            chunk = file.read(chunk_bytes)
            sent = f"bytes {offset}-{offset + len(chunk) - 1}/{size}"
            response = _put(
                session,
                upload_url,
                chunk,
                {"Content-Type": mime, "Content-Range": sent},
            )
            done = _progress(response, size)
            if isinstance(done, dict):
                return done
            if done is not None:
                offset, failures = done, 0
                continue
            failures += 1
            if failures > MAX_RESUMES:
                raise PublishError(
                    "The upload to YouTube was interrupted too often.", retryable=True
                )
            sleep(float(2**failures))
            status = _put(
                session, upload_url, b"", {"Content-Range": f"bytes */{size}"}
            )
            resumed = _progress(status, size)
            if isinstance(resumed, dict):
                return resumed
            if resumed is not None:
                logger.info("YouTube upload resumes at byte %s of %s", resumed, size)
                offset = resumed


def _progress(
    response: httpx.Response | None, size: int
) -> dict[str, Any] | int | None:
    """Return what an upload PUT answer means: the video resource (done),
    the offset to send next (308), or None (interrupted: ask and resume).
    PublishError for a final failure or an expired session."""
    if response is None or response.status_code in RESUMABLE_STATUSES:
        return None
    if response.status_code in (200, 201):
        video = _json(response)
        if not isinstance(video.get("id"), str):
            raise PublishError("YouTube answered the upload without a video id.")
        return video
    if response.status_code == 308:
        match = RANGE.fullmatch(response.headers.get("Range", ""))
        offset = int(match.group(1)) + 1 if match else 0
        if offset > size:
            raise PublishError("YouTube reported more bytes than the file has.")
        return offset
    if response.status_code == 404:
        raise PublishError("The YouTube upload session expired.", retryable=True)
    raise api_error(response, "take the video")


def _put(
    session: OAuthSession, url: str, content: bytes, headers: dict[str, str]
) -> httpx.Response | None:
    """PUT content to the upload session; None if no answer came."""
    try:
        return session.request(
            "PUT", url, content=content, headers=headers, follow_redirects=False
        )
    except httpx.TransportError as exc:
        logger.info("YouTube upload interrupted: %s", type(exc).__name__)
        return None


def _send(
    session: OAuthSession, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    """Send a request; a network failure is a retryable PublishError."""
    try:
        return session.request(method, url, **kwargs)
    except httpx.TransportError as exc:
        raise PublishError(
            f"Cannot reach YouTube: {type(exc).__name__}", retryable=True
        ) from exc


def _json(response: httpx.Response) -> dict[str, Any]:
    """Return the response's JSON object, or {} if it is not one."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
