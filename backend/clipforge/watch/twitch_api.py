"""The Twitch API calls of the go-live watch (T28c; checked 2026-10-31 in
https://dev.twitch.tv/docs/api/reference and
https://dev.twitch.tv/docs/authentication/getting-tokens-oauth,
docs/decisions.md TASK-195).

TwitchApp gets an app access token with the client credentials grant (POST
id.twitch.tv/oauth2/token), keeps it until a minute before it expires and
gets a new one once if Helix answers 401. Helix calls send it as
"Authorization: Bearer" with the app's Client-Id: Get Users (logins to
broadcaster ids), Get Streams (which of up to 100 broadcasters are live)
and Create EventSub Subscription (a stream.online webhook).
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_URL = "https://api.twitch.tv/helix"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
BATCH = 100
REFRESH_EARLY_S = 60.0


class TwitchError(RuntimeError):
    """A Twitch call failed; the message says why (never the secret) and
    status is the HTTP status (0: no answer)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class TwitchApp:
    """A Twitch app (client id and secret) and its cached app token."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.transport = transport
        self.clock = clock
        self._token = ""
        self._expires = 0.0

    @property
    def configured(self) -> bool:
        """Whether both the client id and the secret are set."""
        return bool(self.client_id and self.client_secret)

    def users(self, logins: list[str]) -> list[dict[str, Any]]:
        """Return the Get Users data of the logins (unknown ones are left
        out)."""
        found: list[dict[str, Any]] = []
        for start in range(0, len(logins), BATCH):
            params = [("login", login) for login in logins[start : start + BATCH]]
            found += self._helix("GET", "/users", params=params)["data"]
        return found

    def live_streams(self, user_ids: list[str]) -> list[dict[str, Any]]:
        """Return the Get Streams data of those broadcasters that are live."""
        live: list[dict[str, Any]] = []
        for start in range(0, len(user_ids), BATCH):
            batch = user_ids[start : start + BATCH]
            params = [("user_id", user_id) for user_id in batch]
            params += [("type", "live"), ("first", str(BATCH))]
            live += self._helix("GET", "/streams", params=params)["data"]
        return live

    def subscribe_online(self, user_id: str, callback: str, secret: str) -> str:
        """Create a stream.online webhook subscription; return its id."""
        body = {
            "type": "stream.online",
            "version": "1",
            "condition": {"broadcaster_user_id": user_id},
            "transport": {"method": "webhook", "callback": callback, "secret": secret},
        }
        data = self._helix("POST", "/eventsub/subscriptions", json=body)["data"]
        return str(data[0]["id"])

    def _helix(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._send(method, path, **kwargs)
        if response.status_code == 401:
            self._token = ""
            response = self._send(method, path, **kwargs)
        if not response.is_success:
            raise TwitchError(
                _failure(f"Twitch {path}", response), response.status_code
            )
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise TwitchError(f"Twitch {path} answered an unexpected body")
        return payload

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._app_token()}",
            "Client-Id": self.client_id,
        }
        try:
            with httpx.Client(transport=self.transport, timeout=TIMEOUT) as http:
                return http.request(method, HELIX_URL + path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise TwitchError(f"could not reach Twitch: {exc}") from exc

    def _app_token(self) -> str:
        if not self.configured:
            raise TwitchError("needs the Twitch app keys")
        if self._token and self.clock() < self._expires:
            return self._token
        form = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        try:
            with httpx.Client(transport=self.transport, timeout=TIMEOUT) as http:
                response = http.post(TOKEN_URL, data=form)
        except httpx.HTTPError as exc:
            raise TwitchError(f"could not reach Twitch: {exc}") from exc
        if not response.is_success:
            raise TwitchError(
                _failure("the Twitch app token request", response), response.status_code
            )
        payload = response.json()
        self._token = str(payload["access_token"])
        lifetime = float(payload.get("expires_in", 0))
        self._expires = self.clock() + max(lifetime - REFRESH_EARLY_S, 0.0)
        return self._token


def _failure(what: str, response: httpx.Response) -> str:
    try:
        message = str(response.json().get("message", ""))[:200]
    except ValueError:
        message = ""
    suffix = f": {message}" if message else ""
    return f"{what} answered HTTP {response.status_code}{suffix}"
