"""Tests for the 60 s polling of the watched YouTube channels
(clipforge.watch.youtube_watcher.AutoImporter.tick) on a fake clock: each
feed is read about every 60 s with jitter, conditionally (304: unchanged),
backed off after errors and every 15 min once the hub pushes; a new upload
becomes a top-priority project within one cycle, with its published and
detected times; a video both pushed and polled is imported once. respx
answers with the recorded feeds."""

import random
import threading
from datetime import timedelta

import httpx
import pytest
import respx
from clipforge.auto_import import add_channel, list_channels, set_channel_fields
from clipforge.db import JobRow
from clipforge.jobs import TOP_PRIORITY
from clipforge.models import WatchedChannel, WatchedChannelCreate
from clipforge.watch import websub
from clipforge.watch.events import list_events
from clipforge.watch.youtube_watcher import AutoImporter
from fake_clock import FakeClock
from sqlalchemy import Engine
from sqlmodel import Session, select
from watch_fakes import NEWEST_PUBLISHED, PUSH_NEWEST, WallClock, hub_signature
from youtube_fakes import CHANNEL, NEWEST, feed_response, feed_route


@pytest.fixture
def channel(engine: Engine) -> WatchedChannel:
    return add_channel(engine, WatchedChannelCreate(channel=CHANNEL))


@pytest.fixture
def pushed_channel(engine: Engine, channel: WatchedChannel) -> WatchedChannel:
    """The channel, added a day before the newest upload."""
    added = NEWEST_PUBLISHED - timedelta(days=1)
    set_channel_fields(engine, channel.id, created_at=added)
    return channel.model_copy(update={"created_at": added})


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def _importer(engine: Engine, clock: FakeClock, **kwargs: object) -> AutoImporter:
    wall = WallClock(clock, NEWEST_PUBLISHED - timedelta(seconds=20))
    return AutoImporter(
        engine,
        interval=60.0,
        clock=clock,
        rng=random.Random(3),
        wall_clock=wall,
        **kwargs,  # type: ignore[arg-type]
    )


def test_each_feed_is_read_about_every_60_seconds(
    engine: Engine,
    respx_mock: respx.MockRouter,
    channel: WatchedChannel,
    clock: FakeClock,
) -> None:
    route = feed_route(respx_mock)
    route.side_effect = lambda _: feed_response("feed_before")
    importer = _importer(engine, clock)
    reads = []
    for _ in range(6000):  # 10 minutes in 0.1 s ticks
        importer.tick()
        if route.call_count > len(reads):
            reads.append(clock.now)
        clock.now += 0.1

    gaps = [later - earlier for earlier, later in zip(reads, reads[1:], strict=False)]
    assert len(reads) >= 9
    assert all(54.0 <= gap <= 66.2 for gap in gaps)


def test_a_new_upload_is_a_top_priority_project_within_one_cycle(
    engine: Engine,
    respx_mock: respx.MockRouter,
    channel: WatchedChannel,
    clock: FakeClock,
) -> None:
    feed_route(respx_mock, "feed_before", "feed_after")
    woken: list[bool] = []
    importer = _importer(engine, clock, on_import=lambda: woken.append(True))
    importer.tick()  # 20 s before the upload: records the feed

    clock.now = importer.schedule.next_due(CHANNEL)
    (project_id,) = importer.tick()

    with Session(engine) as session:
        (job,) = session.exec(select(JobRow)).all()
    assert (job.project_id, job.priority) == (project_id, TOP_PRIORITY)
    (event,) = list_events(engine)
    assert (event.platform, event.kind, event.external_id) == (
        "youtube",
        "upload",
        NEWEST,
    )
    assert (event.project_id, event.via, event.source_name) == (
        project_id,
        "poll",
        "YouTube",
    )
    assert event.published_at == NEWEST_PUBLISHED
    delay = event.detected_at - NEWEST_PUBLISHED
    assert timedelta(0) < delay <= timedelta(seconds=66)
    assert woken == [True]


