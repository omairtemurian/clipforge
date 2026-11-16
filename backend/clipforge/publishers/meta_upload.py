"""The resumable video upload of the Meta publishers (SPEC-v2 3.10): the
file is POSTed whole to the upload uri of a reel container (Instagram,
rupload.facebook.com/ig-api-upload) or video session (Facebook Page reels,
rupload.facebook.com/video-upload).

Verified 2026-11-01 (docs/decisions.md "TASK-141", "TASK-142") on
https://developers.facebook.com/docs/instagram-platform/content-publishing
and https://developers.facebook.com/docs/video-api/guides/reels-publishing:
the headers are "Authorization: OAuth <token>", "offset: 0" and "file_size:
<bytes>"; Meta answers {"success": true} or {"debug_info": {"retriable",
"type", "message"}}.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from clipforge.publishers.base import PublishError
from clipforge.publishers.meta_graph import Sleep, json_object

MAX_UPLOAD_TRIES = 3


def send_video(
    platform: str,
    http: Callable[[], httpx.Client],
    uri: str,
    access_token: Callable[[], str],
    video: tuple[Path, int],
    sleep: Sleep,
    tries: int = MAX_UPLOAD_TRIES,
) -> None:
    """Send the video file (path, size in bytes) to the upload uri of
    platform, trying again (up to tries times, 2^n s apart) while Meta says
    it may work; PublishError if it never took it."""
    path, size = video
    error = PublishError(f"{platform} did not take the video.", retryable=True)
    for attempt in range(tries):
        if attempt:
            sleep(float(2**attempt))
        headers = {
            "Authorization": f"OAuth {access_token()}",
            "offset": "0",
            "file_size": str(size),
        }
        try:
            with http() as client, path.open("rb") as body:
                response = client.post(uri, headers=headers, content=body)
        except httpx.TransportError as exc:
            error = PublishError(
                f"Cannot reach {platform}: {type(exc).__name__}", retryable=True
            )
            continue
        answer = json_object(response)
        if response.status_code == 200 and answer.get("success") is True:
            return
        error = upload_error(platform, response, answer)
        if not error.retryable:
            break
    raise error


def upload_error(
    platform: str, response: httpx.Response, answer: dict[str, Any]
) -> PublishError:
    """Return the PublishError of a refused upload answer."""
    debug = answer.get("debug_info")
    info = debug if isinstance(debug, dict) else {}
    message = str(info.get("message") or "") or f"HTTP {response.status_code}"
    retryable = info.get("retriable") is True or (
        response.status_code == 429 or response.status_code >= 500
    )
    return PublishError(
        f"{platform} did not take the video: {message}.", retryable=retryable
    )
