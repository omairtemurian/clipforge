"""TikTok API v2 answers and the file upload of the Content Posting API
(SPEC-v2 3.10).

Verified 2026-11-01 (docs/decisions.md "TASK-140") on
https://developers.tiktok.com/doc/content-posting-api-reference-direct-post,
.../content-posting-api-media-transfer-guide,
.../content-posting-api-reference-get-video-status and
.../tiktok-api-v2-error-handling:

- Every answer carries {"data": {...}, "error": {"code", "message",
  "log_id"}}; anything but code "ok" failed, even with HTTP 200 (the
  creator_info query answers spam_risk_* with 200).
- FILE_UPLOAD: init answers an upload_url (valid one hour) that takes the
  file in PUTs with Content-Range "bytes first-last/total": 206 while
  chunks remain, 201 once all arrived; 403 expired link, 404 unknown
  upload, 416 wrong range, 5xx retry the chunk. Chunks are 5-64 MB, the
  last may hold the trailing bytes (up to 128 MB), total_chunk_count =
  floor(size / chunk_size), a file under 5 MB goes whole, 1-1000 chunks.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from clipforge.oauth import OAuthSession
from clipforge.publishers.base import PublishError

logger = logging.getLogger(__name__)

API = "https://open.tiktokapis.com/v2"
CHUNK_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 4 * 1024**3
# Failed tries of one chunk (no answer or 5xx) before the post waits.
MAX_CHUNK_RETRIES = 5
JSON = {"Content-Type": "application/json; charset=UTF-8"}
# Error codes that pass with time (rate limits, daily caps, outages).
RETRYABLE_CODES = frozenset(
    {
        "rate_limit_exceeded",
        "spam_risk_too_many_posts",
        "reached_active_user_cap",
        "internal_error",
    }
)
CODE_TEXT = {
    "spam_risk_too_many_posts": "the account reached TikTok's daily post cap",
    "reached_active_user_cap": "the app reached TikTok's daily cap of posting users",
    "spam_risk_user_banned_from_posting": "TikTok banned the account from posting",
    "unaudited_client_can_only_post_to_private_accounts": (
        "an unaudited TikTok app can only post SELF_ONLY to private accounts"
    ),
    "privacy_level_option_mismatch": "the privacy level is not one of the account's",
    "rate_limit_exceeded": "too many requests, try again in a minute",
}

SCOPE_MISSING = (
    "Posting was not allowed at the TikTok sign-in (video.publish); connect "
    "the account again and allow it."
)

Sleep = Callable[[float], None]


def answer_data(response: httpx.Response, action: str) -> dict[str, Any]:
    """Return the data of a TikTok answer; PublishError (retryable for 429,
    5xx and RETRYABLE_CODES) if it is not "ok"."""
    body = _json(response)
    error = body.get("error")
    nested = error if isinstance(error, dict) else body
    code = str(nested.get("code") or "")
    message = str(nested.get("message") or "")
    status = response.status_code
    if status == 200 and code == "ok":
        data = body.get("data")
        return data if isinstance(data, dict) else {}
    if status == 401:
        raise PublishError(
            SCOPE_MISSING
            if code == "scope_not_authorized"
            else "TikTok rejected the sign-in; connect the account again."
        )
    detail = CODE_TEXT.get(code) or message or code or "no reason given"
    retryable = status == 429 or status >= 500 or code in RETRYABLE_CODES
    label = f"HTTP {status}, {code}" if code else f"HTTP {status}"
    raise PublishError(
        f"TikTok refused to {action}: {detail} ({label}).", retryable=retryable
    )


def post_json(
    session: OAuthSession, url: str, body: dict[str, Any] | None, action: str
) -> dict[str, Any]:
    """POST body (JSON) as the session's account and return the answer's
    data; a network failure is a retryable PublishError."""
    try:
        response = session.request("POST", url, json=body, headers=JSON)
    except httpx.TransportError as exc:
        raise PublishError(
            f"Cannot reach TikTok: {type(exc).__name__}", retryable=True
        ) from exc
    return answer_data(response, action)


def chunk_plan(size: int, chunk_bytes: int) -> tuple[int, int]:
    """Return (chunk_size, total_chunk_count) of a file of size bytes: one
    whole chunk up to chunk_bytes, else floor(size / chunk_bytes) chunks
    whose last one also takes the trailing bytes."""
    if size <= chunk_bytes:
        return size, 1
    return chunk_bytes, size // chunk_bytes


def send_file(
    http: Callable[[], httpx.Client],
    upload_url: str,
    path: Path,
    mime: str,
    plan: tuple[int, int],
    sleep: Sleep,
) -> None:
    """PUT the file to upload_url in the plan's chunks, in order; a chunk
    that gets no answer or a 5xx is sent again after 2^n s."""
    size = path.stat().st_size
    chunk_size, count = plan
    with http() as client, path.open("rb") as file:
        for index in range(count):
            first = index * chunk_size
            last = size - 1 if index == count - 1 else first + chunk_size - 1
            file.seek(first)
            data = file.read(last - first + 1)
            headers = {
                "Content-Type": mime,
                "Content-Range": f"bytes {first}-{last}/{size}",
            }
            _put_chunk(client, upload_url, data, headers, sleep)


def _put_chunk(
    client: httpx.Client,
    url: str,
    data: bytes,
    headers: dict[str, str],
    sleep: Sleep,
) -> None:
    """PUT one chunk until TikTok takes it (206 or 201)."""
    failures = 0
    while True:
        try:
            response = client.put(url, content=data, headers=headers)
            status = response.status_code
        except httpx.TransportError as exc:
            logger.info("TikTok upload interrupted: %s", type(exc).__name__)
            status = None
        if status in (201, 206):
            return
        if status is not None and status < 500:
            raise _upload_refusal(status)
        failures += 1
        if failures > MAX_CHUNK_RETRIES:
            raise PublishError(
                "The upload to TikTok was interrupted too often.", retryable=True
            )
        sleep(float(2**failures))


def _upload_refusal(status: int) -> PublishError:
    """Return the PublishError of a refused chunk: an expired or unknown
    upload or a range mismatch starts the post again later."""
    if status == 403:
        return PublishError("The TikTok upload link expired.", retryable=True)
    if status == 404:
        return PublishError("TikTok lost the upload.", retryable=True)
    if status == 416:
        return PublishError(
            "TikTok's upload progress did not match; the upload starts again.",
            retryable=True,
        )
    return PublishError(f"TikTok refused the video file (HTTP {status}).")


def _json(response: httpx.Response) -> dict[str, Any]:
    """Return the response's JSON object, or {} if it is not one."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
