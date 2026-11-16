"""Pending OAuth authorizations: start() returns the provider's
authorization URL and remembers its random `state` with the PKCE (RFC 7636,
S256) code verifier; take() hands the flow back exactly once when the
provider redirects to the callback. In memory: a restart forgets them."""

import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlencode

from clipforge.oauth import Clock, Flow, OAuthClient, OAuthError
from clipforge.oauth_tokens import check_ref

# A pending authorization expires after this many seconds.
FLOW_TTL_S = 600.0


def code_challenge(verifier: str, *, hex_digest: bool = False) -> str:
    """Return the S256 code challenge of verifier: BASE64URL(SHA256(verifier))
    without padding (RFC 7636), or its hex SHA-256 (hex_digest: TikTok's
    desktop flow)."""
    digest = hashlib.sha256(verifier.encode("ascii"))
    if hex_digest:
        return digest.hexdigest()
    return base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")


class PendingFlows:
    """The authorizations started and not yet finished, by state."""

    def __init__(self, clock: Clock = time.time) -> None:
        self.clock = clock
        self._flows: dict[str, Flow] = {}
        self._lock = threading.Lock()

    def start(self, client: OAuthClient, redirect_uri: str, token_ref: str) -> str:
        """Remember a new flow whose token goes to token_ref and return the
        URL where the user signs in and consents."""
        check_ref(token_ref)
        state = secrets.token_urlsafe(32)
        # 64 random bytes -> 86 unreserved characters (43..128 allowed)
        verifier = secrets.token_urlsafe(64)
        flow = Flow(client.name, token_ref, redirect_uri, verifier, self.clock())
        with self._lock:
            self._drop_expired()
            self._flows[state] = flow
        query = {
            client.client_id_param: client.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": client.scope_separator.join(client.scopes),
            "state": state,
            "code_challenge": code_challenge(verifier, hex_digest=client.pkce_hex),
            "code_challenge_method": "S256",
            **client.authorize_params,
        }
        return f"{client.authorize_url}?{urlencode(query)}"

    def take(self, state: str, client_name: str) -> Flow:
        """Return and forget the flow of state; OAuthError invalid_state if
        it is unknown, expired or was started for another client."""
        with self._lock:
            self._drop_expired()
            flow = self._flows.pop(state, None)
        if flow is None or flow.client_name != client_name:
            raise OAuthError(
                "invalid_state",
                "This sign-in link is unknown or expired; start the connection again.",
            )
        return flow

    def _drop_expired(self) -> None:
        now = self.clock()
        for state in [
            s for s, f in self._flows.items() if now - f.started_at > FLOW_TTL_S
        ]:
            del self._flows[state]


pending = PendingFlows()
