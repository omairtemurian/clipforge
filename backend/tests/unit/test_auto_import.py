"""Tests for Auto Import (clipforge.auto_import): the first read records
the feed, new videos become projects once with the channel's defaults,
feed errors, disabled channels, usage caps and the thread (the polling
cadence is in test_watch_polling.py).
respx answers with recorded feeds instead of YouTube."""

import threading
from datetime import UTC, datetime

import httpx
import pytest
import respx
from clipforge import config, usage
from clipforge.auto_import import (
    ChannelExists,
    add_channel,
    channel_videos,
    list_channels,
)
from clipforge.channel_rows import WatchedChannelRow
from clipforge.config import Settings
from clipforge.db import JobRow, ProjectRow
from clipforge.models import ProcessingSettings, WatchedChannel, WatchedChannelCreate
from clipforge.watch.youtube_watcher import AutoImporter
from sqlalchemy import Engine
from sqlmodel import Session, select
from youtube_fakes import (
    CHANNEL,
    MIDDLE,
    NEWEST,
    OLDEST,
    feed_response,
    feed_route,
)

DEFAULTS = ProcessingSettings(genre="comedy", num_clips=3, aspect="1:1")


@pytest.fixture
def channel(engine: Engine) -> WatchedChannel:
    return add_channel(
        engine,
        WatchedChannelCreate(
            channel=f"https://www.youtube.com/channel/{CHANNEL}",
            settings=DEFAULTS,
            source_rights="permission",
            credit_line="Video by YouTube",
            auto_schedule_drafts=True,
        ),
    )


def _projects(engine: Engine) -> list[ProjectRow]:
    with Session(engine) as session:
        return list(session.exec(select(ProjectRow).order_by(ProjectRow.id)))


def _watch_ids(projects: list[ProjectRow]) -> list[str]:
    return [(p.source_url or "").rsplit("=", 1)[-1] for p in projects]


def test_add_channel_stores_the_defaults(
    engine: Engine, channel: WatchedChannel
) -> None:
    assert list_channels(engine) == [channel]
    assert channel.channel_id == CHANNEL
    assert channel.settings == DEFAULTS
    assert (channel.source_rights, channel.credit_line) == (
        "permission",
        "Video by YouTube",
    )
    assert channel.auto_schedule_drafts is True and channel.enabled is True
    assert (channel.title, channel.last_checked_at, channel.last_error) == (
        "",
        None,
        None,
    )

    with pytest.raises(ChannelExists):
        add_channel(engine, WatchedChannelCreate(channel=CHANNEL))


@pytest.mark.parametrize(
    "ref",
    [
        CHANNEL,
        f" https://youtube.com/channel/{CHANNEL}/videos ",
        f"https://m.youtube.com/channel/{CHANNEL}",
        f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}",
    ],
)
def test_a_channel_is_given_by_id_or_link(ref: str) -> None:
    assert WatchedChannelCreate(channel=ref).channel == CHANNEL


@pytest.mark.parametrize(
    "ref",
    ["@x", "UCshort", f"https://example.com/channel/{CHANNEL}", f"x{CHANNEL}"],
)
def test_other_channel_refs_are_refused(ref: str) -> None:
    with pytest.raises(ValueError, match="YouTube channel id"):
        WatchedChannelCreate(channel=ref)


