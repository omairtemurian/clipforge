"""Tests of the daily digest (clipforge.autopilot.digest, SPEC-v2 3.19): once
a day, from the configured time, a notification with the drafts waiting, the
posts scheduled today, the submissions still to do and the earnings estimated
for yesterday; nothing to tell, no digest. Fake clocks, Europe/Zurich days."""

import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from clipforge import config, notifications, submissions
from clipforge.autopilot import digest
from clipforge.autopilot.rows import DraftRow
from clipforge.models import DraftStatus, SubmissionPatch
from clipforge.submission_rows import SubmissionRow
from clipforge.watch.youtube_watcher import AutoImporter
from fake_clock import FakeWallClock
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session
from submission_fakes import T0, account, campaign_clip, new_campaign, publish

ZURICH = ZoneInfo("Europe/Zurich")
# 2030-01-15: 09:00 UTC is 10:00 in Zurich, after the default 08:00.
NOW = T0
YESTERDAY_NOON = datetime(2030, 1, 14, 11, 0, tzinfo=UTC)


def add_draft(
    engine: Engine, campaign_id: int, status: DraftStatus = "pending"
) -> None:
    clip_id = add_clip(engine, add_project(engine), "rendered", 70)
    with Session(engine) as session:
        session.add(
            DraftRow(
                clip_id=clip_id, campaign_id=campaign_id, status=status, created_at=NOW
            )
        )
        session.commit()


def published_post(engine: Engine, campaign_id: int, hour: int = 1) -> int:
    """Publish a new clip of the campaign at T0 + hour; its submission id."""
    clip_id = campaign_clip(engine, campaign_id)
    post_id = publish(engine, clip_id, account(engine, name=str(clip_id)), hour=hour)
    (found,) = [s for s in submissions.list_submissions(engine) if s.post_id == post_id]
    return found.id


def answer(engine: Engine, submission_id: int, views: int, at: datetime) -> None:
    """Make the submission approved with views, answered at at."""
    with Session(engine) as session:
        row = session.get(SubmissionRow, submission_id)
        assert row is not None
        row.status = "approved"
        row.approved_views = views
        row.answered_at = at
        session.commit()


def test_the_digest_counts_what_waits_what_is_scheduled_and_what_was_earned(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine, rate_per_1k_usd=1.5)
    add_draft(engine, campaign.id)
    add_draft(engine, campaign.id, "pending")
    add_draft(engine, campaign.id, "needs_fix")
    add_draft(engine, campaign.id, "rejected")
    published_post(engine, campaign.id)
    ticked = published_post(engine, campaign.id, hour=30)
    earned = published_post(engine, campaign.id, hour=2)
    answer(engine, earned, 2000, YESTERDAY_NOON)
    submissions.update_submission(engine, ticked, SubmissionPatch(status="submitted"))

    result = digest.build(engine, NOW, ZURICH)

    assert result == digest.Digest(
        drafts_waiting=2,
        posts_today=2,
        submissions_pending=1,
        earnings_yesterday=3.0,
    )


def test_earnings_are_only_those_answered_yesterday_of_a_campaign_with_a_rate(
    engine: Engine,
) -> None:
    paid = new_campaign(engine, rate_per_1k_usd=2.0)
    unpaid = new_campaign(engine, name="No rate", rate_per_1k_usd=None)
    first = published_post(engine, paid.id, hour=1)
    old = published_post(engine, paid.id, hour=2)
    today = published_post(engine, paid.id, hour=3)
    norate = published_post(engine, unpaid.id, hour=4)
    answer(engine, first, 500, YESTERDAY_NOON)
    answer(engine, old, 9000, YESTERDAY_NOON - timedelta(days=1))
    answer(engine, today, 9000, NOW)
    answer(engine, norate, 9000, YESTERDAY_NOON)

    assert digest.build(engine, NOW, ZURICH).earnings_yesterday == 1.0


