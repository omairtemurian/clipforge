"""What every social publisher implements (SPEC-v2 3.10).

A Publisher wraps one platform's official API for the owner's OAuth app
(OAuthClient: endpoints, client id/secret, scopes):

- finish_sign_in(token): the token to keep after the code exchange (e.g.
  Meta's long-lived token); by default the exchanged token itself.
- fetch_account(token): who signed in (external id, display name) and the
  platform's restrictions on the account or app, right after the OAuth
  callback traded the code for token.
- upload(session, upload): publish one post's rendered video (and
  thumbnail) as the account whose token the OAuthSession uses (its id on
  the platform is upload.account_external_id); returns the
  platform's post id and link, or raises PublishError (retryable for
  passing failures such as rate limits and 5xx answers).

The publish run (clipforge.publishers.publish) moves the post through its
states around upload(); publishers never touch the database.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import httpx

from clipforge.models import Clip, Post, SocialPlatform
from clipforge.oauth import TIMEOUT, Clock, OAuthClient, OAuthSession
from clipforge.oauth_tokens import Token
from clipforge.token_store import TokenStore


@dataclass(frozen=True)
class AccountProfile:
    """The signed-in account: its id on the platform, the name shown for
    it, the platform's restrictions on it (shown in the UI) and its picture's
    link, if the platform gave one."""

    external_id: str
    display_name: str
    restrictions: tuple[str, ...] = ()
    avatar_url: str | None = None


@dataclass(frozen=True)
class Upload:
    """What a publisher posts: the post (payload, scheduled_at), its clip,
    the clip's rendered video, the thumbnail file, if any, and the id on
    the platform of the account that posts it."""

    post: Post
    clip: Clip
    video: Path
    thumbnail: Path | None
    account_external_id: str | None = None


@dataclass(frozen=True)
class PublishResult:
    """A published post: the platform's id of it and its public link."""

    external_post_id: str
    url: str | None


def hashtag_line(tags: list[str]) -> str:
    """Return tags as one line of "#tag" words (blank tags left out)."""
    return " ".join(f"#{tag.lstrip('#')}" for tag in tags if tag.strip("# "))


def clip_caption(clip: Clip) -> str:
    """Return the clip's default post caption: its title followed by its
    hashtags."""
    hashtags = hashtag_line(clip.hashtags)
    return "\n\n".join(part for part in (clip.title.strip(), hashtags) if part)


class PublishError(Exception):
    """The platform refused or failed a request. retryable: trying again
    later may work (rate limit, quota reset, 5xx, network)."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class Publisher(ABC):
    """One platform's publisher for the owner's OAuth app. transport and
    clock replace the network and the time in tests."""

    platform: ClassVar[SocialPlatform]

    def __init__(
        self,
        client: OAuthClient,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock = time.time,
    ) -> None:
        self.client = client
        self.transport = transport
        self.clock = clock

    def finish_sign_in(self, token: Token) -> Token:
        """Return the token to store for the account that just signed in
        (the exchanged token, unless the platform trades it for another)."""
        return token

    @abstractmethod
    def fetch_account(self, token: Token) -> AccountProfile:
        """Return the account that token belongs to; PublishError if the
        platform does not say."""

    @abstractmethod
    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """Publish upload as the session's account; PublishError on
        failure."""

    def session(self, store: TokenStore, token_ref: str) -> OAuthSession:
        """Return a session that sends requests as the account of token_ref
        (refreshing its token when needed)."""
        return OAuthSession(
            self.client, store, token_ref, clock=self.clock, transport=self.transport
        )

    def http(self) -> httpx.Client:
        """Return an HTTP client for requests outside an OAuthSession (e.g.
        fetch_account with a fresh token)."""
        return httpx.Client(transport=self.transport, timeout=TIMEOUT)
