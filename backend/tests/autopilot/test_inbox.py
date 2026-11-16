"""Tests of the Approval Inbox (SPEC-v2 3.19, clipforge.autopilot.inbox):
drafts made of campaign clips, review notes, the owner's decisions with
their feedback, and where an approved draft's posts go. Fake clocks."""

from datetime import UTC, datetime, timedelta

import pytest
from autopilot_fakes import turn_on
from campaign_api import in_campaign
from clipforge import campaign_accounts
from clipforge.autopilot import inbox
from clipforge.autopilot.rows import FeedbackEventRow
from clipforge.models import DRAFT_NOTES_MAX, DraftApprove, ScheduleRules
from draft_fakes import SLOTS, add_draft, inbox_with_draft, postable_campaign
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, col, select
from submission_fakes import account, campaign_clip, new_campaign

NOW = datetime(2030, 1, 10, 12, 0, tzinfo=UTC)


def feedback(engine: Engine) -> list[tuple[int | None, str, str | None]]:
    with Session(engine) as session:
        events = session.exec(
            select(FeedbackEventRow).order_by(col(FeedbackEventRow.id))
        ).all()
        return [(e.clip_id, e.action, e.reason) for e in events]


def test_a_clip_that_passes_the_rules_becomes_a_pending_draft(engine: Engine) -> None:
    campaign_id = postable_campaign(engine)
    clip_id = campaign_clip(engine, campaign_id)

    draft = inbox.create_draft(engine, clip_id, NOW)

    assert (draft.clip_id, draft.campaign_id) == (clip_id, campaign_id)
    assert (draft.status, draft.created_at, draft.notes) == ("pending", NOW, [])
    assert all(result.passed for result in draft.rule_results)


def test_a_clip_that_fails_a_rule_needs_a_fix(engine: Engine) -> None:
    campaign = new_campaign(engine)
    draft = inbox.create_draft(engine, campaign_clip(engine, campaign.id))

    assert draft.status == "needs_fix"
    failed = {r.rule for r in draft.rule_results if not r.passed}
    assert {"permission", "hashtags", "credit_line"} <= failed


def test_a_clip_has_one_draft_and_must_be_in_a_campaign(engine: Engine) -> None:
    campaign_id = postable_campaign(engine)
    clip_id = campaign_clip(engine, campaign_id)
    inbox.create_draft(engine, clip_id)
    loose = add_clip(engine, add_project(engine), "rendered", 70)

    with pytest.raises(inbox.DraftExists):
        inbox.create_draft(engine, clip_id)
    with pytest.raises(inbox.NotInCampaign):
        inbox.create_draft(engine, loose)
    with pytest.raises(inbox.ClipNotFound):
        inbox.create_draft(engine, 999)
    assert len(inbox.list_drafts(engine)) == 1


def test_the_inbox_lists_newest_first_filters_and_expires(engine: Engine) -> None:
    first = postable_campaign(engine)
    second = postable_campaign(engine, name="Other")
    old = inbox.create_draft(engine, campaign_clip(engine, first), NOW - timedelta(3))
    mine = inbox.create_draft(engine, campaign_clip(engine, first), NOW)
    other = inbox.create_draft(engine, campaign_clip(engine, second), NOW)

    listed = inbox.list_drafts(engine, now=NOW)
    pending = inbox.list_drafts(engine, "pending", first, now=NOW)

    assert [d.id for d in listed] == [other.id, mine.id, old.id]
    assert [d.status for d in listed] == ["pending", "pending", "expired"]
    assert [d.id for d in pending] == [mine.id]


def test_notes_are_kept_in_order_with_their_author(engine: Engine) -> None:
    draft_id = inbox_with_draft(engine).draft_id

    inbox.add_note(engine, draft_id, "Hook is weak", "agent", NOW)
    draft = inbox.add_note(engine, draft_id, "Fine by me", "owner", NOW)

    assert [(n.text, n.by, n.at) for n in draft.notes] == [
        ("Hook is weak", "agent", NOW),
        ("Fine by me", "owner", NOW),
    ]
    assert inbox.get_draft(engine, draft_id).notes == draft.notes


