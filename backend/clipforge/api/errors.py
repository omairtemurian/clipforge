"""JSON errors of the API (SPEC 7): every error response is {error, message}.

`error` is a short code (not_found, validation_error, conflict, ...) and
`message` a sentence for the user. A post that may not be published yet
(posts.PublishBlocked: no source rights, clip not rendered, account gone,
SPEC-v2 1.6) is 409 with the guard's code, from any endpoint. An unhandled
exception is logged with its traceback and answered with a generic
internal_error: the traceback never reaches the client.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from clipforge.posts import PublishBlocked

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An error that an endpoint reports as {error: code, message}; extra
    adds fields to that body (e.g. the failed campaign rules) and headers
    adds response headers (e.g. Retry-After of a 429)."""

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.extra = extra or {}
        self.headers = headers


def not_found(what: str, item_id: int) -> ApiError:
    """Return the 404 error for a missing item, e.g. not_found("project", 3)."""
    return ApiError(404, "not_found", f"{what} {item_id} not found")


def install_error_handlers(app: FastAPI) -> None:
    """Make app answer every error with {error, message} JSON."""
    app.add_exception_handler(ApiError, _api_error)  # type: ignore[arg-type]
    app.add_exception_handler(PublishBlocked, _publish_blocked)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error)


def _body(status_code: int, error: str, message: str) -> JSONResponse:
    """Return the JSON error response with the given status."""
    return JSONResponse({"error": error, "message": message}, status_code=status_code)


async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
    body = {"error": exc.error, "message": exc.message, **exc.extra}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


async def _publish_blocked(_request: Request, exc: PublishBlocked) -> JSONResponse:
    """Answer a publish guard's refusal (e.g. source_rights_missing)."""
    return _body(409, exc.code, exc.message)


async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Answer errors that FastAPI raises itself (unknown path, wrong method)."""
    phrase = HTTPStatus(exc.status_code).phrase
    code = "not_found" if exc.status_code == 404 else phrase.lower().replace(" ", "_")
    return _body(exc.status_code, code, str(exc.detail))


async def _validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Answer an invalid request with one line per problem: "body.url: ..."."""
    problems = [
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    ]
    return _body(422, "validation_error", "; ".join(problems))


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Log the traceback and answer with a generic message."""
    logger.error(
        "unhandled error in %s %s", request.method, request.url.path, exc_info=exc
    )
    return _body(500, "internal_error", "Something went wrong on the server.")
