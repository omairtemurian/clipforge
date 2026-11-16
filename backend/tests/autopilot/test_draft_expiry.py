"""Tests of the expiry of the autopilot's drafts (SPEC-v2 3.19,
clipforge.autopilot.safety.expire_drafts): pending and needs_fix drafts
expire after their campaign's draft_ttl_days, on Auto Import's tick, also
while every autopilot is paused. Fake clocks."""

from datetime import UTC, datetime, timedelta

from autopilot_fakes import turn_on
from clipforge.autopilot import safety
from clipforge.autopilot.rows import DraftRow
from clipforge.models import DraftStatus
from clipforge.watch.youtube_watcher import AutoImporter
from fake_clock import FakeWallClock
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, col, select
from submission_fakes import new_campaign

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)


def draft_statuses(engine: Engine) -> list[DraftStatus]:
    with Session(engine) as session:
        return list(session.exec(select(DraftRow.status).order_by(col(DraftRow.id))))


def add_draft(
    engine: Engine, campaign_id: int, status: DraftStatus, made: datetime
) -> None:
    clip_id = add_clip(engine, add_project(engine), "rendered", 70)
    with Session(engine) as session:
        session.add(
            DraftRow(
                clip_id=clip_id, campaign_id=campaign_id, status=status, created_at=made
            )
        )
        session.commit()


def test_waiting_drafts_expire_after_the_campaign_ttl(engine: Engine) -> None:
    short = new_campaign(engine)
    turn_on(engine, short.id, enabled=False, draft_ttl_days=1)
    default = new_campaign(engine)
    for status in ("pending", "needs_fix", "approved", "rejected"):
        add_draft(engine, short.id, status, NOW)
    add_draft(engine, default.id, "pending", NOW)

    assert safety.expire_drafts(engine, NOW + timedelta(hours=23)) == []
    assert safety.expire_drafts(engine, NOW + timedelta(days=1)) == [1, 2]
    assert draft_statuses(engine) == [
        "expired",
        "expired",
        "approved",
        "rejected",
        "pending",
    ]
    assert safety.expire_drafts(engine, NOW + timedelta(days=3)) == [5]


def test_auto_import_expires_drafts_on_its_tick_even_while_paused(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)
    add_draft(engine, campaign.id, "pending", NOW)
    safety.set_paused(engine, True, NOW)
    wall = FakeWallClock(NOW + timedelta(days=2))
    importer = AutoImporter(engine, wall_clock=wall)

    importer.tick()
    assert draft_statuses(engine) == ["pending"]
    wall.advance(days=1)
    importer.tick()

    assert draft_statuses(engine) == ["expired"]