def test_a_draft_takes_a_limited_number_of_notes(engine: Engine) -> None:
    draft_id = inbox_with_draft(engine).draft_id
    for n in range(DRAFT_NOTES_MAX):
        inbox.add_note(engine, draft_id, f"note {n}", "agent")

    with pytest.raises(inbox.TooManyNotes):
        inbox.add_note(engine, draft_id, "one more", "agent")
    with pytest.raises(inbox.DraftNotFound):
        inbox.add_note(engine, 999, "x", "owner")


def test_rejecting_records_the_reason_once(engine: Engine) -> None:
    setup = inbox_with_draft(engine)
    now = datetime.now(UTC)

    draft = inbox.reject(engine, setup.draft_id, "bad_crop", now)

    assert (draft.status, draft.reject_reason, draft.decided_at) == (
        "rejected",
        "bad_crop",
        now,
    )
    assert feedback(engine) == [(setup.clip_id, "rejected", "bad_crop")]
    with pytest.raises(inbox.DraftDecided):
        inbox.reject(engine, setup.draft_id, None)
    assert len(feedback(engine)) == 1


def test_approving_records_the_decision(engine: Engine) -> None:
    setup = inbox_with_draft(engine)

    (draft,) = inbox.mark_approved(engine, [setup.draft_id], NOW)

    assert (draft.status, draft.decided_at) == ("approved", NOW)
    assert feedback(engine) == [(setup.clip_id, "approved", None)]
    with pytest.raises(inbox.DraftDecided):
        inbox.waiting_draft(engine, setup.draft_id)


def test_the_plan_uses_the_autopilot_accounts_and_slots(engine: Engine) -> None:
    setup = inbox_with_draft(engine, max_posts_per_day=2)

    plan = inbox.approval_plan(
        engine, setup.campaign_id, [setup.clip_id], DraftApprove()
    )

    assert plan.queue is True
    assert plan.clip_ids == [setup.clip_id]
    assert [t.account_id for t in plan.targets] == [setup.account_id]
    assert plan.rules == ScheduleRules.model_validate(SLOTS | {"posts_per_day": 2})


def test_the_owners_rules_are_capped_at_the_daily_limit(engine: Engine) -> None:
    setup = inbox_with_draft(engine, max_posts_per_day=1, slots=None)
    rules = ScheduleRules(timezone="UTC", times=["08:00", "12:00", "20:00"])

    plan = inbox.approval_plan(
        engine, setup.campaign_id, [setup.clip_id], DraftApprove(rules=rules)
    )

    assert plan.rules.daily_times() == rules.times[:1]


def test_without_autopilot_accounts_the_campaigns_accounts_are_used(
    engine: Engine,
) -> None:
    campaign_id = postable_campaign(engine)
    turn_on(engine, campaign_id, slots=SLOTS)
    youtube = account(engine, "youtube", "second")
    campaign_accounts.set_accounts(engine, campaign_id, [youtube])

    plan = inbox.approval_plan(engine, campaign_id, [1], DraftApprove())

    assert [t.account_id for t in plan.targets] == [youtube]


def test_a_plan_needs_slots_and_accounts(engine: Engine) -> None:
    campaign_id = postable_campaign(engine)
    turn_on(engine, campaign_id)

    with pytest.raises(inbox.NoSlots):
        inbox.approval_plan(engine, campaign_id, [1], DraftApprove())
    with pytest.raises(campaign_accounts.NoCampaignAccounts):
        inbox.approval_plan(
            engine, campaign_id, [1], DraftApprove(rules=ScheduleRules(**SLOTS))
        )


def test_pending_drafts_of_a_campaign_are_oldest_first(engine: Engine) -> None:
    setup = inbox_with_draft(engine)
    later = add_draft(engine, setup.campaign_id, "Later")
    inbox.reject(engine, add_draft(engine, setup.campaign_id), None)
    elsewhere = postable_campaign(engine, name="Other")
    inbox.create_draft(
        engine, add_clip(engine, in_campaign(engine, elsewhere), "rendered", 70)
    )

    pending = inbox.pending_drafts(engine, setup.campaign_id)

    assert [d.id for d in pending] == [setup.draft_id, later]