def test_the_first_read_records_the_feed_without_importing(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    feed_route(respx_mock, "feed_before")

    assert AutoImporter(engine).poll() == []

    assert _projects(engine) == []
    videos = channel_videos(engine, channel.id)
    assert {(v.video_id, v.project_id) for v in videos} == {
        (MIDDLE, None),
        (OLDEST, None),
    }
    (checked,) = list_channels(engine)
    assert checked.title == "YouTube" and checked.last_checked_at is not None


def test_a_new_video_becomes_a_project_once(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    feed_route(respx_mock, "feed_before", "feed_after", "feed_after", "feed_before")
    importer = AutoImporter(engine)
    importer.poll()

    (project_id,) = importer.poll()
    assert importer.poll() == [] and importer.poll() == []

    (project,) = _projects(engine)
    assert project.id == project_id
    assert project.source_url == f"https://www.youtube.com/watch?v={NEWEST}"
    assert project.settings == DEFAULTS
    assert (project.source_rights, project.credit_line) == (
        "permission",
        "Video by YouTube",
    )
    with Session(engine) as session:
        (job,) = session.exec(select(JobRow)).all()
    assert (job.kind, job.status, job.project_id) == ("process", "queued", project_id)
    newest = channel_videos(engine, channel.id)[0]
    assert (newest.video_id, newest.project_id) == (NEWEST, project_id)
    assert newest.published_at is not None


def test_a_deleted_project_is_not_imported_again(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    feed_route(respx_mock, "feed_before", "feed_after", "feed_after")
    importer = AutoImporter(engine)
    importer.poll()
    (project_id,) = importer.poll()
    with Session(engine) as session:
        for job in session.exec(select(JobRow).where(JobRow.project_id == project_id)):
            session.delete(job)
        session.delete(session.get(ProjectRow, project_id))
        session.commit()

    assert importer.poll() == []


def test_new_videos_of_an_empty_channel_are_imported_oldest_first(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    feed_route(respx_mock, "feed_empty", "feed_after")
    importer = AutoImporter(engine)
    importer.poll()

    assert len(importer.poll()) == 3
    assert _watch_ids(_projects(engine)) == [OLDEST, MIDDLE, NEWEST]


def test_a_feed_error_is_kept_and_retried(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    feed_route(respx_mock, httpx.Response(500), "feed_before", httpx.ConnectError("x"))
    importer = AutoImporter(engine)

    assert importer.poll() == []
    (failed,) = list_channels(engine)
    assert failed.last_error == "the channel feed answered HTTP 500"
    assert failed.last_checked_at is None

    importer.poll()  # the first read that works only records the feed
    assert _projects(engine) == []
    (ok,) = list_channels(engine)
    assert ok.last_error is None and ok.last_checked_at is not None

    importer.poll()
    (offline,) = list_channels(engine)
    assert offline.last_error is not None and "could not read" in offline.last_error
    assert offline.last_checked_at == ok.last_checked_at


def test_a_disabled_channel_is_not_read(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    route = feed_route(respx_mock, "feed_before")
    with Session(engine) as session:
        row = session.get(WatchedChannelRow, channel.id)
        assert row is not None
        row.enabled = False
        session.add(row)
        session.commit()

    assert AutoImporter(engine).poll() == []
    assert route.call_count == 0


def test_nothing_is_imported_while_a_usage_cap_is_used_up(
    engine: Engine,
    respx_mock: respx.MockRouter,
    channel: WatchedChannel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_route(respx_mock, "feed_before", "feed_after", "feed_after")
    importer = AutoImporter(engine)
    importer.poll()
    capped = config.settings.model_copy(update={"usage_cap_llm_tokens": 100})
    monkeypatch.setattr(config, "settings", capped)
    usage.record(engine, usage.LLM_TOKENS, 500, at=datetime.now(UTC))

    assert importer.poll() == []
    assert _projects(engine) == []
    assert NEWEST not in {v.video_id for v in channel_videos(engine, channel.id)}

    monkeypatch.setattr(config, "settings", Settings())
    assert len(importer.poll()) == 1


def test_from_settings_uses_the_poll_interval(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    importer = AutoImporter.from_settings(engine)
    assert (importer.interval, importer.public_url) == (60, "")
    settings = Settings(
        auto_import_poll_s=42.5, public_callback_url="https://watch.example.com"
    )
    monkeypatch.setattr(config, "settings", settings)
    importer = AutoImporter.from_settings(engine)
    assert (importer.interval, importer.public_url) == (
        42.5,
        settings.public_callback_url,
    )
    with pytest.raises(ValueError, match="greater than or equal to 30"):
        Settings(auto_import_poll_s=10)


def test_the_thread_imports_a_new_video_and_stops(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    route = feed_route(respx_mock)
    reads: list[int] = []

    def answer(_: httpx.Request) -> httpx.Response:
        reads.append(1)
        return feed_response("feed_after" if len(reads) > 1 else "feed_before")

    route.side_effect = answer
    woken = threading.Event()
    importer = AutoImporter(engine, interval=0.05, on_import=woken.set)

    importer.start()
    try:
        assert woken.wait(10)
    finally:
        importer.stop(5)

    assert route.call_count >= 2
    assert _watch_ids(_projects(engine)) == [NEWEST]
    with pytest.raises(RuntimeError, match="already started"):
        importer.start()
        importer.start()
    importer.stop(5)
