"""API key check and rate limit of the public REST API /api/v1 (SPEC-v2
3.14).

A request sends its key as `X-API-Key: <key>` or `Authorization: Bearer
<key>` (both are security schemes of the OpenAPI document, so /api/docs
can send them). No key: 401 api_key_missing; an unknown or revoked key:
401 api_key_invalid; more than api_rate_limit_per_min requests of one key
within a minute: 429 rate_limited with Retry-After (seconds).
"""

import math
import threading
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine

from clipforge import api_keys
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError
from clipforge.models import ApiKey
from clipforge.scheduler.rate_limits import RateLimit

API_KEY_HEADER = "X-API-Key"
RATE_WINDOW = timedelta(minutes=1)
CHALLENGE = {"WWW-Authenticate": "Bearer"}

key_header = APIKeyHeader(
    name=API_KEY_HEADER,
    scheme_name="ApiKey",
    description="An API key made in ClipForge (POST /api/api-keys).",
    auto_error=False,
)
bearer = HTTPBearer(
    scheme_name="Bearer",
    description="The same API key as `Authorization: Bearer <key>`.",
    auto_error=False,
)


class KeyRateLimiter:
    """At most per_minute requests of each API key within any minute
    (thread safe: sync endpoints run in a thread pool)."""

    def __init__(self, per_minute: int) -> None:
        self.limit = RateLimit(RATE_WINDOW, per_minute, "API requests per minute")
        self._requests: defaultdict[int, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def admit(self, key_id: int, now: datetime) -> datetime | None:
        """Count a request of key key_id at now and return None, or return
        when the key may send its next request (the request is not
        counted)."""
        with self._lock:
            times = self._requests[key_id]
            while times and times[0] <= now - RATE_WINDOW:
                times.popleft()
            free_at = self.limit.free_at(times, now)
            if free_at is None:
                times.append(now)
            return free_at


def require_api_key(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    header_key: Annotated[str | None, Security(key_header)],
    bearer_key: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> ApiKey:
    """Dependency of every /api/v1 endpoint: return the request's API key
    after the key check and the rate limit (401, 429 otherwise)."""
    key = header_key or (bearer_key.credentials if bearer_key is not None else None)
    if not key:
        raise ApiError(
            401,
            "api_key_missing",
            f"Send an API key as {API_KEY_HEADER} or Authorization: Bearer.",
            headers=CHALLENGE,
        )
    now = datetime.now(UTC)
    found = api_keys.authenticate(engine, key, now)
    if found is None:
        raise ApiError(
            401, "api_key_invalid", "The API key is not valid.", headers=CHALLENGE
        )
    limiter: KeyRateLimiter = request.app.state.api_limiter
    free_at = limiter.admit(found.id, now)
    if free_at is not None:
        wait = max(1, math.ceil((free_at - now).total_seconds()))
        raise ApiError(
            429,
            "rate_limited",
            f"Too many requests with this API key; "
            f"at most {limiter.limit.most} per minute. Try again in {wait} s.",
            headers={"Retry-After": str(wait)},
        )
    return found