def test_the_feed_is_read_conditionally_and_304_means_unchanged(
    engine: Engine,
    respx_mock: respx.MockRouter,
    channel: WatchedChannel,
    clock: FakeClock,
) -> None:
    tagged = feed_response("feed_before")
    tagged.headers["ETag"] = '"v1"'
    changed = feed_response("feed_after")
    changed.headers["ETag"] = '"v2"'
    route = feed_route(respx_mock, tagged, httpx.Response(304), changed)
    importer = _importer(engine, clock)
    importer.tick()
    first_checked = list_channels(engine)[0].last_checked_at

    clock.now = importer.schedule.next_due(CHANNEL)
    assert importer.tick() == []
    assert route.calls.last.request.headers["if-none-match"] == '"v1"'
    (unchanged,) = list_channels(engine)
    assert unchanged.last_checked_at is not None and first_checked is not None
    assert unchanged.last_checked_at > first_checked

    clock.now = importer.schedule.next_due(CHANNEL)
    assert len(importer.tick()) == 1
    assert route.calls.last.request.headers["if-none-match"] == '"v1"'
    assert importer.schedule.validators(CHANNEL).etag == '"v2"'


def test_feed_errors_back_off_and_a_read_that_works_resets_the_pace(
    engine: Engine,
    respx_mock: respx.MockRouter,
    channel: WatchedChannel,
    clock: FakeClock,
) -> None:
    errors = [httpx.Response(500)] * 3
    route = feed_route(respx_mock, *errors, "feed_before", "feed_before")
    importer = _importer(engine, clock)
    delays = []
    for _ in range(4):
        importer.tick()
        delays.append(importer.schedule.next_due(CHANNEL) - clock.now)
        clock.now += 1
        importer.tick()  # not due yet: no request
        clock.now = importer.schedule.next_due(CHANNEL)

    assert route.call_count == 4
    for delay, base in zip(delays, [120, 240, 480, 60], strict=True):
        assert base * 0.9 <= delay <= base * 1.1
    (ok,) = list_channels(engine)
    assert ok.last_error is None


def test_a_channel_the_hub_pushes_is_polled_every_15_minutes(
    engine: Engine,
    respx_mock: respx.MockRouter,
    channel: WatchedChannel,
    clock: FakeClock,
) -> None:
    feed_route(respx_mock, "feed_before")
    importer = _importer(engine, clock)
    lease_end = importer.wall_clock() + timedelta(days=9)
    set_channel_fields(
        engine,
        channel.id,
        push_state="subscribed",
        push_lease_expires_at=lease_end,
        push_requested_at=importer.wall_clock(),
    )

    importer.tick()

    assert 810.0 <= importer.schedule.next_due(CHANNEL) - clock.now <= 990.0


def test_a_video_pushed_and_polled_at_once_is_imported_once(
    engine: Engine,
    respx_mock: respx.MockRouter,
    pushed_channel: WatchedChannel,
    clock: FakeClock,
) -> None:
    feed_route(respx_mock, "feed_before", *["feed_after"] * 4)
    importer = _importer(engine, clock)
    importer.poll()
    signature = hub_signature(websub.topic_secret(CHANNEL), PUSH_NEWEST)
    start = threading.Barrier(2)
    results: list[list[int]] = []

    def push() -> None:
        start.wait()
        answer = importer.receive_push(CHANNEL, PUSH_NEWEST, signature)
        results.append(list(answer.imported))

    def poll() -> None:
        start.wait()
        results.append(importer.poll())

    threads = [threading.Thread(target=push), threading.Thread(target=poll)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert sorted(len(ids) for ids in results) == [0, 1]
    assert importer.poll() == []
    assert importer.receive_push(CHANNEL, PUSH_NEWEST, signature).imported == ()
    with Session(engine) as session:
        assert len(session.exec(select(JobRow)).all()) == 1
    assert [e.external_id for e in list_events(engine)] == [NEWEST]
