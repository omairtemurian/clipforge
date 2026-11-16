"""Helpers of the posting worker tests (tests only): queued posts of a
rendered clip, a worker on a fake wall clock with the ExampleTube publisher
(respx: nothing leaves the machine) and ExampleTube's answers."""

from datetime import UTC, datetime, timedelta

import httpx
import respx
from clipforge import posts
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import Publisher
from clipforge.scheduler.post_worker import PostWorker
from clipforge.scheduler.retry import RetryPolicy
from clipforge.token_store import TokenStore
from fake_clock import FakeWallClock
from social_fakes import ACCESS, CLIENT, VIDEOS_URL, ExamplePublisher, add_account
from sqlalchemy import Engine

START = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)
# Short backoff of the tests: 60 s, 120 s, 240 s, 240 s, ...; 6 uploads.
RETRY = RetryPolicy(6, timedelta(seconds=60), timedelta(seconds=240))


def connect(engine: Engine, store: TokenStore, external_id: str) -> int:
    """Connect a "tiktok" (ExampleTube) account with a token; its id."""
    account_id = add_account(engine, external_id)
    store.save(f"ref-{external_id}", Token(access_token=ACCESS))
    return account_id


def queue(
    engine: Engine, clip_id: int, account_id: int, at: datetime | None = None
) -> int:
    """Queue a post of clip_id to account_id for at (None: at once); its id."""
    draft = posts.create_post(
        engine, clip_id=clip_id, account_id=account_id, payload={"title": "Bit"}
    )
    return posts.queue_post(engine, draft.id, at).id


def example(_platform: str) -> Publisher:
    return ExamplePublisher(CLIENT)


def make_worker(
    engine: Engine,
    store: TokenStore,
    clock: FakeWallClock,
    retry: RetryPolicy = RETRY,
) -> PostWorker:
    """A worker on clock that publishes with ExampleTube."""
    return PostWorker(
        engine, store, interval=1.0, retry=retry, publisher_for=example, now=clock
    )


def answer_published(respx_mock: respx.MockRouter) -> respx.Route:
    """Make ExampleTube take every video (ids v1, v2, ...)."""
    counter = iter(range(1, 1000))

    def created(_request: httpx.Request) -> httpx.Response:
        number = next(counter)
        link = f"https://ex/v{number}"
        return httpx.Response(201, json={"id": f"v{number}", "link": link})

    return respx_mock.post(VIDEOS_URL).mock(side_effect=created)


def answer_busy(respx_mock: respx.MockRouter) -> respx.Route:
    """Make ExampleTube answer 503 (a retryable failure) to every upload."""
    return respx_mock.post(VIDEOS_URL).mock(return_value=httpx.Response(503))
