"""OAuth 2.0 authorization code flow with PKCE (RFC 7636), shared by the
cloud imports and, later, the social publishers (SPEC-v2 3.1, 4).

- OAuthClient: one provider app (endpoints, client id/secret, scopes).
- PendingFlows (clipforge.oauth_flows): the started consents by `state`,
  with their PKCE code verifiers.
- exchange_code() / refresh(): the token endpoint calls (form-encoded POST,
  or a GET with the form as query for Meta).
- Token (clipforge.oauth_tokens) and TokenStore (clipforge.token_store):
  tokens as encrypted 0600 files named by a token_ref.
- OAuthSession: requests with the stored access token; it refreshes the
  token when it expires and once more after a 401.

Google's flow for desktop apps is the reference (docs/decisions.md
"TASK-66"): loopback redirect URI, S256 code challenge, form-encoded token
endpoint answering {access_token, expires_in, refresh_token, scope,
token_type}; a refresh answer may omit the refresh_token, which is kept.
"""

import logging
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx

from clipforge.oauth_tokens import Token
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(60.0, connect=10.0)

Clock = Callable[[], float]


class OAuthError(Exception):
    """An OAuth step failed. code is a short API error code: invalid_state,
    authorization_denied, token_error, not_connected, reconnect_required."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class OAuthClient:
    """A provider app: its endpoints, credentials and the scopes it asks
    for; authorize_params are added to the authorization URL. Providers
    that differ from RFC 6749/7636 set client_id_param (the name of the
    client id parameter, TikTok: client_key), scope_separator (TikTok: ",")
    and pkce_hex (TikTok's desktop flow: the hex SHA-256 code challenge);
    token_method GET sends the token form as query (Meta), and refresh_grant
    returns the refresh form for providers without refresh tokens (Meta
    exchanges the still-valid access token for a new one)."""

    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    authorize_params: Mapping[str, str] = field(default_factory=dict)
    client_id_param: str = "client_id"
    scope_separator: str = " "
    pkce_hex: bool = False
    token_method: str = "POST"
    refresh_grant: Callable[[Token], dict[str, str]] | None = field(
        default=None, compare=False
    )

    def granted(self, scope: str) -> list[str]:
        """Return the scopes of a token answer's scope string (split on
        whitespace and commas)."""
        return [part for part in re.split(r"[\s,]+", scope) if part]


@dataclass(frozen=True)
class Flow:
    """A started authorization: what the callback needs to finish it."""

    client_name: str
    token_ref: str
    redirect_uri: str
    code_verifier: str
    started_at: float


def exchange_code(
    client: OAuthClient,
    flow: Flow,
    code: str,
    *,
    clock: Clock = time.time,
    transport: httpx.BaseTransport | None = None,
) -> Token:
    """Trade an authorization code for a token (grant_type
    authorization_code, with the flow's code_verifier); OAuthError
    token_error if the provider refuses."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": flow.code_verifier,
        "redirect_uri": flow.redirect_uri,
        client.client_id_param: client.client_id,
    }
    if client.client_secret:
        form["client_secret"] = client.client_secret
    return _token_request(client, form, clock, transport, previous=None)


def refresh(
    client: OAuthClient,
    token: Token,
    *,
    clock: Clock = time.time,
    transport: httpx.BaseTransport | None = None,
) -> Token:
    """Get a new access token with token's refresh_token (grant_type
    refresh_token) or the client's refresh_grant. OAuthError
    reconnect_required if there is no refresh token or the provider rejects
    it (invalid_grant / Meta's code 190: revoked or expired)."""
    if client.refresh_grant is not None:
        form = client.refresh_grant(token)
    elif not token.refresh_token:
        raise OAuthError(
            "reconnect_required", f"The {client.name} sign-in expired; connect again."
        )
    else:
        form = {"grant_type": "refresh_token", "refresh_token": token.refresh_token}
    form[client.client_id_param] = client.client_id
    if client.client_secret:
        form["client_secret"] = client.client_secret
    return _token_request(client, form, clock, transport, previous=token)


