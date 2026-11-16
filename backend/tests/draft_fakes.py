"""Helpers of the Approval Inbox tests (tests only): a campaign that may be
posted to (permission evidence, YouTube allowed), its autopilot on with an
account and slots, and a rendered campaign clip with a pending draft."""

from dataclasses import dataclass
from typing import Any

from autopilot_fakes import turn_on
from campaign_api import PERMISSION_URL, PNG
from clipforge import campaigns
from clipforge.autopilot import inbox
from clipforge.models import CampaignCreate
from sqlalchemy import Engine
from submission_fakes import account, campaign_clip

SLOTS: dict[str, Any] = {
    "timezone": "Europe/Zurich",
    "times": ["09:00", "18:00"],
    "start_date": "2030-01-14",
}


@dataclass(frozen=True)
class Inbox:
    """A postable campaign, the YouTube account of its autopilot and one
    pending draft (of clip clip_id)."""

    campaign_id: int
    account_id: int
    clip_id: int
    draft_id: int


def postable_campaign(engine: Engine, **fields: Any) -> int:
    """Add an active campaign with complete permission evidence that allows
    YouTube and has no other rules; its id."""
    data = {
        "name": "Pizza Clips",
        "permission_source_url": PERMISSION_URL,
        "allowed_platforms": ["youtube"],
    } | fields
    created = campaigns.create_campaign(engine, CampaignCreate.model_validate(data))
    campaigns.set_permission_screenshot(engine, created.id, PNG, ".png")
    return created.id


def inbox_with_draft(engine: Engine, **autopilot: Any) -> Inbox:
    """A postable campaign whose autopilot is on (a YouTube account, SLOTS,
    then autopilot's fields) with one pending draft of a rendered clip."""
    campaign_id = postable_campaign(engine)
    account_id = account(engine, "youtube")
    turn_on(
        engine,
        campaign_id,
        **{"account_ids": [account_id], "slots": SLOTS} | autopilot,
    )
    clip_id = campaign_clip(engine, campaign_id)
    draft = inbox.create_draft(engine, clip_id)
    assert draft.status == "pending", draft.rule_results
    return Inbox(campaign_id, account_id, clip_id, draft.id)


def add_draft(engine: Engine, campaign_id: int, title: str = "Clip") -> int:
    """Add a rendered clip of the campaign with a draft; the draft's id."""
    return inbox.create_draft(engine, campaign_clip(engine, campaign_id, title)).id
