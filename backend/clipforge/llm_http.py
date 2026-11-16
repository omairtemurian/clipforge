"""HTTP for the LLM clients in clipforge.llm: one JSON POST per call (and
a GET of Copilot's model list).

post_json() and get_json() turn every failure into LLMError: no connection, an HTTP
error status (with an excerpt of the body), or an answer that does not
parse. The credential sent in the headers is redacted wherever the
server's text is quoted, and is never logged.
"""

import logging
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

# Curating a long transcript window can take minutes on a local model.
TIMEOUT = httpx.Timeout(300.0, connect=10.0)
EXCERPT_CHARS = 500
REDACTED = "***"

ReplyT = TypeVar("ReplyT", bound=BaseModel)

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM gave no answer: no credentials, no connection, an HTTP error
    status, or a reply that is not a chat answer.

    status_code is the HTTP status when the server answered, else None.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def join_url(base: str, path: str) -> str:
    """Return base and path joined by exactly one slash.

    Unlike RFC 3986 resolution, the last segment of base is kept:
    "https://models.github.ai/inference" + "chat/completions" gives
    "https://models.github.ai/inference/chat/completions".
    """
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _excerpt(text: str, secret: str) -> str:
    """Return text on one line, cut to EXCERPT_CHARS, with secret redacted."""
    if secret:
        text = text.replace(secret, REDACTED)
    line = " ".join(text.split())
    if len(line) > EXCERPT_CHARS:
        return line[:EXCERPT_CHARS] + "…"
    return line or "(empty body)"


def post_json(
    provider: str,
    url: str,
    body: dict[str, Any],
    reply_type: type[ReplyT],
    *,
    headers: dict[str, str],
    secret: str,
    transport: httpx.BaseTransport | None,
) -> ReplyT:
    """POST body as JSON to url and return the answer parsed as reply_type.

    Raises LLMError if the server cannot be reached, answers with a non-2xx
    status (the message has the status and an excerpt of the body), or sends
    something that is not a reply_type. secret (the credential in headers)
    is replaced by "***" wherever the server's text is quoted. provider
    prefixes the messages; transport, if given, replaces the network.
    """
    started = time.monotonic()
    reply = _send(
        provider,
        "POST",
        url,
        reply_type,
        body=body,
        headers=headers,
        secret=secret,
        transport=transport,
    )
    logger.info(
        "%s %s replied in %.1fs", provider, body["model"], time.monotonic() - started
    )
    return reply


def get_json(
    provider: str,
    url: str,
    reply_type: type[ReplyT],
    *,
    headers: dict[str, str],
    secret: str,
    transport: httpx.BaseTransport | None,
) -> ReplyT:
    """GET url and return the answer parsed as reply_type; fails like
    post_json (LLMError, with secret redacted)."""
    return _send(
        provider,
        "GET",
        url,
        reply_type,
        body=None,
        headers=headers,
        secret=secret,
        transport=transport,
    )


def _send(
    provider: str,
    method: str,
    url: str,
    reply_type: type[ReplyT],
    *,
    body: dict[str, Any] | None,
    headers: dict[str, str],
    secret: str,
    transport: httpx.BaseTransport | None,
) -> ReplyT:
    """Send one request (body as JSON, if any) and parse its answer; see
    post_json for the errors."""
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT) as http:
            response = http.request(method, url, json=body, headers=headers)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        reason = _excerpt(str(exc) or type(exc).__name__, secret)
        raise LLMError(f"{provider}: cannot reach {url}: {reason}") from exc
    status = response.status_code
    if not response.is_success:
        raise LLMError(
            f"{provider}: HTTP {status} from {url}: {_excerpt(response.text, secret)}",
            status_code=status,
        )
    try:
        return reply_type.model_validate_json(response.content)
    except ValidationError as exc:
        # from None: pydantic's message quotes the reply, which may echo secret.
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"]) or "reply"
        raise LLMError(
            f"{provider}: unexpected reply from {url} ({where}: {error['msg']}): "
            f"{_excerpt(response.text, secret)}",
            status_code=status,
        ) from None
