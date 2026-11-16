"""The accounts that a clipping campaign is run on (SPEC-v2 3.18: map each
campaign to the clipper's own social accounts), and the posts of the
campaign's bulk scheduler.

A campaign's accounts are the owner's own accounts (clipforge.social_accounts)
on platforms that the campaign allows (with none listed any account can be
mapped, but the rule checker blocks publishing until the campaign lists the
platform). The bulk scheduler of a campaign is
clipforge.post_schedule.bulk_schedule with these accounts as the targets.
"""

from sqlalchemy import Engine, delete
from sqlmodel import Session, col, select

from clipforge import campaigns, social_accounts
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import Campaign, PostTarget, PostText, SocialAccount
from clipforge.social_rows import SocialAccountRow
from clipforge.submission_rows import CampaignAccountRow


class PlatformNotAllowed(ValueError):
    """An account is on a platform that the campaign does not allow."""


class ClipsNotInCampaign(ValueError):
    """Clips that do not belong to a project of the campaign; clip_ids lists
    them."""

    def __init__(self, campaign: Campaign, clip_ids: list[int]) -> None:
        super().__init__(
            f"clips {clip_ids} are not in a project of campaign {campaign.name!r}"
        )
        self.clip_ids = clip_ids


class NoCampaignAccounts(ValueError):
    """The campaign has no accounts to post to."""


def list_accounts(engine: Engine, campaign_id: int) -> list[SocialAccount]:
    """Return the accounts that campaign campaign_id is run on, oldest
    account first; CampaignNotFound if there is no such campaign."""
    campaigns.get_campaign(engine, campaign_id)
    with Session(engine) as session:
        rows = session.exec(
            select(SocialAccountRow)
            .join(
                CampaignAccountRow,
                col(CampaignAccountRow.account_id) == col(SocialAccountRow.id),
            )
            .where(col(CampaignAccountRow.campaign_id) == campaign_id)
            .order_by(col(SocialAccountRow.id))
        )
        return [row.to_model() for row in rows]


def set_accounts(
    engine: Engine, campaign_id: int, account_ids: list[int]
) -> list[SocialAccount]:
    """Make account_ids the accounts of the campaign and return them.

    Raise CampaignNotFound, social_accounts.AccountNotFound for an unknown
    account and PlatformNotAllowed for an account on a platform the campaign
    does not allow; nothing changes then.
    """
    campaign = campaigns.get_campaign(engine, campaign_id)
    for account_id in account_ids:
        check_platform(campaign, social_accounts.get_account(engine, account_id))
    with Session(engine) as session:
        session.exec(
            delete(CampaignAccountRow).where(
                col(CampaignAccountRow.campaign_id) == campaign_id
            )
        )
        for account_id in dict.fromkeys(account_ids):
            session.add(
                CampaignAccountRow(campaign_id=campaign_id, account_id=account_id)
            )
        session.commit()
    return list_accounts(engine, campaign_id)


def bulk_targets(
    engine: Engine, campaign: Campaign, text: PostText
) -> list[PostTarget]:
    """Return the targets of the campaign's bulk scheduler: each of its
    accounts saying text. NoCampaignAccounts if it has none and
    PlatformNotAllowed if the campaign stopped allowing an account's
    platform since it was mapped."""
    accounts = list_accounts(engine, campaign.id)
    if not accounts:
        raise NoCampaignAccounts(
            f"campaign {campaign.name!r} has no accounts: choose them first"
        )
    for account in accounts:
        check_platform(campaign, account)
    return [PostTarget(account_id=a.id, text=text) for a in accounts]


def check_clips(engine: Engine, campaign: Campaign, clip_ids: list[int]) -> None:
    """Check that every clip is in a project of the campaign;
    ClipsNotInCampaign lists those that are not (or do not exist)."""
    with Session(engine) as session:
        found = set(
            session.exec(
                select(ClipRow.id)
                .join(ProjectRow, col(ProjectRow.id) == col(ClipRow.project_id))
                .where(
                    col(ClipRow.id).in_(clip_ids),
                    col(ProjectRow.campaign_id) == campaign.id,
                )
            )
        )
    missing = [clip_id for clip_id in dict.fromkeys(clip_ids) if clip_id not in found]
    if missing:
        raise ClipsNotInCampaign(campaign, missing)


def check_platform(campaign: Campaign, account: SocialAccount) -> None:
    """Raise PlatformNotAllowed if the campaign allows platforms and the
    account's is not one of them."""
    allowed = campaign.allowed_platforms
    if allowed and account.platform not in allowed:
        raise PlatformNotAllowed(
            f"{account.display_name or account.platform} is on "
            f"{account.platform}, which campaign {campaign.name!r} does not "
            f"allow ({', '.join(allowed)})"
        )
