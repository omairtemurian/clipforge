"""Meta's Graph API for the Meta publishers (SPEC-v2 3.10): the owner's
Meta app (META_APP_ID / META_APP_SECRET) with Facebook Login for Business,
its long-lived user tokens and the Graph API's answers.

Verified 2026-11-01 (docs/decisions.md "TASK-141") on
https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow,
.../facebook-login/guides/access-tokens/get-long-lived,
.../facebook-login/facebook-login-for-business and
.../graph-api/guides/error-handling:

- Sign-in: https://www.facebook.com/v26.0/dialog/oauth (client_id,
  redirect_uri, state, scope comma or space separated; config_id names a
  Facebook Login for Business configuration). The code is traded with a
  GET of oauth/access_token (client_id, redirect_uri, client_secret, code)
  for {access_token, token_type, expires_in}: a short-lived user token.
- No refresh tokens: GET oauth/access_token?grant_type=fb_exchange_token
  trades a still-valid user token for a long-lived one (about 60 days);
  an expired token cannot be traded (the user signs in again).
- Errors: {"error": {message, type, code, error_subcode, is_transient,
  error_user_title, error_user_msg, fbtrace_id}}; code 190: the token
  expired or was revoked; 10 and 200-299: a permission is missing; 1, 2:
  passing outage; 4, 17, 32, 341, 613 and 80001/80002: rate limits; 368:
  temporarily blocked for policy reasons.
"""

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx

from clipforge import config
from clipforge.config import Settings
from clipforge.oauth import Clock, OAuthClient, refresh
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import Publisher, PublishError

logger = logging.getLogger(__name__)

Sleep = Callable[[float], None]

API_VERSION = "v26.0"
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
AUTHORIZE_URL = f"https://www.facebook.com/{API_VERSION}/dialog/oauth"
TOKEN_URL = f"{GRAPH}/oauth/access_token"
PERMISSIONS_URL = f"{GRAPH}/me/permissions"
SETTINGS_KEYS = ("META_APP_ID", "META_APP_SECRET")
TOKEN_CODE = 190
PERMISSION_CODES = frozenset({10, *range(200, 300)})
RETRYABLE_CODES = frozenset({1, 2, 4, 17, 32, 341, 368, 613, 80001, 80002})


class GraphSession(Protocol):
    """What sends Graph API requests as an account: an OAuthSession (the
    user's token) or a Page token session (facebook_api.BearerSession)."""

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        **body: Any,
    ) -> httpx.Response:
        """Send the request and return its (read) response."""
        ...


class MetaPublisher(Publisher):
    """A publisher for the Meta app: its sign-in ends with the long-lived
    user token; sleep waits between upload tries and status checks."""

    def __init__(
        self,
        client: OAuthClient,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock = time.time,
        sleep: Sleep = time.sleep,
    ) -> None:
        super().__init__(client, transport=transport, clock=clock)
        self.sleep = sleep

    def finish_sign_in(self, token: Token) -> Token:
        """Return the long-lived (about 60 days) token of the sign-in with
        the permissions the user granted."""
        with self.http() as http:
            return long_lived(
                self.client,
                token,
                clock=self.clock,
                transport=self.transport,
                http=http,
            )


def meta_client(
    name: str, scopes: tuple[str, ...], settings: Settings | None = None
) -> OAuthClient | None:
    """Return the Meta app of the settings signing in as name with scopes,
    or None while META_APP_ID or META_APP_SECRET is not set."""
    cfg = settings or config.settings
    app_id = cfg.meta_app_id.strip()
    secret = cfg.meta_app_secret.strip()
    if not app_id or not secret:
        return None
    config_id = cfg.meta_login_config_id.strip()
    return OAuthClient(
        name=name,
        client_id=app_id,
        client_secret=secret,
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        scopes=scopes,
        authorize_params={"config_id": config_id} if config_id else {},
        scope_separator=",",
        token_method="GET",
        refresh_grant=exchange_grant,
    )


def exchange_grant(token: Token) -> dict[str, str]:
    """Return the token request that trades token for a long-lived one."""
    return {"grant_type": "fb_exchange_token", "fb_exchange_token": token.access_token}


def long_lived(
    client: OAuthClient,
    token: Token,
    *,
    clock: Clock,
    transport: httpx.BaseTransport | None,
    http: httpx.Client,
) -> Token:
    """Return the long-lived token of a fresh sign-in, its scope set to the
    permissions the user granted (/me/permissions; kept empty if Meta does
    not say)."""
    lasting = refresh(client, token, clock=clock, transport=transport)
    try:
        response = http.get(
            PERMISSIONS_URL, headers={"Authorization": f"Bearer {lasting.access_token}"}
        )
    except httpx.TransportError as exc:
        logger.info("%s permissions unknown: %s", client.name, type(exc).__name__)
        return lasting
    rows = json_object(response).get("data")
    granted = [
        str(row.get("permission"))
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict) and row.get("status") == "granted"
    ]
    return lasting.model_copy(update={"scope": ",".join(granted)})


def graph_call(
    session: GraphSession,
    method: str,
    url: str,
    action: str,
    platform: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    retryable_subcodes: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """Send a Graph API request as the session's account and return its
    JSON answer; PublishError if it failed (retryable for no answer)."""
    try:
        response = session.request(method, url, params=params, json=body)
    except httpx.TransportError as exc:
        raise PublishError(
            f"Cannot reach {platform}: {type(exc).__name__}", retryable=True
        ) from exc
    return answer_json(response, action, platform, retryable_subcodes)


def answer_json(
    response: httpx.Response,
    action: str,
    platform: str,
    retryable_subcodes: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """Return the JSON object of a 200 answer without an error; else raise
    its graph_error."""
    body = json_object(response)
    if response.status_code == 200 and "error" not in body:
        return body
    raise graph_error(response, action, platform, retryable_subcodes)


def graph_error(
    response: httpx.Response,
    action: str,
    platform: str,
    retryable_subcodes: frozenset[int] = frozenset(),
) -> PublishError:
    """Return the PublishError of a failed Graph API answer: retryable for
    429, 5xx, transient errors, rate limits and retryable_subcodes."""
    raw = json_object(response).get("error")
    error = raw if isinstance(raw, dict) else {}
    code = _int(error.get("code"))
    subcode = _int(error.get("error_subcode"))
    status = response.status_code
    reason = str(error.get("error_user_msg") or error.get("message") or "")
    reason = reason or "no reason given"
    if code == TOKEN_CODE or status == 401:
        return PublishError(
            f"{platform} rejected the sign-in ({reason}); connect the account again."
        )
    if code in PERMISSION_CODES:
        return PublishError(
            f"{platform} refused to {action}: a permission is missing ({reason}); "
            "connect the account again and allow every permission."
        )
    retryable = (
        status == 429
        or status >= 500
        or code in RETRYABLE_CODES
        or subcode in retryable_subcodes
        or error.get("is_transient") is True
    )
    label = f"HTTP {status}"
    if code is not None:
        label += f", code {code}" + (f"/{subcode}" if subcode is not None else "")
    return PublishError(
        f"{platform} refused to {action}: {reason} ({label}).", retryable=retryable
    )


def json_object(response: httpx.Response) -> dict[str, Any]:
    """Return the response's JSON object, or {} if it is not one."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _int(value: object) -> int | None:
    """Return value as an int if it is one (or an int string), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None
