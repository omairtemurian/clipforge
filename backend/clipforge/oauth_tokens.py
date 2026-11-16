"""OAuth tokens (clipforge.oauth): the Token model and the token_ref that
names where clipforge.token_store keeps one (SocialAccount.token_ref,
SPEC-v2 4). Tokens never enter the database, logs or API responses: Token
leaves them out of its repr."""

import re
import secrets

from pydantic import BaseModel, Field

# An access token this close to its expiry is refreshed before use.
EXPIRY_MARGIN_S = 60.0
TOKEN_REF = re.compile(r"[A-Za-z0-9_-]{1,64}")


class Token(BaseModel):
    """A stored token; expires_at is in seconds since the epoch (None: the
    provider gave no lifetime)."""

    access_token: str = Field(repr=False)
    refresh_token: str | None = Field(default=None, repr=False)
    expires_at: float | None = None
    scope: str = ""
    token_type: str = "Bearer"

    def expired(self, now: float) -> bool:
        """Return True if the access token expires within EXPIRY_MARGIN_S."""
        return self.expires_at is not None and now >= self.expires_at - EXPIRY_MARGIN_S


def check_ref(token_ref: str) -> str:
    """Return token_ref; ValueError unless it is 1-64 of [A-Za-z0-9_-]
    (it names a file)."""
    if not TOKEN_REF.fullmatch(token_ref):
        raise ValueError(f"invalid token_ref {token_ref!r}")
    return token_ref


def new_token_ref() -> str:
    """Return a new random token_ref (for accounts that have no fixed one)."""
    return secrets.token_hex(16)