def test_the_days_are_those_of_the_timezone(engine: Engine) -> None:
    campaign = new_campaign(engine)
    sub = published_post(engine, campaign.id)
    # 23:30 UTC on the 14th is 00:30 on the 15th in Zurich: not yesterday.
    answer(engine, sub, 1000, datetime(2030, 1, 14, 23, 30, tzinfo=UTC))

    assert digest.build(engine, NOW, ZURICH).earnings_yesterday == 0.0
    assert digest.build(engine, NOW, UTC).earnings_yesterday == 1.5


def test_describe_lists_every_number_and_labels_the_earnings_as_an_estimate() -> None:
    title, body = digest.describe(digest.Digest(3, 2, 1, 4.5))

    assert title == "3 drafts waiting for you"
    assert body.splitlines() == [
        "Drafts waiting for approval: 3",
        "Posts scheduled today: 2",
        "Submissions still to do: 1",
        "Estimated earnings yesterday: $4.50 (estimate)",
    ]


def test_the_digest_comes_at_the_configured_time_once_a_day(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.settings, "digest_time", "09:30")
    campaign = new_campaign(engine)
    add_draft(engine, campaign.id)
    # 08:29 UTC is 09:29 in Zurich.
    early = datetime(2030, 1, 15, 8, 29, tzinfo=UTC)

    assert digest.send_due(engine, early, ZURICH) is None
    sent = digest.send_due(engine, early + timedelta(minutes=1), ZURICH)
    again = digest.send_due(engine, early + timedelta(hours=5), ZURICH)
    next_day = digest.send_due(engine, early + timedelta(days=1, minutes=1), ZURICH)

    assert sent is not None
    assert (sent.kind, sent.title, sent.link) == (
        "digest",
        "1 draft waiting for you",
        "/inbox",
    )
    assert "Drafts waiting for approval: 1" in sent.body
    assert again is None
    assert next_day is not None and next_day.id != sent.id
    assert len(notifications.list_notifications(engine).items) == 2


def test_no_digest_without_a_time_or_without_news(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert digest.send_due(engine, NOW, ZURICH) is None
    monkeypatch.setattr(config.settings, "digest_time", "")
    campaign = new_campaign(engine)
    add_draft(engine, campaign.id)

    assert digest.send_due(engine, NOW, ZURICH) is None
    assert notifications.list_notifications(engine).items == []


def test_auto_import_sends_the_digest_on_its_tick_and_survives_its_failure(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TZ", "Europe/Zurich")
    time.tzset()
    campaign = new_campaign(engine)
    add_draft(engine, campaign.id)
    wall = FakeWallClock(NOW)
    importer = AutoImporter(engine, wall_clock=wall)

    importer.tick()
    importer.tick()

    (note,) = notifications.list_notifications(engine).items
    assert note.kind == "digest"

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("no digest today")

    monkeypatch.setattr(digest, "send_due", broken)
    wall.advance(days=1)
    assert importer.tick() == []
    monkeypatch.undo()
    time.tzset()


def test_the_board_answer_or_numbers_stamp_answered_at(engine: Engine) -> None:
    campaign = new_campaign(engine)
    sub = published_post(engine, campaign.id)

    def answered_at() -> datetime | None:
        return submissions.get_submission(engine, sub).answered_at

    submissions.update_submission(engine, sub, SubmissionPatch(status="submitted"))
    assert answered_at() is None
    submissions.update_submission(engine, sub, SubmissionPatch(status="approved"))
    first = answered_at()
    assert first is not None
    submissions.update_submission(engine, sub, SubmissionPatch(notes="fine"))
    assert answered_at() == first
    submissions.update_submission(engine, sub, SubmissionPatch(approved_views=10))
    assert answered_at() is not None and answered_at() >= first  # type: ignore[operator]
    submissions.update_submission(engine, sub, SubmissionPatch(status="submitted"))
    assert answered_at() is None