def _token_request(
    client: OAuthClient,
    form: dict[str, str],
    clock: Clock,
    transport: httpx.BaseTransport | None,
    previous: Token | None,
) -> Token:
    """POST form to the token endpoint and return the Token it answers.

    A refresh (previous set) keeps previous's refresh token when the answer
    has none.
    """
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT) as http:
            as_query = client.token_method == "GET"
            response = http.request(
                client.token_method,
                client.token_url,
                params=form if as_query else None,
                data=None if as_query else form,
            )
    except httpx.HTTPError as exc:
        raise OAuthError(
            "token_error", f"Cannot reach {client.name} to sign in: {exc}"
        ) from exc
    body = _json_object(response)
    if response.status_code != 200 or ("error" in body and "access_token" not in body):
        raw = body.get("error", f"HTTP {response.status_code}")
        # Meta answers {"error": {"message", "type", "code": 190, ...}}.
        nested = raw if isinstance(raw, dict) else {}
        error = str(nested.get("code", raw) if nested else raw)
        logger.warning("%s token endpoint refused: %s", client.name, error)
        code = (
            "reconnect_required"
            if previous and error in ("invalid_grant", "190")
            else "token_error"
        )
        detail = body.get("error_description") or nested.get("message") or error
        raise OAuthError(code, f"{client.name} refused the sign-in: {detail}")
    access = body.get("access_token")
    if not isinstance(access, str) or not access:
        raise OAuthError("token_error", f"{client.name} sent no access token")
    expires_in = body.get("expires_in")
    refresh_token = body.get("refresh_token")
    return Token(
        access_token=access,
        refresh_token=refresh_token
        if isinstance(refresh_token, str) and refresh_token
        else (previous.refresh_token if previous else None),
        expires_at=clock() + float(expires_in)
        if isinstance(expires_in, int | float)
        else None,
        scope=str(body.get("scope", previous.scope if previous else "")),
        token_type=str(body.get("token_type", "Bearer")),
    )


def _json_object(response: httpx.Response) -> dict[str, object]:
    """Return the response's JSON object, or {} if it is not one."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


class OAuthSession:
    """Sends requests as the account whose token is stored under token_ref.

    The access token is refreshed (and saved) when it is about to expire,
    and once more when the provider answers 401 anyway. OAuthError
    not_connected if no token is stored; reconnect_required if refreshing
    fails for good.
    """

    def __init__(
        self,
        client: OAuthClient,
        store: TokenStore,
        token_ref: str,
        *,
        clock: Clock = time.time,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = client
        self.store = store
        self.token_ref = token_ref
        self.clock = clock
        self.transport = transport
        self._lock = threading.Lock()

    def access_token(self, *, force_refresh: bool = False) -> str:
        """Return a usable access token, refreshing it if needed (or if
        force_refresh)."""
        with self._lock:
            token = self.store.load(self.token_ref)
            if token is None:
                raise OAuthError(
                    "not_connected", f"{self.client.name} is not connected."
                )
            if force_refresh or token.expired(self.clock()):
                token = refresh(
                    self.client, token, clock=self.clock, transport=self.transport
                )
                self.store.save(self.token_ref, token)
            return token.access_token

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        **body: Any,
    ) -> httpx.Response:
        """Send a request and return its (read) response; body takes the
        keyword arguments of stream() (headers, content, json, ...)."""
        with self.stream(method, url, params=params, **body) as response:
            response.read()
            return response

    @contextmanager
    def stream(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        json: Any = None,
        follow_redirects: bool = True,
    ) -> Iterator[httpx.Response]:
        """Send a request (with headers and a content or json body, if
        given) and yield the response with its body unread (for downloads);
        a 401 is retried once with a refreshed token."""
        with httpx.Client(
            transport=self.transport, timeout=TIMEOUT, follow_redirects=follow_redirects
        ) as http:
            token = self.access_token()
            for attempt in range(2):
                request = http.build_request(
                    method,
                    url,
                    params=params,
                    headers={**(headers or {}), "Authorization": f"Bearer {token}"},
                    content=content,
                    json=json,
                )
                response = http.send(request, stream=True)
                if response.status_code != 401 or attempt == 1:
                    try:
                        yield response
                    finally:
                        response.close()
                    return
                response.close()
                logger.info("%s answered 401; refreshing the token", self.client.name)
                token = self.access_token(force_refresh=True)
