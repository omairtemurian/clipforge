"""The autopilot settings of a campaign (SPEC-v2 3.19).

A campaign that was never set up has the defaults (autopilot off, 3 clips per
source video, at most 3 posts a day on an account with a hard cap of 5, drafts
expire after 3 days). Saving replaces all of a campaign's settings and checks
what they name: the caption template, the brand template, and that every
account exists and is on a platform that the campaign allows.
"""

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import campaign_accounts, campaigns, social_accounts
from clipforge.autopilot.rows import AutopilotSettingsRow
from clipforge.campaign_presets import check_caption_template
from clipforge.db import BrandTemplateRow
from clipforge.models import AutopilotSettings, AutopilotSettingsUpdate
from clipforge.social_rows import SocialAccountRow


class BrandTemplateNotFound(LookupError):
    """The settings name a brand template that does not exist."""


def get_settings(engine: Engine, campaign_id: int) -> AutopilotSettings:
    """Return the autopilot settings of the campaign, the defaults if it was
    never set up. Accounts that were disconnected since are left out.
    campaigns.CampaignNotFound if there is no such campaign."""
    campaigns.get_campaign(engine, campaign_id)
    with Session(engine) as session:
        row = session.get(AutopilotSettingsRow, campaign_id)
        if row is None:
            return AutopilotSettings(campaign_id=campaign_id)
        settings = row.to_model()
        known = set(
            session.exec(
                select(SocialAccountRow.id).where(
                    col(SocialAccountRow.id).in_(settings.account_ids)
                )
            )
        )
    settings.account_ids = [i for i in settings.account_ids if i in known]
    return settings


def save_settings(
    engine: Engine, campaign_id: int, update: AutopilotSettingsUpdate
) -> AutopilotSettings:
    """Make update the autopilot settings of the campaign and return them.

    Raise campaigns.CampaignNotFound, campaign_presets.UnknownCaptionTemplate,
    BrandTemplateNotFound, social_accounts.AccountNotFound for an unknown
    account and campaign_accounts.PlatformNotAllowed for an account on a
    platform that the campaign does not allow; nothing changes then.
    """
    campaign = campaigns.get_campaign(engine, campaign_id)
    check_caption_template(update.caption_template)
    for account_id in update.account_ids:
        campaign_accounts.check_platform(
            campaign, social_accounts.get_account(engine, account_id)
        )
    with Session(engine) as session:
        brand_id = update.brand_template_id
        if brand_id is not None and session.get(BrandTemplateRow, brand_id) is None:
            raise BrandTemplateNotFound(f"brand template {brand_id} does not exist")
        session.merge(
            AutopilotSettingsRow(campaign_id=campaign_id, **update.model_dump())
        )
        session.commit()
    return get_settings(engine, campaign_id)
